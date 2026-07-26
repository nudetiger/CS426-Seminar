package com.cs426.gallery;

import android.content.Intent;
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
import java.util.Collections;
import java.util.List;

/**
 * Phase 2 step 2 gallery host: RecyclerView grid with bind-time (viewport) loading.
 * Images decode when cells bind; recycled holders clear bitmaps so stale pixels never stick.
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";

    private RecyclerView galleryRecycler;
    private GalleryAdapter galleryAdapter;
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

        GalleryRepository repository = new GalleryRepository(this);
        ImageDecoder decoder = new ImageDecoder(this);

        galleryAdapter = new GalleryAdapter(repository, decoder);
        galleryAdapter.setOnImageClickListener(this::openPreview);
        galleryRecycler.setAdapter(galleryAdapter);

        try {
            images = repository.loadImages();
        } catch (IOException e) {
            Log.e(TAG, "Failed to load gallery manifest", e);
            Toast.makeText(this, R.string.gallery_load_error, Toast.LENGTH_LONG).show();
            return;
        }

        // Metadata only at init — decode happens in adapter onBind (viewport loading).
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

        galleryAdapter.submit(images, cellSize);
        gridReady = true;
        // After submit, the next frame has bound the first viewport (sync decode on main thread).
        galleryRecycler.post(() -> {
            if (isFinishing()) {
                return;
            }
            BenchLog.mark(
                    "gallery_ready",
                    createElapsedRealtime,
                    "dataset=" + BuildConfig.GALLERY_DATASET + " count=" + images.size());
            reportFullyDrawn();
        });
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
        if (galleryAdapter != null) {
            galleryAdapter.releaseBitmaps(galleryRecycler);
        }
        if (galleryRecycler != null) {
            galleryRecycler.setAdapter(null);
        }
        super.onDestroy();
    }
}
