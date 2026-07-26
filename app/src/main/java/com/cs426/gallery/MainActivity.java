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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Phase 2 step 3 gallery host: viewport bind loads decode on a bounded background
 * executor; UI bitmap applies stay on the main thread; executor shuts down on destroy.
 */
public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MainActivity";

    private RecyclerView galleryRecycler;
    private GalleryAdapter galleryAdapter;
    @Nullable
    private ExecutorService decodeExecutor;
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
        decodeExecutor = createDecodeExecutor();

        galleryAdapter = new GalleryAdapter(repository, decoder, decodeExecutor);
        galleryAdapter.setOnImageClickListener(this::openPreview);
        galleryRecycler.setAdapter(galleryAdapter);

        try {
            images = repository.loadImages();
        } catch (IOException e) {
            Log.e(TAG, "Failed to load gallery manifest", e);
            Toast.makeText(this, R.string.gallery_load_error, Toast.LENGTH_LONG).show();
            return;
        }

        galleryRecycler.post(this::bindGridWhenSized);
    }

    private static ExecutorService createDecodeExecutor() {
        int cores = Runtime.getRuntime().availableProcessors();
        int poolSize = Math.max(2, Math.min(4, cores));
        AtomicInteger nextId = new AtomicInteger(1);
        ThreadFactory factory = runnable -> {
            Thread thread = new Thread(runnable, "gallery-decode-" + nextId.getAndIncrement());
            thread.setPriority(Thread.NORM_PRIORITY - 1);
            return thread;
        };
        return Executors.newFixedThreadPool(poolSize, factory);
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
        // Grid is laid out; visible cells decode asynchronously on the executor.
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
            galleryAdapter.markShutdown();
            galleryAdapter.releaseBitmaps(galleryRecycler);
        }
        if (galleryRecycler != null) {
            galleryRecycler.setAdapter(null);
        }
        if (decodeExecutor != null) {
            decodeExecutor.shutdownNow();
            decodeExecutor = null;
        }
        super.onDestroy();
    }
}
