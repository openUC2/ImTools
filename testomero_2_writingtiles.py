import numpy as np
from omero.gateway import BlitzGateway
from omero.model import ProjectDatasetLinkI, MapAnnotationI, NamedValue
from omero.rtypes import rstring

HOST, PORT, USERNAME, PASSWORD = "100.111.214.77", 4064, "root", "omero"

NX, NY = 5, 4
Y, X = 256, 256
UM_PER_PX = 0.65
STEP_X_UM = X * UM_PER_PX
STEP_Y_UM = Y * UM_PER_PX

def acquire_tile(ix, iy):
    # replace with real camera frame
    rng = np.random.default_rng(ix + 1000*iy)
    img = rng.random((Y, X), dtype=np.float32)
    return (img * 65535).astype(np.uint16)  # 1×Y×X, uint16

conn = BlitzGateway(USERNAME, PASSWORD, host=HOST, port=PORT, secure=True); conn.connect()

types = conn.getTypesService(); update = conn.getUpdateService()
proj = types.newProject(); proj.setName(rstring("ImSwitch XY Streams")); proj = update.saveAndReturnObject(proj)
dset = types.newDataset(); dset.setName(rstring("Live Run")); dset = update.saveAndReturnObject(dset)
link = ProjectDatasetLinkI(); link.setParent(proj); link.setChild(dset); update.saveObject(link)

for iy in range(NY):
    for ix in range(NX):
        frame = acquire_tile(ix, iy)

        # create the OMERO Image directly from a NumPy sequence (no disk I/O)
        img = conn.createImageFromNumpySeq(
            [frame],             # sequence of planes (ZCT order); here 1 plane
            X, Y,                # sizeX, sizeY
            1, 1, 1,             # sizeZ, sizeC, sizeT
            description=f"Tile ({ix},{iy}) streamed",
            dataset=dset,
            pixelType="uint16",
            channelList=None
        )

        # set physical pixel size (µm)
        pix = img.getPrimaryPixels()
        pix.setPhysicalSizeX(UM_PER_PX); pix.setPhysicalSizeY(UM_PER_PX)

        # annotate tile positions so downstream stitching knows where to place it
        ma = MapAnnotationI()
        ma.setNs(rstring("omero.mapr.tile"))
        px_um = ix * STEP_X_UM
        py_um = iy * STEP_Y_UM
        ma.setMapValue([
            NamedValue("tile_x", str(ix)),
            NamedValue("tile_y", str(iy)),
            NamedValue("posX_um", f"{px_um:.3f}"),
            NamedValue("posY_um", f"{py_um:.3f}"),
            NamedValue("um_per_px", f"{UM_PER_PX:.5f}")
        ])
        ma = update.saveAndReturnObject(ma)
        img.linkAnnotation(ma)

conn.close()
