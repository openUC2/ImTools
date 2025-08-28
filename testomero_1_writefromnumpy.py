import argparse
import sys
import tempfile
import numpy as np
import zarr
import os

from ome_zarr.io import parse_url
from ome_zarr.writer import write_image

import locale
import platform

from omero.cli import cli_login, CLI
from omero.gateway import BlitzGateway
import omero.clients
from omero.cli import cli_login
from omero.model import ChecksumAlgorithmI
from omero.model import NamedValue
from omero.model.enums import ChecksumAlgorithmSHA1160
from omero.rtypes import rstring, rbool
from omero_version import omero_version
from omero.callbacks import CmdCallbackI


def create_data(shape):
    mean_val=10
    rng = np.random.default_rng(0)
    return rng.poisson(mean_val, size=shape).astype(np.uint8)


def get_files_for_fileset(fs_path):
    filepaths = []
    for path, subdirs, files in os.walk(fs_path):
        for name in files:
            print(os.path.join(path, name))
            filepaths.append(os.path.join(path, name))
    return filepaths


def create_image_from_tiles(conn, numpy_image, tile_size, axes, dataset_id=None):
    """Create an OMERO image from a numpy array using tiles.

    Parameters
    ----------
    conn : BlitzGateway
        connection to OMERO
    numpy_image : numpy.ndarray
        the processed numpy large image
    tile_size : int
        the tile size
    dataset_id : int
        Dataset to add the Image to
    """    

    with tempfile.TemporaryDirectory() as tmpdirname:
        print('created temporary directory', tmpdirname)

        # create a temp OME-Zarr image...
        name = "image.zarr"
        tmpdirname = os.path.join(tmpdirname, name)
        store = parse_url(tmpdirname, mode="w").store
        root = zarr.group(store=store)
        write_image(image=numpy_image, group=root, axes=axes, storage_options=dict(chunks=tile_size))

        rsp = full_import(conn.c, tmpdirname)

        if rsp:
            links = []
            for p in rsp.pixels:
                print ('Imported Image ID: %d' % p.image.id.val)
                if dataset_id is not None:
                    link = omero.model.DatasetImageLinkI()
                    link.parent = omero.model.DatasetI(dataset_id, False)
                    link.child = omero.model.ImageI(p.image.id.val, False)
                    links.append(link)
            conn.getUpdateService().saveArray(links, conn.SERVICE_OPTS)


def create_fileset(files):
    """Create a new Fileset from local files."""
    fileset = omero.model.FilesetI()
    for f in files:
        entry = omero.model.FilesetEntryI()
        entry.setClientPath(rstring(f))
        fileset.addFilesetEntry(entry)

    # Fill version info
    system, node, release, version, machine, processor = platform.uname()

    client_version_info = [
        NamedValue('omero.version', omero_version),
        NamedValue('os.name', system),
        NamedValue('os.version', release),
        NamedValue('os.architecture', machine)
    ]
    try:
        client_version_info.append(
            NamedValue('locale', locale.getdefaultlocale()[0]))
    except:
        pass

    upload = omero.model.UploadJobI()
    upload.setVersionInfo(client_version_info)
    fileset.linkJob(upload)
    return fileset


def create_settings():
    """Create ImportSettings and set some values."""
    settings = omero.grid.ImportSettings()
    settings.doThumbnails = rbool(True)
    settings.noStatsInfo = rbool(False)
    settings.userSpecifiedTarget = None
    settings.userSpecifiedName = None
    settings.userSpecifiedDescription = None
    settings.userSpecifiedAnnotationList = None
    settings.userSpecifiedPixels = None
    settings.checksumAlgorithm = ChecksumAlgorithmI()
    s = rstring(ChecksumAlgorithmSHA1160)
    settings.checksumAlgorithm.value = s
    return settings


