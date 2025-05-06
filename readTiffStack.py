import tifffile as tiff
import numpy as np


# Funktion zum Einlesen des TIFF-Stapels
def read_tiff_stack(file_path):
    with tiff.TiffFile(file_path) as tif:
        images = [page.asarray() for page in tif.pages]
    return images

# Beispielverwendung
file_path = '/Users/bene/Dropbox/Dokumente/Promotion/PROJECTS/MicronController/ImSwitch/timelapse.tif'

# TIFF-Stapel wieder einlesen
read_images = read_tiff_stack(file_path)
print(f"Anzahl der eingelesenen Bilder: {len(read_images)}")