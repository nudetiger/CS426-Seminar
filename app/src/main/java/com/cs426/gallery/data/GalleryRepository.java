package com.cs426.gallery.data;

import android.content.Context;

import com.cs426.gallery.BuildConfig;

import java.io.IOException;
import java.util.Collections;
import java.util.List;

/**
 * Loads the selected dataset (BuildConfig.GALLERY_DATASET) and returns ordered metadata.
 * Holds no Activity or View references.
 */
public class GalleryRepository {

    private final Context appContext;
    private final DatasetManifestReader manifestReader;

    public GalleryRepository(Context context) {
        this.appContext = context.getApplicationContext();
        this.manifestReader = new DatasetManifestReader();
    }

    public String getSelectedDatasetName() {
        return BuildConfig.GALLERY_DATASET;
    }

    /**
     * Returns images oldest-first from {@code assets/datasets/<name>/manifest.json}.
     * Image files live under {@code assets/datasets/.../images/}.
     */
    public List<GalleryImage> loadImages() throws IOException {
        String dataset = getSelectedDatasetName();
        String assetManifestPath = "datasets/" + dataset + "/manifest.json";
        List<GalleryImage> images = manifestReader.readFromAssets(appContext, assetManifestPath);
        return Collections.unmodifiableList(images);
    }

    /** Asset path for the original image file within the selected dataset. */
    public String getImageAssetPath(GalleryImage image) {
        return "datasets/" + getSelectedDatasetName() + "/images/" + image.getFilename();
    }
}
