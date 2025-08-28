import numpy as np
from omero.gateway import BlitzGateway
from omero.rtypes import rstring

HOST, PORT, USERNAME, PASSWORD = "100.111.214.77", 4064, "root", "omero"

NX, NY = 5, 4
TY, TX = 256, 256                   # tile size
BIG_Y, BIG_X = NY*TY, NX*TX         # stitched size
UM_PER_PX = 0.65

def acquire_tile(ix, iy):
    rng = np.random.default_rng(ix + 1000*iy)
    img = rng.random((TY, TX), dtype=np.float32)
    return (img * 65535).astype(np.uint16)

conn = BlitzGateway(USERNAME, PASSWORD, host=HOST, port=PORT, secure=True); conn.connect()

# 1) Pre-create empty target image (1Z,1C,1T) of full stitched size
img = conn.createImageFromNumpySeq(
    [np.zeros((BIG_Y, BIG_X), dtype=np.uint16)],  # one blank plane
    BIG_X, BIG_Y, 1, 1, 1,
    #description="Live-stitched stream",
    pixelType="uint16"
)
pix = img.getPrimaryPixels()
pix.setPhysicalSizeX(UM_PER_PX); pix.setPhysicalSizeY(UM_PER_PX)

# 2) Open a RawPixelsStore to write tiles into regions
raw = conn.c.sf.createRawPixelsStore()
raw.setPixelsId(pix.getId().val, True)

# helper to write a tile at (ix,iy) into stitched image
def write_tile(ix, iy, tile):
    # region in the stitched plane
    x0, y0 = ix*TX, iy*TY
    w, h = TX, TY
    # OMERO expects bytes in row-major order; ensure C-contiguous
    buf = memoryview(tile)  # zero-copy view over uint16 array
    # Some deployments expose setRegion(x, y, w, h, z, c, t, bytes)
    raw.setRegion(x0, y0, w, h, 0, 0, 0, buf)     # write subregion of plane Z=0,C=0,T=0

# 3) Stream tiles directly into the single plane
for iy in range(NY):
    for ix in range(NX):
        frame = acquire_tile(ix, iy)
        write_tile(ix, iy, frame)

raw.close()
conn.close()
