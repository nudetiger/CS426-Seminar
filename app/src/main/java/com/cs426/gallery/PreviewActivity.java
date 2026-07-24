package com.cs426.gallery;

import android.graphics.Bitmap;
import android.os.Bundle;
import android.util.Log;
import android.view.MenuItem;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.appcompat.app.ActionBar;
import androidx.appcompat.app.AppCompatActivity;

import com.cs426.gallery.data.GalleryImage;
import com.cs426.gallery.data.GalleryRepository;
import com.cs426.gallery.image.ImageDecoder;

import java.io.IOException;
import java.util.Collections;
import java.util.List;

/**
 * Full-image preview. Receives image id/index via Intent extras (never a Bitmap).
 * Loads the original dataset file; navigates with arrows and an intentionally
 * inefficient finger-follow swipe that decodes the neighbor only after a swipe starts.
 */
public class PreviewActivity extends AppCompatActivity {

    public static final String EXTRA_IMAGE_ID = "extra_image_id";
    public static final String EXTRA_IMAGE_INDEX = "extra_image_index";

    private static final String TAG = "PreviewActivity";
    private static final float SWIPE_COMMIT_FRACTION = 0.28f;

    private View swipeLayer;
    private ImageView previewImage;
    private ImageView adjacentImage;
    private ImageButton prevButton;
    private ImageButton nextButton;

    private GalleryRepository repository;
    private ImageDecoder decoder;
    private List<GalleryImage> images = Collections.emptyList();
    private int currentIndex;
    @Nullable
    private Bitmap currentBitmap;
    @Nullable
    private Bitmap adjacentBitmap;
    private int adjacentIndex = -1;

