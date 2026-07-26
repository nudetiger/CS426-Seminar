package com.cs426.gallery;

import android.content.Intent;
import android.graphics.Bitmap;
import android.os.Bundle;
import android.util.Log;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.GridLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.cs426.gallery.bench.BenchLog;
import com.cs426.gallery.data.GalleryImage;
import com.cs426.gallery.data.GalleryRepository;
import com.cs426.gallery.image.ImageDecoder;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Phase 2 step 1 gallery host: RecyclerView + GridLayoutManager recycle cell views,
 * but still decodes every original-resolution image on the main thread at init.
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";

    private RecyclerView galleryRecycler;
    private GalleryAdapter galleryAdapter;
    private final List<Bitmap> decodedBitmaps = new ArrayList<>();
    private List<GalleryImage> images = Collections.emptyList();
    private boolean gridReady;
    private long createElapsedRealtime;

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        createElapsedRealtime = BenchLog.now();
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        galleryRecycler = findViewById(R.id.gallery_recycler);
        int columnCount = getResources().getInteger(R.integer.gallery_column_count);
        galleryRecycler.setLayoutManager(new GridLayoutManager(this, columnCount));
        galleryRecycler.addItemDecoration(new GalleryGridSpacingDecoration(
                columnCount,
                getResources().getDimensionPixelSize(R.dimen.gallery_column_spacing),
                getResources().getDimensionPixelSize(R.dimen.gallery_row_spacing)));
        galleryRecycler.setHasFixedSize(true);

        galleryAdapter = new GalleryAdapter();
        galleryAdapter.setOnImageClickListener(this::openPreview);
        galleryRecycler.setAdapter(galleryAdapter);

        GalleryRepository repository = new GalleryRepository(this);
        ImageDecoder decoder = new ImageDecoder(this);

        try {
            images = repository.loadImages();
        } catch (IOException e) {
            Log.e(TAG, "Failed to load gallery manifest", e);
            Toast.makeText(this, R.string.gallery_load_error, Toast.LENGTH_LONG).show();
            return;
        }

        // Still Phase 1-style bottleneck until later steps: decode all originals at init.
        for (GalleryImage image : images) {
            try {
                Bitmap bitmap = decoder.decodeAssetFull(repository.getImageAssetPath(image));
                decodedBitmaps.add(bitmap);
            } catch (IOException e) {
                Log.e(TAG, "Failed to decode " + image.getFilename(), e);
                decodedBitmaps.add(null);
            }
        }

        galleryRecycler.post(this::bindGridWhenSized);
    }

    private void bindGridWhenSized() {
        if (gridReady || isFinishing()) {
            return;
        }

        int columnCount = getResources().getInteger(R.integer.gallery_column_count);
        int containerWidth = resolveGalleryContentWidth();
        if (columnCount <= 0) {
            return;
        }
        if (containerWidth <= 0) {
            galleryRecycler.post(this::bindGridWhenSized);
            return;
        }

        int columnSpacing = getResources().getDimensionPixelSize(R.dimen.gallery_column_spacing);
        int totalSpacing = columnSpacing * (columnCount - 1);
        int availableWidth = Math.max(0, containerWidth - totalSpacing);
        int cellSize = Math.max(1, availableWidth / columnCount);

        galleryAdapter.submit(images, decodedBitmaps, cellSize);
        gridReady = true;
        BenchLog.mark(
                "gallery_ready",
                createElapsedRealtime,
                "dataset=" + BuildConfig.GALLERY_DATASET + " count=" + images.size());
        reportFullyDrawn();
    }

    private int resolveGalleryContentWidth() {
        int width = galleryRecycler.getWidth()
                - galleryRecycler.getPaddingLeft()
                - galleryRecycler.getPaddingRight();
        if (width > 0) {
            return width;
        }

        width = getResources().getDisplayMetrics().widthPixels
                - galleryRecycler.getPaddingLeft()
                - galleryRecycler.getPaddingRight();
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
        if (galleryRecycler != null) {
            galleryRecycler.setAdapter(null);
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
