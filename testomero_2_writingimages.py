
import os, json, shutil, subprocess, tempfile, datetime as dt
import numpy as np
import tifffile as tiff

from omero.gateway import BlitzGateway
from omero.model import ProjectDatasetLinkI, MapAnnotationI, NamedValue, ProjectI, DatasetI
from omero.rtypes import rstring

# ---------- CONFIG ----------
HOST      = "100.111.214.77"
PORT      = 4064
USERNAME  = "root"
PASSWORD  = "omero"

PROJECT_NAME   = "ImSwitch XY Scans"
DATASET_PREFIX = "Run " + dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# scan grid (tiles)
NX, NY        = 5, 4             # tiles in X and Y
PIX_PER_TILE  = (256, 256)       # (Y, X)
UM_PER_PIXEL  = 0.65             # microns/px
STEP_TILES_UM = int(PIX_PER_TILE[1] * UM_PER_PIXEL)  # stage step between tiles (X); Y uses PIX_PER_TILE[0]

MAKE_OVERVIEW = True             # also write a stitched overview image and import it

# ---------- HELPERS ----------
def omero_cli(*args):
    cmd = ["omero", *args]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"OMERO CLI failed: {' '.join(cmd)}\n{res.stdout}")
    return res.stdout

def omero_cli_login():
    # you can store a session (omero sessions list) if you prefer; this keeps it simple
    return omero_cli("login", "-s", HOST, "-u", USERNAME, "-w", PASSWORD)

def omero_cli_import(path, dataset_id):
    out = omero_cli("import", "-d", str(dataset_id), path)
    # crude parse for created Image IDs
    new_ids = []
    for line in out.splitlines():
        # lines often look like: Created image:12345
        if "Created image:" in line:
            try:
                new_ids.append(int(line.strip().split("Created image:")[1]))
            except Exception:
                pass
    return new_ids

def make_fake_tile(yx_shape, seed=None):
    rng = np.random.default_rng(seed)
    y, x = yx_shape
    # simple synthetic pattern (gradient + blobs) – replace with camera frames
    base = np.linspace(0, 1, x, dtype=np.float32)[None, :].repeat(y, axis=0)
    noise = (rng.normal(0, 0.05, (y, x))).astype(np.float32)
    blob_y, blob_x = rng.integers(0, y), rng.integers(0, x)
    rr, cc = np.ogrid[:y, :x]
    blob = np.exp(-(((rr-blob_y)**2 + (cc-blob_x)**2) / (2*(min(y, x)/10)**2))).astype(np.float32)
    img = base + 0.7*blob + noise
    img = np.clip(img, 0, 1)
    # 16-bit
    return (img * 65535).astype(np.uint16)

def save_ome_tiff(path, data_uint16, posX_um, posY_um, um_per_px, series_name):
    """
    Save single-plane, single-channel OME-TIFF with Plane.PositionX/Y.
    """
    # OME-XML via tifffile: set physical pixel sizes + stage positions
    ome_metadata = {
        "Axes": "YX",
        "PhysicalSizeX": um_per_px,
        "PhysicalSizeXUnit": "µm",
        "PhysicalSizeY": um_per_px,
        "PhysicalSizeYUnit": "µm",
        # store per-plane positions (single plane => index 0)
        "Plane": [{"PositionX": float(posX_um), "PositionY": float(posY_um)}],
        "Name": series_name,
    }
    tiff.imwrite(
        path,
        data_uint16,
        photometric="minisblack",
        metadata={"axes": "YX"},
        description=tiff.OmeXml.OMEXML(**ome_metadata).to_xml(),  # precise OME-XML
        compression=None,
    )

def stitch_overview(all_tiles, tile_shape, nx, ny):
    """
    Assemble a single big array from tiles arranged row-major (Y outer, X inner).
    all_tiles: dict[(ix, iy)] -> np.ndarray
    """
    ty, tx = tile_shape
    big = np.zeros((ny*ty, nx*tx), dtype=np.uint16)
    for iy in range(ny):
        for ix in range(nx):
            tile = all_tiles[(ix, iy)]
            y0, x0 = iy*ty, ix*tx
            big[y0:y0+ty, x0:x0+tx] = tile
    return big