    private int touchSlop;
    private float downX;
    private float downY;
    private boolean trackingSwipe;
    private boolean swipeArmed;
    /** -1 = toward previous, +1 = toward next, 0 = undecided. */
    private int swipeDirection;

    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_preview);

        ActionBar actionBar = getSupportActionBar();
        if (actionBar != null) {
            actionBar.setDisplayHomeAsUpEnabled(true);
        }

        swipeLayer = findViewById(R.id.preview_swipe_layer);
        previewImage = findViewById(R.id.preview_image);
        adjacentImage = findViewById(R.id.preview_image_adjacent);
        prevButton = findViewById(R.id.preview_prev);
        nextButton = findViewById(R.id.preview_next);

        repository = new GalleryRepository(this);
        decoder = new ImageDecoder(this);
        touchSlop = ViewConfiguration.get(this).getScaledTouchSlop();

        try {
            images = repository.loadImages();
        } catch (IOException e) {
            Log.e(TAG, "Failed to load gallery manifest", e);
            Toast.makeText(this, R.string.gallery_load_error, Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        if (images.isEmpty()) {
            Toast.makeText(this, R.string.gallery_load_error, Toast.LENGTH_LONG).show();
            finish();
            return;
        }

        currentIndex = resolveStartIndex();
        prevButton.setOnClickListener(v -> showAtIndex(currentIndex - 1));
        nextButton.setOnClickListener(v -> showAtIndex(currentIndex + 1));
        swipeLayer.setOnTouchListener(this::onSwipeTouch);
        showAtIndex(currentIndex);
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == android.R.id.home) {
            finish();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    private int resolveStartIndex() {
        int indexExtra = getIntent().getIntExtra(EXTRA_IMAGE_INDEX, -1);
        if (indexExtra >= 0 && indexExtra < images.size()) {
            return indexExtra;
        }

        int idExtra = getIntent().getIntExtra(EXTRA_IMAGE_ID, -1);
        if (idExtra >= 0) {
            for (int i = 0; i < images.size(); i++) {
                if (images.get(i).getId() == idExtra) {
                    return i;
                }
            }
        }
        return 0;
    }

    private boolean onSwipeTouch(View v, MotionEvent event) {
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downX = event.getX();
                downY = event.getY();
                trackingSwipe = true;
                swipeArmed = false;
                swipeDirection = 0;
                return true;

            case MotionEvent.ACTION_MOVE:
                if (!trackingSwipe) {
                    return false;
                }
                float dx = event.getX() - downX;
                float dy = event.getY() - downY;
                if (!swipeArmed) {
                    if (Math.abs(dx) < touchSlop || Math.abs(dx) < Math.abs(dy)) {
                        return true;
                    }
                    // Intentionally bad: neighbor decode starts only once a swipe is detected.
                    swipeDirection = dx < 0 ? 1 : -1;
                    int targetIndex = currentIndex + swipeDirection;
                    if (targetIndex < 0 || targetIndex >= images.size()) {
                        swipeDirection = 0;
                        return true;
                    }
                    swipeArmed = true;
                    loadAdjacentForSwipe(targetIndex);
                }
                if (swipeArmed && swipeDirection != 0 && adjacentBitmap != null) {
                    applyMergeDrag(dx);
                }
                return true;

            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                if (swipeArmed && swipeDirection != 0 && adjacentBitmap != null) {
                    float totalDx = event.getX() - downX;
                    float width = Math.max(swipeLayer.getWidth(), 1);
                    boolean commit = Math.abs(totalDx) >= width * SWIPE_COMMIT_FRACTION
                            && Math.signum(totalDx) == -swipeDirection;
                    if (commit) {
                        commitSwipe(currentIndex + swipeDirection);
                    } else {
                        cancelSwipe();
                    }
                } else {
                    resetSwipeVisuals();
                    clearAdjacent();
                }
                trackingSwipe = false;
                swipeArmed = false;
                swipeDirection = 0;
                return true;

            default:
                return false;
        }
    }

    /**
     * Phase 1 preview bottleneck: full-resolution decode of the neighbor only after swipe
     * detection, on the main thread, so the drag hitch is observable.
     */
    private void loadAdjacentForSwipe(int index) {
        if (adjacentIndex == index && adjacentBitmap != null) {
            return;
        }
        clearAdjacent();
        GalleryImage image = images.get(index);
        try {
            adjacentBitmap = decoder.decodeAssetFull(repository.getImageAssetPath(image));
            adjacentIndex = index;
            adjacentImage.setImageBitmap(adjacentBitmap);
            adjacentImage.setVisibility(View.VISIBLE);
            float width = swipeLayer.getWidth();
            adjacentImage.setTranslationX(swipeDirection > 0 ? width : -width);
        } catch (IOException e) {
            Log.e(TAG, "Failed to decode adjacent preview for " + image.getFilename(), e);
            Toast.makeText(this, R.string.preview_load_error, Toast.LENGTH_SHORT).show();
            clearAdjacent();
            swipeArmed = false;
            swipeDirection = 0;
        }
    }

    private void applyMergeDrag(float dx) {
        float width = swipeLayer.getWidth();
        if (width <= 0) {
            return;
        }
        // Clamp so the pages stay visually paired while dragging.
        float clamped = Math.max(-width, Math.min(width, dx));
        if (swipeDirection > 0) {
            clamped = Math.min(0f, clamped);
        } else {
            clamped = Math.max(0f, clamped);
        }
        previewImage.setTranslationX(clamped);
        adjacentImage.setTranslationX(clamped + (swipeDirection > 0 ? width : -width));
    }

    private void commitSwipe(int newIndex) {
        Bitmap previous = currentBitmap;
        currentBitmap = adjacentBitmap;
        adjacentBitmap = null;
        adjacentIndex = -1;
        currentIndex = newIndex;

        previewImage.setImageBitmap(currentBitmap);
        previewImage.setTranslationX(0f);
        adjacentImage.setImageDrawable(null);
        adjacentImage.setTranslationX(0f);
        adjacentImage.setVisibility(View.GONE);

        if (previous != null && !previous.isRecycled()) {
            previous.recycle();
        }

        GalleryImage image = images.get(currentIndex);
        previewImage.setContentDescription(
                getString(R.string.preview_image_cd_indexed, image.getId()));
        updateArrowState();
    }

    private void cancelSwipe() {
        previewImage.animate().translationX(0f).setDuration(120).start();
        float width = swipeLayer.getWidth();
        float rest = swipeDirection > 0 ? width : -width;
        adjacentImage.animate()
                .translationX(rest)
                .setDuration(120)
                .withEndAction(this::clearAdjacent)
                .start();
    }

    private void resetSwipeVisuals() {
        previewImage.animate().cancel();
        adjacentImage.animate().cancel();
        previewImage.setTranslationX(0f);
        adjacentImage.setTranslationX(0f);
    }

    private void clearAdjacent() {
        adjacentImage.animate().cancel();
        adjacentImage.setImageDrawable(null);
        adjacentImage.setTranslationX(0f);
        adjacentImage.setVisibility(View.GONE);
        if (adjacentBitmap != null && !adjacentBitmap.isRecycled()) {
            adjacentBitmap.recycle();
        }
        adjacentBitmap = null;
        adjacentIndex = -1;
    }

    private void showAtIndex(int index) {
        if (index < 0 || index >= images.size()) {
            return;
        }
        resetSwipeVisuals();
        clearAdjacent();
        trackingSwipe = false;
        swipeArmed = false;
        swipeDirection = 0;

        currentIndex = index;
        GalleryImage image = images.get(currentIndex);

        Bitmap previous = currentBitmap;
        currentBitmap = null;
        previewImage.setImageDrawable(null);
        if (previous != null && !previous.isRecycled()) {
            previous.recycle();
        }

        try {
            currentBitmap = decoder.decodeAssetFull(repository.getImageAssetPath(image));
            previewImage.setImageBitmap(currentBitmap);
            previewImage.setContentDescription(
                    getString(R.string.preview_image_cd_indexed, image.getId()));
        } catch (IOException e) {
            Log.e(TAG, "Failed to decode preview for " + image.getFilename(), e);
            Toast.makeText(this, R.string.preview_load_error, Toast.LENGTH_SHORT).show();
        }

        updateArrowState();
    }

    private void updateArrowState() {
        boolean hasPrev = currentIndex > 0;
        boolean hasNext = currentIndex < images.size() - 1;
        prevButton.setVisibility(hasPrev ? View.VISIBLE : View.INVISIBLE);
        prevButton.setEnabled(hasPrev);
        nextButton.setVisibility(hasNext ? View.VISIBLE : View.INVISIBLE);
        nextButton.setEnabled(hasNext);
    }

    @Override
    protected void onDestroy() {
        resetSwipeVisuals();
        previewImage.setImageDrawable(null);
        clearAdjacent();
        if (currentBitmap != null && !currentBitmap.isRecycled()) {
            currentBitmap.recycle();
        }
        currentBitmap = null;
        super.onDestroy();
    }
}
