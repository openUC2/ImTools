#!/usr/bin/env python3

"""
Minimal example of writing images consecutively into an OME-TIFF on the fly
using tifffile, each with per-plane stage coordinates and pixel size.

**Workflow**:
1. We start a Stitcher in a background thread with a queue.
2. We can call stitcher.add_image(...) any time new images arrive from the camera.
3. The queue is processed in the background, writing each image to the OME-TIFF
   in append mode, embedding stage positions and pixel size in the metadata.
4. Fiji can open the resulting file and often interprets the "Plane" fields for mosaic.
   (You may need the "Stitching" or "Bio-Formats Importer" options in Fiji.)

Important notes:
- This approach relies on tifffile's per-plane "metadata" dictionary. It's not
  standard OME-XML, but Fiji often recognizes it.
- The file's final OME metadata is not truly combined into one block, so you may
  see warnings about "missing plane" or partial plane references in some OME
  tools. If you need a fully compliant single OME-XML block, you must do a
  single write pass or handle the offsets manually.
"""

import time
import threading
import numpy as np
import tifffile
from collections import deque

class OmeTiffStitcher:
    def __init__(self, file_path, bigtiff=True):
        """
        file_path: Where to write the OME-TIFF
        bigtiff:   Whether to use bigtiff=True (recommended if large or many images)
        """
        self.file_path = file_path
        self.bigtiff = bigtiff
        self.queue = deque()       # Holds (image_array, metadata_dict)
        self.lock = threading.Lock()
        self.is_running = False
        self._thread = None

    def start(self):
        """Begin the background thread that writes images to disk as they arrive."""
        self.is_running = True
        self._thread = threading.Thread(target=self._process_queue, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the thread to stop, then join it."""
        self.is_running = False
        if self._thread is not None:
            self._thread.join()

    def add_image(self, image, position_x, position_y, index_x, index_y, pixel_size):
        """
        Enqueue an image for writing.
        :param image: 2D or 3D NumPy array (e.g. grayscale or color).
        :param position_x: stage X coordinate in microns
        :param position_y: stage Y coordinate in microns
        :param index_x:   tile index X (used for some readers)
        :param index_y:   tile index Y
        :param pixel_size: pixel size in microns
        """
        # A minimal OME-like metadata block that Fiji can often interpret.
        # The "Plane" section stores stage position; "Pixels" sets physical pixel size.
        metadata = {
            "Pixels": {
                "PhysicalSizeX": pixel_size,
                "PhysicalSizeXUnit": "µm",
                "PhysicalSizeY": pixel_size,
                "PhysicalSizeYUnit": "µm",
            },
            "Plane": {
                "PositionX": position_x,
                "PositionY": position_y,
                "IndexX": index_x,
                "IndexY": index_y
            },
        }
        with self.lock:
            self.queue.append((image, metadata))

    def _process_queue(self):
        """
        Background loop: open the OME-TIFF in append mode, pop images from queue,
        and write them with embedded metadata.
        """
        with tifffile.TiffWriter(self.file_path, bigtiff=self.bigtiff, append=True) as tif:
            # Keep running until stop() is called AND the queue is empty
            while self.is_running or len(self.queue) > 0:
                with self.lock:
                    if self.queue:
                        image, metadata = self.queue.popleft()
                    else:
                        image = None

                if image is not None:
                    # Each call writes a new series/plane in append mode.
                    tif.write(data=image, metadata=metadata)

                time.sleep(0.01)  # Sleep briefly to reduce CPU usage

    def close(self):
        """Close the OME-TIFF file. Not strictly necessary if using stop()."""
        self.stop()
        if self._thread is not None:
            self._thread.join()
            self._thread = None
        self.is_running = False
        self.queue.clear()
        self.lock = None
        self._thread = None
        self.queue = None
        self.file_path = None

def main():
    """
    Standalone demonstration:
      - We'll generate 6 random images for a 2x3 mosaic (each 200x200).
      - We store them with "PositionX/Y" so Fiji can attempt to mosaic them.
    """
    stitcher = OmeTiffStitcher("example_stitch.ome.tiff")
    stitcher.start()

    # Example tile layout: 2 rows x 3 cols, each 200x200 grayscale
    rows, cols = 20, 30
    tile_height, tile_width = 200, 200
    pixel_size = 1.0  # 1 micron per pixel

    # Minimal loop simulating images arriving from a camera
    for r in range(rows):
        for c in range(cols):
            # Create a random 2D image (grayscale)
            img = np.random.randint(
                0, 255, (tile_height, tile_width), dtype=np.uint8
            )

            # Suppose each tile is offset by tile_width * pixel_size
            position_x = c * tile_width * pixel_size
            position_y = r * tile_height * pixel_size

            stitcher.add_image(
                image=img,
                position_x=position_x,
                position_y=position_y,
                index_x=c,
                index_y=r,
                pixel_size=pixel_size
            )

    # Wait a moment for the background to flush all images
    time.sleep(1.0)

    stitcher.stop()
    print("All images appended into example_stitch.ome.tiff.\n"
          "Open in Fiji → Bio-Formats Importer. You may see partial-plane warnings,\n"
          "but you can attempt 'stitch tiles' by stage position if Fiji offers it.")


if __name__ == "__main__":
    main()
