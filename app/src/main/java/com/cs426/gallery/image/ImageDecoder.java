package com.cs426.gallery.image;

import android.content.Context;
import android.content.res.AssetManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * Decodes local asset images. Grid cells use display-sized ({@code inSampleSize}) decode;
 * preview continues to use full-resolution decode of the original file.
 */
public class ImageDecoder {

    private final AssetManager assets;

    public ImageDecoder(Context context) {
        this.assets = context.getApplicationContext().getAssets();
    }

    /** Full-resolution decode for preview (original source file). */
    public Bitmap decodeAssetFull(String assetPath) throws IOException {
        byte[] bytes = readAssetBytes(assetPath);
        Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
        if (bitmap == null) {
            throw new IOException("Failed to decode bitmap: " + assetPath);
        }
        return bitmap;
    }

    /**
     * Decode scaled for a grid cell. Uses {@link BitmapFactory.Options#inSampleSize}
     * so the result is roughly display-sized (not full original resolution).
     */
    public Bitmap decodeAssetForDisplay(String assetPath, int reqWidthPx, int reqHeightPx)
            throws IOException {
        int reqWidth = Math.max(1, reqWidthPx);
        int reqHeight = Math.max(1, reqHeightPx);
        byte[] bytes = readAssetBytes(assetPath);

        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);

        BitmapFactory.Options decode = new BitmapFactory.Options();
        decode.inSampleSize = calculateInSampleSize(bounds, reqWidth, reqHeight);
        Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length, decode);
        if (bitmap == null) {
            throw new IOException("Failed to decode sampled bitmap: " + assetPath);
        }
        return bitmap;
    }

    /**
     * Largest power-of-two sample size that keeps both dimensions {@code >=} the request.
     * Matches the Android developer documentation pattern.
     */
    static int calculateInSampleSize(BitmapFactory.Options options, int reqWidth, int reqHeight) {
        final int height = options.outHeight;
        final int width = options.outWidth;
        int inSampleSize = 1;

        if (height > reqHeight || width > reqWidth) {
            final int halfHeight = height / 2;
            final int halfWidth = width / 2;
            while ((halfHeight / inSampleSize) >= reqHeight
                    && (halfWidth / inSampleSize) >= reqWidth) {
                inSampleSize *= 2;
            }
        }
        return Math.max(1, inSampleSize);
    }

    private byte[] readAssetBytes(String assetPath) throws IOException {
        // Decode from a byte array: AssetManager streams are not always mark-supported,
        // so BitmapFactory.decodeStream(InputStream) can return null for valid JPEGs.
        try (InputStream in = assets.open(assetPath);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[16 * 1024];
            int read;
            while ((read = in.read(buffer)) != -1) {
                out.write(buffer, 0, read);
            }
            return out.toByteArray();
        }
    }
}
