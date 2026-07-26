package com.cs426.gallery;

import android.graphics.Bitmap;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.recyclerview.widget.RecyclerView;

import com.cs426.gallery.data.GalleryImage;

import java.util.Collections;
import java.util.List;

/**
 * Phase 2 step 1 adapter: recycles cell views via ViewHolder.
 * Bitmaps are still supplied from eager decode-all-at-init (later steps change loading).
 */
public class GalleryAdapter extends RecyclerView.Adapter<GalleryAdapter.GalleryViewHolder> {

    public interface OnImageClickListener {
        void onImageClick(int imageId, int imageIndex);
    }

    private List<GalleryImage> images = Collections.emptyList();
    private List<Bitmap> bitmaps = Collections.emptyList();
    private int cellSize;
    @Nullable
    private OnImageClickListener clickListener;

    public void setOnImageClickListener(@Nullable OnImageClickListener listener) {
        clickListener = listener;
    }

    public void submit(List<GalleryImage> images, List<Bitmap> bitmaps, int cellSize) {
        this.images = images != null ? images : Collections.emptyList();
        this.bitmaps = bitmaps != null ? bitmaps : Collections.emptyList();
        this.cellSize = Math.max(1, cellSize);
        notifyDataSetChanged();
    }

    @NonNull
    @Override
    public GalleryViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View itemView = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_gallery_image, parent, false);
        // Width is MATCH_PARENT so GridLayoutManager + spacing decoration size columns;
        // height is the square edge matching Phase 1 cellSize.
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

        GalleryImage image = images.get(position);
        holder.imageView.setContentDescription(
                holder.itemView.getContext()
                        .getString(R.string.gallery_item_cd_indexed, image.getId()));

        Bitmap bitmap = position < bitmaps.size() ? bitmaps.get(position) : null;
        if (bitmap != null) {
            holder.imageView.setImageBitmap(bitmap);
        } else {
            holder.imageView.setImageDrawable(null);
        }

        final int imageIndex = position;
        final int imageId = image.getId();
        holder.itemView.setOnClickListener(v -> {
            if (clickListener != null) {
                clickListener.onImageClick(imageId, imageIndex);
            }
        });
    }

    @Override
    public int getItemCount() {
        return images.size();
    }

    static final class GalleryViewHolder extends RecyclerView.ViewHolder {
        final ImageView imageView;

        GalleryViewHolder(@NonNull View itemView) {
            super(itemView);
            imageView = itemView.findViewById(R.id.item_image);
        }
    }
}
