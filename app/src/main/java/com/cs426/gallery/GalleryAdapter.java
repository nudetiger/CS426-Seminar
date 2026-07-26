package com.cs426.gallery;

import android.graphics.Bitmap;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.recyclerview.widget.RecyclerView;

import com.cs426.gallery.data.GalleryImage;
import com.cs426.gallery.data.GalleryRepository;
import com.cs426.gallery.image.ImageDecoder;
import com.cs426.gallery.image.ThumbnailCache;

import java.io.IOException;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;

/**
 * Phase 2 step 6 adapter: bind-time display-sized decode with bounded cache, plus
 * scroll-aware UI applies (defer {@code setImageBitmap} while flinging) and
 * off-screen prefetch into the cache so scroll pays fewer decode/upload spikes.
 */
public class GalleryAdapter extends RecyclerView.Adapter<GalleryAdapter.GalleryViewHolder> {

    private static final String TAG = "GalleryAdapter";
    /** Extra rows above/below the visible window to decode into the cache. */
    private static final int PREFETCH_ROWS = 2;

    public interface OnImageClickListener {
        void onImageClick(int imageId, int imageIndex);
    }

    private final GalleryRepository repository;
    private final ImageDecoder decoder;
    private final ExecutorService decodeExecutor;
    private final ThumbnailCache thumbnailCache;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Set<String> inflightKeys = Collections.synchronizedSet(new HashSet<>());

    private List<GalleryImage> images = Collections.emptyList();
    private int cellSize;
    private int columnCount = 1;
    @Nullable
    private OnImageClickListener clickListener;
    private boolean shutdown;
    /** When true, misses still decode into cache but do not touch ImageViews until idle. */
    private boolean deferUiBitmapApply;

    public GalleryAdapter(
            @NonNull GalleryRepository repository,
            @NonNull ImageDecoder decoder,
            @NonNull ExecutorService decodeExecutor,
            @NonNull ThumbnailCache thumbnailCache) {
        this.repository = repository;
        this.decoder = decoder;
        this.decodeExecutor = decodeExecutor;
        this.thumbnailCache = thumbnailCache;
    }

    public void setOnImageClickListener(@Nullable OnImageClickListener listener) {
        clickListener = listener;
    }

    public void setColumnCount(int columnCount) {
        this.columnCount = Math.max(1, columnCount);
    }

    public void submit(List<GalleryImage> images, int cellSize) {
        this.images = images != null ? images : Collections.emptyList();
        this.cellSize = Math.max(1, cellSize);
        notifyDataSetChanged();
    }

    /**
     * While the list is dragging/settling, skip main-thread bitmap applies for decode
     * completions (cache is still populated). On resume, apply cache hits to visible cells.
     */
    public void setDeferUiBitmapApply(boolean defer, @Nullable RecyclerView recyclerView) {
        if (deferUiBitmapApply == defer) {
            return;
        }
        deferUiBitmapApply = defer;
        if (!defer && recyclerView != null) {
            applyCacheHitsToVisible(recyclerView);
        }
    }

    /**
     * Decode nearby positions into {@link ThumbnailCache} without binding views.
     * Safe to call from the main thread during scroll; work runs on the decode pool.
     */
    public void prefetchAround(int firstVisible, int lastVisible) {
        if (shutdown || images.isEmpty() || cellSize <= 0) {
            return;
        }

        int extra = PREFETCH_ROWS * columnCount;
        int start = Math.max(0, firstVisible - extra);
        int end = Math.min(images.size() - 1, lastVisible + extra);
        for (int position = start; position <= end; position++) {
            enqueueDecode(position, /* applyToHolder */ null, /* generation */ -1);
        }
    }

