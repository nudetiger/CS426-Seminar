package com.cs426.gallery.bench;

import android.os.SystemClock;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

/**
 * Structured log markers for the host-side benchmark harness ({@code GalleryBench} tag).
 * Format: {@code event key=value key=value} — keep payloads cheap (one line per event).
 */
public final class BenchLog {

    public static final String TAG = "GalleryBench";

    private BenchLog() {
    }

    public static long now() {
        return SystemClock.elapsedRealtime();
    }

    public static void mark(@NonNull String event, long startElapsedRealtime) {
        mark(event, startElapsedRealtime, null);
    }

    public static void mark(
            @NonNull String event,
            long startElapsedRealtime,
            @Nullable String extraKeyValues) {
        long elapsed = Math.max(0L, now() - startElapsedRealtime);
        StringBuilder line = new StringBuilder(event);
        line.append(" elapsed_ms=").append(elapsed);
        if (extraKeyValues != null && !extraKeyValues.isEmpty()) {
            line.append(' ').append(extraKeyValues);
        }
        Log.i(TAG, line.toString());
    }

    public static void markFields(@NonNull String event, @NonNull String keyValues) {
        Log.i(TAG, event + " " + keyValues);
    }
}
