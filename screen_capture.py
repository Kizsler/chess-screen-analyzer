"""Screen capture module for grabbing the chess board region."""

import numpy as np
from PIL import Image, ImageGrab


class ScreenCapture:
    """Captures a specific region of the screen."""

    def __init__(self, region):
        """
        Initialize with a region dict.

        Args:
            region: dict with keys x, y, width, height
        """
        self.region = region
        self._last_image = None

    def capture(self):
        """
        Capture the screen region.

        Returns:
            numpy array of the captured image (RGB)
        """
        # Use PIL ImageGrab - more compatible with threading
        bbox = (
            self.region["x"],
            self.region["y"],
            self.region["x"] + self.region["width"],
            self.region["y"] + self.region["height"]
        )
        img = ImageGrab.grab(bbox=bbox)
        return np.array(img)

    def capture_if_changed(self, threshold=0.02):
        """
        Capture only if the image has changed significantly.

        Args:
            threshold: minimum difference ratio to consider changed

        Returns:
            tuple (image, changed) where changed is True if new capture differs
        """
        img = self.capture()

        if self._last_image is None:
            self._last_image = img.copy()
            return img, True

        # Quick comparison using downsampled images
        small_new = img[::8, ::8].astype(np.float32)
        small_old = self._last_image[::8, ::8].astype(np.float32)

        diff = np.abs(small_new - small_old).mean() / 255.0

        if diff > threshold:
            self._last_image = img.copy()
            return img, True

        return img, False

    def update_region(self, region):
        """Update the capture region."""
        self.region = region
        self._last_image = None

    def close(self):
        """Clean up resources."""
        pass  # No cleanup needed for PIL
