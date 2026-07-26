package com.cs426.gallery;

import android.graphics.Rect;
import android.view.View;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

/**
 * Matches Phase 1 column/row spacing for a fixed-span grid.
 */
public class GalleryGridSpacingDecoration extends RecyclerView.ItemDecoration {

    private final int spanCount;
    private final int horizontalSpacing;
    private final int verticalSpacing;

    public GalleryGridSpacingDecoration(int spanCount, int horizontalSpacing, int verticalSpacing) {
        this.spanCount = Math.max(1, spanCount);
        this.horizontalSpacing = Math.max(0, horizontalSpacing);
        this.verticalSpacing = Math.max(0, verticalSpacing);
    }

    @Override
    public void getItemOffsets(
            @NonNull Rect outRect,
            @NonNull View view,
            @NonNull RecyclerView parent,
            @NonNull RecyclerView.State state) {
        int position = parent.getChildAdapterPosition(view);
        if (position == RecyclerView.NO_POSITION) {
            return;
        }

        int column = position % spanCount;
        outRect.left = column * horizontalSpacing / spanCount;
        outRect.right = horizontalSpacing - (column + 1) * horizontalSpacing / spanCount;
        if (position >= spanCount) {
            outRect.top = verticalSpacing;
        }
    }
}
