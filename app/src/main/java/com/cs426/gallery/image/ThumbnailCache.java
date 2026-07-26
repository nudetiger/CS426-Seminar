package com.cs426.gallery.image;

import android.graphics.Bitmap;
import android.util.LruCache;

import androidx.annotation.Nullable;

/**
 * Bounded in-memory thumbnail cache keyed by image id + display size.
 * Holds only {@link Bitmap} values — never Activity, View, or Context references.
 */
public final class ThumbnailCache {

    private final LruCache<String, Bitmap> cache;

    public ThumbnailCache(int maxSizeBytes) {
        final int maxSize = Math.max(1, maxSizeBytes);
        cache = new LruCache<String, Bitmap>(maxSize) {
            @Override
            protected int sizeOf(String key, Bitmap value) {
                return Math.max(1, value.getByteCount());
            }

            @Override
            protected void entryRemoved(
                    boolean evicted,
                    String key,
                    Bitmap oldValue,
                    @Nullable Bitmap newValue) {
                if (oldValue != null && oldValue != newValue && !oldValue.isRecycled()) {
                    oldValue.recycle();
                }
            }
        };
    }

    /** Default budget: 1/8 of the app heap max, matching common Android thumbnail guidance. */
    public static int defaultMaxSizeBytes() {
        long eighth = Runtime.getRuntime().maxMemory() / 8L;
        return (int) Math.min(Integer.MAX_VALUE, Math.max(1L, eighth));
    }

    public static String key(int imageId, int sizePx) {
        return imageId + "@" + Math.max(1, sizePx);
    }

    @Nullable
    public Bitmap get(String key) {
        return cache.get(key);
    }

    public void put(String key, Bitmap bitmap) {
        if (key == null || bitmap == null || bitmap.isRecycled()) {
            return;
        }
        cache.put(key, bitmap);
    }

    public void clear() {
        cache.evictAll();
    }
}
