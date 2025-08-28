# pip install https://github.com/glencoesoftware/zeroc-ice-py-macos-universal2/releases/download/20240131/zeroc_ice-3.6.5-cp310-cp310-macosx_11_0_universal2.whl
# pip install omero-py
# By default, you will have logged into your 'current' group in OMERO. This
# can be changed by switching group in the OMERO.insight or OMERO.web clients.
# 

import omero.clients
from omero.gateway import BlitzGateway
from omero.rtypes import rstring  # Import rstring for setting string values

HOST = "100.111.214.77"
PORT = 4064
USERNAME = "root"
PASSWORD = "omero"

client = omero.client(HOST, PORT)
session = client.createSession(USERNAME, PASSWORD)
conn = BlitzGateway(client_obj=client)

user = conn.getUser()
print("Current user:")
print("   ID:", user.getId())
print("   Username:", user.getName())
print("   Full Name:", user.getFullName())

# Check if you are an Administrator
print("   Is Admin:", conn.isAdmin())
if not conn.isFullAdmin():
    # If 'Restricted Administrator' show privileges
    print(conn.getCurrentAdminPrivileges())

print("Member of:")
for g in conn.getGroupsMemberOf():
    print("   ID:", g.getName(), " Name:", g.getId())
group = conn.getGroupFromContext()
print("Current group: ", group.getName())

# List the group owners and other members
owners, members = group.groupSummary()
print("   Group owners:")
for o in owners:
    print("     ID: %s %s Name: %s" % (
        o.getId(), o.getOmeName(), o.getFullName()))
print("   Group members:")
for m in members:
    print("     ID: %s %s Name: %s" % (
        m.getId(), m.getOmeName(), m.getFullName()))

print("Owner of:")
for g in conn.listOwnedGroups():
    print("   ID: ", g.getName(), " Name:", g.getId())

# Added in OMERO 5.0
print("Admins:")
for exp in conn.getAdministrators():
    print("   ID: %s %s Name: %s" % (
        exp.getId(), exp.getOmeName(), exp.getFullName()))

# The 'context' of our current session
ctx = conn.getEventContext()
# print(ctx)     # for more info


from omero.gateway import DatasetWrapper
# Use omero.gateway.DatasetWrapper:
new_dataset = DatasetWrapper(conn, omero.model.DatasetI())
new_dataset.setName('Scipy_Gaussian_Filter')
new_dataset.save()
print("New dataset, Id:", new_dataset.id)
# Can get the underlying omero.model.DatasetI with:
dataset_obj = new_dataset._obj

# OR create the DatasetI directly:
dataset_obj = omero.model.DatasetI()
dataset_obj.setName(rstring("New Dataset"))
dataset_obj = conn.getUpdateService().saveAndReturnObject(dataset_obj, conn.SERVICE_OPTS)
dataset_id = dataset_obj.getId().getValue()
print("New dataset, Id:", dataset_id)



from numpy import array, int8
import omero
size_x, size_y, size_z, size_c, size_t = 5, 4, 1, 2, 1
plane1 = array(
    [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [0, 1, 2, 3, 4], [5, 6, 7, 8, 9]],
    dtype=int8)
plane2 = array(
    [[5, 6, 7, 8, 9], [0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [0, 1, 2, 3, 4]],
    dtype=int8)
planes = [plane1, plane2]


def plane_gen():
    """generator will yield planes"""
    for p in planes:
        yield p
        
# https://forum.image.sc/t/how-to-write-tiles-from-large-numpy-image-to-omero/79756/6
desc = "Image created from a hard-coded arrays"
i = conn.createImageFromNumpySeq(
    plane_gen(), "numpy image", size_z, size_c, size_t, description=desc,
    dataset=None)
print('Created new Image:%s Name:"%s"' % (i.getId(), i.getName()))


# ========== ADDITIONAL EXAMPLE: Create Dataset and Image with Metadata ==========

from numpy import array, int8
from omero.model import MapAnnotationI, NamedValue
import omero

# Create a new dataset called "StageScan"
stage_scan_dataset = omero.model.DatasetI()
stage_scan_dataset.setName(rstring("StageScan"))
stage_scan_dataset.setDescription(rstring("Dataset containing stage scan images with metadata"))
stage_scan_dataset = conn.getUpdateService().saveAndReturnObject(stage_scan_dataset, conn.SERVICE_OPTS)
print(f"Created dataset 'StageScan' with ID: {stage_scan_dataset.getId().getValue()}")

# Create sample image data
size_x, size_y, size_z, size_c, size_t = 5, 4, 1, 2, 1
plane1 = array(
    [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [0, 1, 2, 3, 4], [5, 6, 7, 8, 9]],
    dtype=int8)
plane2 = array(
    [[5, 6, 7, 8, 9], [0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [0, 1, 2, 3, 4]],
    dtype=int8)
planes = [plane1, plane2]

def plane_gen():
    """generator will yield planes"""
    for p in planes:
        yield p

# Create image in the StageScan dataset
desc = "Image created from a hard-coded arrays with stage scan metadata"
i = conn.createImageFromNumpySeq(
    plane_gen(), "Stage Scan Image", size_z, size_c, size_t, description=desc,
    dataset=stage_scan_dataset)
print('Created new Image:%s Name:"%s"' % (i.getId(), i.getName()))

# Add metadata annotations to the image
metadata_annotation = MapAnnotationI()
metadata_annotation.setNs(rstring("imswitch.stage.scan"))

# Define metadata key-value pairs
metadata_values = [
    NamedValue("scan_type", "stage_scan"),
    NamedValue("stage_x_start", "0.0"),
    NamedValue("stage_y_start", "0.0"),
    NamedValue("stage_x_end", "100.0"),
    NamedValue("stage_y_end", "80.0"),
    NamedValue("step_size_um", "10.0"),
    NamedValue("pixel_size_um", "0.65"),
    NamedValue("acquisition_date", "2025-08-27"),
    NamedValue("microscope", "ImSwitch_System"),
    NamedValue("objective", "10x/0.3"),
    NamedValue("illumination", "LED_array"),
    NamedValue("exposure_time_ms", "50")
]

metadata_annotation.setMapValue(metadata_values)
metadata_annotation = conn.getUpdateService().saveAndReturnObject(
    metadata_annotation, conn.SERVICE_OPTS)

# Reload the image to get the latest version and avoid OptimisticLockException
image_id = i.getId()
fresh_image = conn.getObject("Image", image_id)

# Link metadata to the image using direct model objects
from omero.model import ImageAnnotationLinkI
link = ImageAnnotationLinkI()
link.setParent(fresh_image._obj)  # Fresh Image object
link.setChild(metadata_annotation)  # MapAnnotation object
conn.getUpdateService().saveObject(link, conn.SERVICE_OPTS)
print("Added metadata annotation to image")

# Optionally, also add a simple text annotation
from omero.model import CommentAnnotationI
comment = CommentAnnotationI()
comment.setTextValue(rstring("This image was acquired during an automated stage scan using ImSwitch"))
comment = conn.getUpdateService().saveAndReturnObject(comment, conn.SERVICE_OPTS)

# Link comment to the image (reload image again to be safe)
fresh_image = conn.getObject("Image", image_id)
comment_link = ImageAnnotationLinkI()
comment_link.setParent(fresh_image._obj)  # Fresh Image object
comment_link.setChild(comment)  # CommentAnnotation object
conn.getUpdateService().saveObject(comment_link, conn.SERVICE_OPTS)
print("Added comment annotation to image")

print(f"Stage scan setup complete! Dataset ID: {stage_scan_dataset.getId().getValue()}, Image ID: {i.getId()}")