def upload_files(proc, files, client):
    """Upload files to OMERO from local filesystem."""
    ret_val = []
    for i, fobj in enumerate(files):
        rfs = proc.getUploader(i)
        try:
            with open(fobj, 'rb') as f:
                print ('Uploading: %s' % fobj)
                offset = 0
                block = []
                rfs.write(block, offset, len(block))  # Touch
                while True:
                    block = f.read(1000 * 1000)
                    if not block:
                        break
                    rfs.write(block, offset, len(block))
                    offset += len(block)
                ret_val.append(client.sha1(fobj))
        finally:
            rfs.close()
    return ret_val


def assert_import(client, proc, files, wait):
    """Wait and check that we imported an image."""
    hashes = upload_files(proc, files, client)
    handle = proc.verifyUpload(hashes)
    cb = CmdCallbackI(client, handle)

    # https://github.com/openmicroscopy/openmicroscopy/blob/v5.4.9/components/blitz/src/ome/formats/importer/ImportLibrary.java#L631
    if wait == 0:
        cb.close(False)
        return None
    if wait < 0:
        while not cb.block(2000):
            sys.stdout.write('.')
            sys.stdout.flush()
        sys.stdout.write('\n')
    else:
        cb.loop(wait, 1000)
    rsp = cb.getResponse()
    if isinstance(rsp, omero.cmd.ERR):
        raise Exception(rsp)
    assert len(rsp.pixels) > 0
    return rsp


def full_import(client, fs_path, wait=-1):
    """Re-usable method for a basic import."""
    mrepo = client.getManagedRepository()
    files = get_files_for_fileset(fs_path)
    assert files, 'No files found: %s' % fs_path

    fileset = create_fileset(files)
    settings = create_settings()

    proc = mrepo.importFileset(fileset, settings)
    try:
        return assert_import(client, proc, files, wait)
    finally:
        proc.close()


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('dataset_id', type=int, help="Dataset ID to add Image")
    args = parser.parse_args(argv)

    with cli_login() as cli:
        conn = BlitzGateway(client_obj=cli._client)
        dataset_id = args.dataset_id

        shape = (2, 1024, 1024)
        numpy_image = create_data(shape)
        tile_size = (1, 256, 256)
        axes = "cyx"
        create_image_from_tiles(conn, numpy_image, tile_size, axes, dataset_id)


if __name__ == '__main__':
    main(sys.argv[1:])


# ========== ADDITIONAL EXAMPLE: Create Dataset and Image with Metadata ==========

def create_stage_scan_with_metadata():
    """Create a StageScan dataset with image and metadata annotations."""
    
    # Connect to OMERO
    from omero.gateway import BlitzGateway
    HOST = "100.111.214.77"
    PORT = 4064
    USERNAME = "root"
    PASSWORD = "omero"
    
    conn = BlitzGateway(USERNAME, PASSWORD, host=HOST, port=PORT, secure=True)
    
    try:
        conn.connect()
        
        from numpy import array, int8
        from omero.model import MapAnnotationI, NamedValue, CommentAnnotationI
        import omero
        from omero.rtypes import rstring
        
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
        
        # Link metadata to the image
        i.linkAnnotation(metadata_annotation)
        print("Added metadata annotation to image")
        
        # Optionally, also add a simple text annotation
        comment = CommentAnnotationI()
        comment.setTextValue(rstring("This image was acquired during an automated stage scan using ImSwitch"))
        comment = conn.getUpdateService().saveAndReturnObject(comment, conn.SERVICE_OPTS)
        i.linkAnnotation(comment)
        print("Added comment annotation to image")
        
        print(f"Stage scan setup complete! Dataset ID: {stage_scan_dataset.getId().getValue()}, Image ID: {i.getId()}")
        
        return stage_scan_dataset.getId().getValue(), i.getId()
        
    finally:
        try:
            conn.close()
        except Exception:
            pass

# Uncomment the line below to run the example:
# create_stage_scan_with_metadata()