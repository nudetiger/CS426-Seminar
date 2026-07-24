package com.cs426.gallery.data;

/**
 * Immutable metadata for one gallery image from the dataset manifest.
 */
public final class GalleryImage {

    private final int id;
    private final String filename;
    private final String timestamp;
    private final int width;
    private final int height;

    public GalleryImage(int id, String filename, String timestamp, int width, int height) {
        this.id = id;
        this.filename = filename;
        this.timestamp = timestamp;
        this.width = width;
        this.height = height;
    }

    public int getId() {
        return id;
    }

    public String getFilename() {
        return filename;
    }

    public String getTimestamp() {
        return timestamp;
    }

    public int getWidth() {
        return width;
    }

    public int getHeight() {
        return height;
    }
}