# ---------- MAIN ----------
def main():
    tmpdir = tempfile.mkdtemp(prefix="imswitch_xy_")
    try:
        # connect
        conn = BlitzGateway(USERNAME, PASSWORD, host=HOST, port=PORT, secure=True)
        assert conn.connect(), "OMERO login failed"

        # project + dataset
        update = conn.getUpdateService()
        # Create via model constructors (TypesService has no newProject/newDataset)
        proj = ProjectI()
        proj.setName(rstring(PROJECT_NAME))
        proj = update.saveAndReturnObject(proj)

        dset = DatasetI()
        dset.setName(rstring(DATASET_PREFIX))
        dset = update.saveAndReturnObject(dset)

        link = ProjectDatasetLinkI()
        link.setParent(proj); link.setChild(dset)
        update.saveObject(link)

        dataset_id = dset.id.val
        print(f"Dataset ID: {dataset_id}")

        # prepare tiles
        all_tiles = {}
        tile_paths = []
        for iy in range(NY):
            for ix in range(NX):
                tile = make_fake_tile(PIX_PER_TILE, seed=iy*1000+ix)
                all_tiles[(ix, iy)] = tile
                posX_um = ix * STEP_TILES_UM
                posY_um = iy * (PIX_PER_TILE[0] * UM_PER_PIXEL)

                fname = f"tile_x{ix:02d}_y{iy:02d}.ome.tiff"
                fpath = os.path.join(tmpdir, fname)
                save_ome_tiff(
                    fpath,
                    tile,
                    posX_um=posX_um,
                    posY_um=posY_um,
                    um_per_px=UM_PER_PIXEL,
                    series_name=f"Tile ({ix},{iy})",
                )
                tile_paths.append((fpath, ix, iy, posX_um, posY_um))

        # login & import tiles
        omero_cli_login()
        created_ids = []
        for (fpath, ix, iy, px, py) in tile_paths:
            ids = omero_cli_import(fpath, dataset_id)
            if not ids:
                raise RuntimeError(f"No Image ID returned for {os.path.basename(fpath)}")
            img_id = ids[-1]
            created_ids.append((img_id, ix, iy, px, py))

        # annotate images with tile indices (so clients can reconstruct layout)
        for (img_id, ix, iy, px, py) in created_ids:
            img = conn.getObject("Image", img_id)
            ma = MapAnnotationI()
            ma.setNs(rstring("omero.mapr.tile"))  # namespace
            pairs = [
                NamedValue("tile_x", str(ix)),
                NamedValue("tile_y", str(iy)),
                NamedValue("posX_um", f"{px:.3f}"),
                NamedValue("posY_um", f"{py:.3f}"),
                NamedValue("um_per_px", f"{UM_PER_PIXEL:.5f}"),
            ]
            ma.setMapValue(pairs)
            ma = update.saveAndReturnObject(ma)
            img.linkAnnotation(ma)

        print(f"Imported {len(created_ids)} tiles.")

        # optional: create and import stitched overview (guarantees a visible stitch in OMERO)
        if MAKE_OVERVIEW:
            big = stitch_overview(all_tiles, PIX_PER_TILE, NX, NY)
            overview_path = os.path.join(tmpdir, "stitched_overview.ome.tiff")
            # save with correct physical scale (single image, no plane positions necessary)
            ome_meta = {
                "Axes": "YX",
                "PhysicalSizeX": UM_PER_PIXEL,
                "PhysicalSizeXUnit": "µm",
                "PhysicalSizeY": UM_PER_PIXEL,
                "PhysicalSizeYUnit": "µm",
                "Name": "Stitched overview",
            }
            tiff.imwrite(
                overview_path,
                big,
                photometric="minisblack",
                metadata={"axes": "YX"},
                description=tiff.omexml.OMEXML(**ome_meta).to_xml(),
                compression=None,
            )
            omero_cli_login()
            ov_ids = omero_cli_import(overview_path, dataset_id)
            print(f"Overview Image IDs: {ov_ids}")

        print("Done.")

    finally:
        # Close OMERO connection cleanly to avoid Ice communicator warning
        try:
            if 'conn' in locals() and conn is not None:
                conn.close()
        except Exception:
            pass
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass

if __name__ == "__main__":
    main()