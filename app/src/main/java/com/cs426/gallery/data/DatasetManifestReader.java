package com.cs426.gallery.data;

import android.content.Context;
import android.content.res.AssetManager;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

/**
 * Parses dataset manifest.json and orders items oldest-to-newest by timestamp, then id.
 */
public class DatasetManifestReader {

    public List<GalleryImage> readFromAssets(Context context, String assetPath) throws IOException {
        AssetManager assets = context.getApplicationContext().getAssets();
        try (InputStream in = assets.open(assetPath)) {
            return read(in);
        } catch (JSONException e) {
            throw new IOException("Invalid manifest JSON at " + assetPath, e);
        }
    }

    public List<GalleryImage> read(InputStream in) throws IOException, JSONException {
        String json = readFully(in);
        JSONObject root = new JSONObject(json);
        JSONArray items = root.optJSONArray("images");
        if (items == null) {
            items = root.optJSONArray("items");
        }
        if (items == null && root.has("id")) {
            // Single-object fallback is not expected; keep parse strict for datasets.
            throw new JSONException("manifest must contain an 'images' or 'items' array");
        }
        if (items == null) {
            throw new JSONException("manifest must contain an 'images' or 'items' array");
        }

        List<GalleryImage> images = new ArrayList<>(items.length());
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.getJSONObject(i);
            images.add(new GalleryImage(
                    item.getInt("id"),
                    item.getString("filename"),
                    item.getString("timestamp"),
                    item.getInt("width"),
                    item.getInt("height")
            ));
        }

        Collections.sort(images, Comparator
                .comparing(GalleryImage::getTimestamp)
                .thenComparingInt(GalleryImage::getId));
        return images;
    }

    private static String readFully(InputStream in) throws IOException {
        StringBuilder sb = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(in, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line).append('\n');
            }
        }
        return sb.toString();
    }
}