    @NonNull
    @Override
    public GalleryViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View itemView = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_gallery_image, parent, false);
        RecyclerView.LayoutParams params = new RecyclerView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                cellSize);
        itemView.setLayoutParams(params);
        return new GalleryViewHolder(itemView);
    }

    @Override
    public void onBindViewHolder(@NonNull GalleryViewHolder holder, int position) {
        ViewGroup.LayoutParams params = holder.itemView.getLayoutParams();
        if (params.height != cellSize) {
            params.height = cellSize;
            holder.itemView.setLayoutParams(params);
        }

        cancelPendingDecode(holder);
        clearHolderImage(holder);

        GalleryImage image = images.get(position);
        final int imageIndex = position;
        final int imageId = image.getId();
        final int reqSize = cellSize;
        final String cacheKey = ThumbnailCache.key(imageId, reqSize);

        holder.boundImageId = imageId;
        holder.bindGeneration++;
        final int generation = holder.bindGeneration;

        holder.imageView.setContentDescription(
                holder.itemView.getContext()
                        .getString(R.string.gallery_item_cd_indexed, imageId));

        holder.itemView.setOnClickListener(v -> {
            if (clickListener != null) {
                clickListener.onImageClick(imageId, imageIndex);
            }
        });

        Bitmap cached = thumbnailCache.get(cacheKey);
        if (cached != null && !cached.isRecycled()) {
            holder.imageView.setImageBitmap(cached);
            return;
        }

        holder.imageView.setImageDrawable(null);
        if (shutdown) {
            return;
        }

        // Cache miss: always decode into cache; apply to the holder only when not flinging.
        holder.decodeFuture = enqueueDecode(position, holder, generation);
    }

    /**
     * @param holder    if non-null, result may be applied to this holder (unless deferred)
     * @param generation holder bind generation, or -1 for prefetch-only
     */
    @Nullable
    private Future<?> enqueueDecode(
            int position,
            @Nullable GalleryViewHolder holder,
            int generation) {
        if (shutdown || position < 0 || position >= images.size() || cellSize <= 0) {
            return null;
        }

        GalleryImage image = images.get(position);
        final int imageId = image.getId();
        final String assetPath = repository.getImageAssetPath(image);
        final int reqSize = cellSize;
        final String cacheKey = ThumbnailCache.key(imageId, reqSize);

        Bitmap existing = thumbnailCache.get(cacheKey);
        if (existing != null && !existing.isRecycled()) {
            if (holder != null) {
                applyDecodedBitmap(holder, imageId, generation, existing);
            }
            return null;
        }

        if (!inflightKeys.add(cacheKey)) {
            // Another bind/prefetch already decoding this key; holder waits for cache on next idle.
            return null;
        }

        try {
            return decodeExecutor.submit(() -> {
                Bitmap decoded = null;
                try {
                    Bitmap cached = thumbnailCache.get(cacheKey);
                    if (cached != null && !cached.isRecycled()) {
                        decoded = cached;
                    } else {
                        decoded = decoder.decodeAssetForDisplay(assetPath, reqSize, reqSize);
                        if (decoded != null) {
                            thumbnailCache.put(cacheKey, decoded);
                        }
                    }
                } catch (IOException e) {
                    Log.e(TAG, "Failed to decode " + image.getFilename(), e);
                } finally {
                    inflightKeys.remove(cacheKey);
                }

                if (holder == null) {
                    return;
                }

                final Bitmap result = decoded;
                mainHandler.post(() -> {
                    if (deferUiBitmapApply) {
                        // Leave ImageView empty; cache is warm for the next idle pass / rebind.
                        return;
                    }
                    applyDecodedBitmap(holder, imageId, generation, result);
                });
            });
        } catch (RuntimeException e) {
            inflightKeys.remove(cacheKey);
            Log.e(TAG, "Failed to submit decode for " + image.getFilename(), e);
            return null;
        }
    }

    private void applyCacheHitsToVisible(@NonNull RecyclerView recyclerView) {
        for (int i = 0; i < recyclerView.getChildCount(); i++) {
            RecyclerView.ViewHolder raw = recyclerView.getChildViewHolder(recyclerView.getChildAt(i));
            if (!(raw instanceof GalleryViewHolder)) {
                continue;
            }
            GalleryViewHolder holder = (GalleryViewHolder) raw;
            int position = holder.getBindingAdapterPosition();
            if (position == RecyclerView.NO_POSITION || position >= images.size()) {
                continue;
            }
            if (holder.imageView.getDrawable() != null) {
                continue;
            }

            GalleryImage image = images.get(position);
            String cacheKey = ThumbnailCache.key(image.getId(), cellSize);
            Bitmap cached = thumbnailCache.get(cacheKey);
            if (cached != null && !cached.isRecycled()
                    && holder.isBindingCurrent(image.getId(), holder.bindGeneration)) {
                holder.imageView.setImageBitmap(cached);
            } else if (cached == null) {
                enqueueDecode(position, holder, holder.bindGeneration);
            }
        }
    }

    private void applyDecodedBitmap(
            @NonNull GalleryViewHolder holder,
            int imageId,
            int generation,
            @Nullable Bitmap decoded) {
        if (!holder.isBindingCurrent(imageId, generation) || shutdown) {
            return;
        }

        holder.decodeFuture = null;
        if (decoded != null && !decoded.isRecycled()) {
            holder.imageView.setImageBitmap(decoded);
        } else {
            holder.imageView.setImageDrawable(null);
        }
    }

    @Override
    public void onViewRecycled(@NonNull GalleryViewHolder holder) {
        cancelPendingDecode(holder);
        holder.bindGeneration++;
        holder.boundImageId = GalleryViewHolder.NO_ID;
        clearHolderImage(holder);
        holder.itemView.setOnClickListener(null);
        super.onViewRecycled(holder);
    }

    @Override
    public int getItemCount() {
        return images.size();
    }

    /**
     * Stop accepting new decode work callbacks. The Activity owns executor/cache teardown.
     */
    public void markShutdown() {
        shutdown = true;
        mainHandler.removeCallbacksAndMessages(null);
        inflightKeys.clear();
    }

    /** Detach bitmaps from visible holders (cache still owns recycling via eviction). */
    public void releaseBitmaps(@Nullable RecyclerView recyclerView) {
        if (recyclerView == null) {
            return;
        }
        for (int i = 0; i < recyclerView.getChildCount(); i++) {
            RecyclerView.ViewHolder raw = recyclerView.getChildViewHolder(recyclerView.getChildAt(i));
            if (raw instanceof GalleryViewHolder) {
                GalleryViewHolder holder = (GalleryViewHolder) raw;
                cancelPendingDecode(holder);
                holder.bindGeneration++;
                holder.boundImageId = GalleryViewHolder.NO_ID;
                clearHolderImage(holder);
            }
        }
    }

    private static void cancelPendingDecode(@NonNull GalleryViewHolder holder) {
        // Do not Future.cancel(): the decode should still warm ThumbnailCache for nearby cells.
        // Stale UI applies are ignored via bindGeneration / boundImageId.
        holder.decodeFuture = null;
    }

    private static void clearHolderImage(@NonNull GalleryViewHolder holder) {
        // Do not recycle: thumbnails may still be referenced by ThumbnailCache.
        holder.imageView.setImageDrawable(null);
    }

    static final class GalleryViewHolder extends RecyclerView.ViewHolder {
        static final int NO_ID = -1;

        final ImageView imageView;
        int boundImageId = NO_ID;
        int bindGeneration;
        @Nullable
        Future<?> decodeFuture;

        GalleryViewHolder(@NonNull View itemView) {
            super(itemView);
            imageView = itemView.findViewById(R.id.item_image);
        }

        boolean isBindingCurrent(int imageId, int generation) {
            return boundImageId == imageId && bindGeneration == generation;
        }
    }
}
