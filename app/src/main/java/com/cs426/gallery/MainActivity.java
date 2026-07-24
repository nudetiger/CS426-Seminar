package com.cs426.gallery;

import android.content.Intent;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.util.Log;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;

import com.cs426.gallery.data.GalleryImage;
import com.cs426.gallery.data.GalleryRepository;
import com.cs426.gallery.image.ImageDecoder;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Phase 1 gallery host: eagerly builds the full ScrollView hierarchy and decodes
 * every original-resolution image on the main thread into screen-owned state.
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";

    private View galleryScroll;
    private LinearLayout galleryContainer;
    private final List<Bitmap> decodedBitmaps = new ArrayList<>();
    private List<GalleryImage> images = Collections.emptyList();
    private boolean gridBuilt;

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        galleryScroll = findViewById(R.id.gallery_scroll);
        galleryContainer = findViewById(R.id.gallery_container);

        GalleryRepository repository = new GalleryRepository(this);
        ImageDecoder decoder = new ImageDecoder(this);

        try {
            images = repository.loadImages();
        } catch (IOException e) {
            Log.e(TAG, "Failed to load gallery manifest", e);
            Toast.makeText(this, R.string.gallery_load_error, Toast.LENGTH_LONG).show();
            return;
        }

        // Phase 1 bottleneck: decode all originals on the main thread during init.
        for (GalleryImage image : images) {
            try {
                Bitmap bitmap = decoder.decodeAssetFull(repository.getImageAssetPath(image));
                decodedBitmaps.add(bitmap);
            } catch (IOException e) {
                Log.e(TAG, "Failed to decode " + image.getFilename(), e);
                decodedBitmaps.add(null);
            }
        }

        galleryContainer.post(this::buildEagerGrid);
    }

    private void buildEagerGrid() {
        if (gridBuilt || isFinishing()) {
            return;
        }

        int columnCount = getResources().getInteger(R.integer.gallery_column_count);
        // ScrollView children with wrap_content can report width 0 while empty; measure the
        // ScrollView (or display width) so the eager grid still builds on first layout.
        int containerWidth = resolveGalleryContentWidth();
        if (columnCount <= 0) {
            return;
        }
        if (containerWidth <= 0) {
            galleryContainer.post(this::buildEagerGrid);
            return;
        }

        galleryContainer.removeAllViews();

        int columnSpacing = getResources().getDimensionPixelSize(R.dimen.gallery_column_spacing);
        int rowSpacing = getResources().getDimensionPixelSize(R.dimen.gallery_row_spacing);
        int totalSpacing = columnSpacing * (columnCount - 1);
        // Guard narrow widths where spacing alone can exceed the container.
        int availableWidth = Math.max(0, containerWidth - totalSpacing);
        int cellSize = Math.max(1, availableWidth / columnCount);

        LayoutInflater inflater = LayoutInflater.from(this);
        LinearLayout currentRow = null;

        for (int index = 0; index < images.size(); index++) {
            if (index % columnCount == 0) {
                currentRow = new LinearLayout(this);
                currentRow.setOrientation(LinearLayout.HORIZONTAL);
                LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(
                        LinearLayout.LayoutParams.MATCH_PARENT,
                        LinearLayout.LayoutParams.WRAP_CONTENT);
                if (index > 0) {
                    rowParams.topMargin = rowSpacing;
                }
                galleryContainer.addView(currentRow, rowParams);
            }

            GalleryImage image = images.get(index);
            View itemView = inflater.inflate(R.layout.item_gallery_image, currentRow, false);
            LinearLayout.LayoutParams cellParams = new LinearLayout.LayoutParams(cellSize, cellSize);
            int column = index % columnCount;
            if (column > 0) {
                cellParams.setMarginStart(columnSpacing);
            }
            itemView.setLayoutParams(cellParams);

            ImageView imageView = itemView.findViewById(R.id.item_image);
            imageView.setContentDescription(
                    getString(R.string.gallery_item_cd_indexed, image.getId()));
            Bitmap bitmap = decodedBitmaps.get(index);
            if (bitmap != null) {
                imageView.setImageBitmap(bitmap);
            }

            final int imageIndex = index;
            final int imageId = image.getId();
            itemView.setOnClickListener(v -> openPreview(imageId, imageIndex));
            currentRow.addView(itemView);
        }

        gridBuilt = true;
    }

    private int resolveGalleryContentWidth() {
        int width = galleryContainer.getWidth()
                - galleryContainer.getPaddingLeft()
                - galleryContainer.getPaddingRight();
        if (width > 0) {
            return width;
        }

        if (galleryScroll != null) {
            width = galleryScroll.getWidth()
                    - galleryContainer.getPaddingLeft()
                    - galleryContainer.getPaddingRight();
            if (width > 0) {
                return width;
            }
        }

        width = getResources().getDisplayMetrics().widthPixels
                - galleryContainer.getPaddingLeft()
                - galleryContainer.getPaddingRight();
        return Math.max(width, 0);
    }

    private void openPreview(int imageId, int imageIndex) {
        Intent intent = new Intent(this, PreviewActivity.class);
        intent.putExtra(PreviewActivity.EXTRA_IMAGE_ID, imageId);
        intent.putExtra(PreviewActivity.EXTRA_IMAGE_INDEX, imageIndex);
        startActivity(intent);
    }

    @Override
    protected void onDestroy() {
        if (galleryContainer != null) {
            galleryContainer.removeAllViews();
        }
        for (Bitmap bitmap : decodedBitmaps) {
            if (bitmap != null && !bitmap.isRecycled()) {
                bitmap.recycle();
            }
        }
        decodedBitmaps.clear();
        super.onDestroy();
    }
}
