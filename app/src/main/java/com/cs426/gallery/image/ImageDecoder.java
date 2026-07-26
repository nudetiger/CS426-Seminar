package com.cs426.gallery.image;

import android.content.Context;
import android.content.res.AssetManager;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * Decodes local asset images. Grid cells still use full-resolution decode until step 4.
 * Sampled thumbnail decode will be added in Phase 2 step 4.
 */
public class ImageDecoder {

    private final AssetManager assets;

    public ImageDecoder(Context context) {
        this.assets = context.getApplicationContext().getAssets();
    }

    public Bitmap decodeAssetFull(String assetPath) throws IOException {
        // Decode from a byte array: AssetManager streams are not always mark-supported,
        // so BitmapFactory.decodeStream(InputStream) can return null for valid JPEGs.
        byte[] bytes = readAssetBytes(assetPath);
        Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
        if (bitmap == null) {
            throw new IOException("Failed to decode bitmap: " + assetPath);
        }
        return bitmap;
    }

    private byte[] readAssetBytes(String assetPath) throws IOException {
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
