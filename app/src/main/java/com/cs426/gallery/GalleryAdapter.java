package com.cs426.gallery;

import android.graphics.Bitmap;
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

import java.io.IOException;
import java.util.Collections;
import java.util.List;

/**
 * Phase 2 step 2 adapter: decodes each cell at bind time and clears/recycles on
 * ViewHolder recycle so recycled cells never keep or show stale bitmaps.
 * Decode remains on the main thread until step 3.
 */
public class GalleryAdapter extends RecyclerView.Adapter<GalleryAdapter.GalleryViewHolder> {

    private static final String TAG = "GalleryAdapter";

    public interface OnImageClickListener {
        void onImageClick(int imageId, int imageIndex);
    }

    private final GalleryRepository repository;
    private final ImageDecoder decoder;

    private List<GalleryImage> images = Collections.emptyList();
    private int cellSize;
    @Nullable
    private OnImageClickListener clickListener;

    public GalleryAdapter(@NonNull GalleryRepository repository, @NonNull ImageDecoder decoder) {
        this.repository = repository;
        this.decoder = decoder;
    }

    public void setOnImageClickListener(@Nullable OnImageClickListener listener) {
        clickListener = listener;
    }

    public void submit(List<GalleryImage> images, int cellSize) {
        this.images = images != null ? images : Collections.emptyList();
        this.cellSize = Math.max(1, cellSize);
        notifyDataSetChanged();
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

        clearHolderBitmap(holder);

        GalleryImage image = images.get(position);
        final int imageIndex = position;
        final int imageId = image.getId();
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

        // Viewport load: decode only the image for this bound cell.
        Bitmap decoded = null;
        try {
            decoded = decoder.decodeAssetFull(repository.getImageAssetPath(image));
        } catch (IOException e) {
            Log.e(TAG, "Failed to decode " + image.getFilename(), e);
        }

        if (!holder.isBindingCurrent(imageId, generation)) {
            // Recycled or rebound while decoding — drop the result (no stale apply).
            if (decoded != null && !decoded.isRecycled()) {
                decoded.recycle();
            }
            return;
        }

        if (decoded != null) {
            holder.boundBitmap = decoded;
            holder.imageView.setImageBitmap(decoded);
        } else {
            holder.imageView.setImageDrawable(null);
        }
    }

    @Override
    public void onViewRecycled(@NonNull GalleryViewHolder holder) {
        holder.bindGeneration++;
        holder.boundImageId = GalleryViewHolder.NO_ID;
        clearHolderBitmap(holder);
        holder.itemView.setOnClickListener(null);
        super.onViewRecycled(holder);
    }

    @Override
    public int getItemCount() {
        return images.size();
    }

    /** Drop any bitmaps still held by visible holders (call before Activity teardown). */
    public void releaseBitmaps(@Nullable RecyclerView recyclerView) {
        if (recyclerView == null) {
            return;
        }
        for (int i = 0; i < recyclerView.getChildCount(); i++) {
            RecyclerView.ViewHolder raw = recyclerView.getChildViewHolder(recyclerView.getChildAt(i));
            if (raw instanceof GalleryViewHolder) {
                GalleryViewHolder holder = (GalleryViewHolder) raw;
                holder.bindGeneration++;
                holder.boundImageId = GalleryViewHolder.NO_ID;
                clearHolderBitmap(holder);
            }
        }
    }

    private static void clearHolderBitmap(@NonNull GalleryViewHolder holder) {
        holder.imageView.setImageDrawable(null);
        if (holder.boundBitmap != null && !holder.boundBitmap.isRecycled()) {
            holder.boundBitmap.recycle();
        }
        holder.boundBitmap = null;
    }

    static final class GalleryViewHolder extends RecyclerView.ViewHolder {
        static final int NO_ID = -1;

        final ImageView imageView;
        int boundImageId = NO_ID;
        int bindGeneration;
        @Nullable
        Bitmap boundBitmap;

        GalleryViewHolder(@NonNull View itemView) {
            super(itemView);
            imageView = itemView.findViewById(R.id.item_image);
        }

        boolean isBindingCurrent(int imageId, int generation) {
            return boundImageId == imageId && bindGeneration == generation;
        }
    }
}
