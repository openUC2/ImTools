#!/usr/bin/env python3

import time
import numpy as np
import dask.array as da
import zarr
import ome_zarr.writer as ozw
from ome_zarr.io import parse_url

def simulate_stage_move(posX, posY):
    time.sleep(0.1)
    print(f"Stage moved to X={posX}, Y={posY}")

def simulate_camera_acquisition(wavelength):
    print(f"Acquiring frame at wavelength {wavelength} nm...")
    time.sleep(0.05)
    frame = np.random.randint(0, 65535, (512, 512), dtype=np.uint16)
    return frame

def main():
    wavelengths = [405, 488]
    zarr_path = "my_experiment.ome.zarr"
    ome_store = parse_url(zarr_path, mode="w").store
    root = zarr.group(store=ome_store)

    tile_index = 0
    for i in range(3):       # row
        for j in range(3):   # column
            posX = i * 10000.0
            posY = j * 10000.0
            simulate_stage_move(posX, posY)

            for w in wavelengths:
                frame = simulate_camera_acquisition(w)

                # shape => (t=1, c=1, z=1, y, x)
                arr_5d = da.from_array(frame[None, None, None, :, :])

                tile_id = f"tile_{i}_{j}_lambda_{w}"
                grp = root.create_group(tile_id, overwrite=True)

                # Must include at least one "scale" transform:
                coord_tf = [
                    [
                        {"type": "scale", "scale": [1, 1, 1, 1, 1]},
                        {"type": "translation", "translation": [0, 0, 0, posY, posX]}
                    ]
                ]

                ozw.write_image(
                    image=arr_5d,
                    group=grp,
                    scaler=None,  # single-scale only
                    axes=["t", "c", "z", "y", "x"],
                    coordinate_transformations=coord_tf,
                    channel_names=[f"{w}nm"],
                )

                grp.attrs.update({
                    "stage_position_um": [posX, posY],
                    "simulated_wavelength_nm": w,
                })

                tile_index += 1

    print(f"Done. OME-Zarr data written to: {zarr_path}")

if __name__ == "__main__":
    main()
