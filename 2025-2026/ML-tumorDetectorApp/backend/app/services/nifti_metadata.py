from pathlib import Path
import nibabel as nib
from nibabel.orientations import aff2axcodes
import numpy as np

def validate_tumor_presence(image_path : Path | str) -> bool:
    nifti = nib.load(str(image_path))
    data = np.asanyarray(nifti.dataobj)
    return bool(np.any(data>0))

def extract_metadata(image_path: Path | str) -> dict:
    img = nib.load(str(image_path))
    shape = [int(x) for x in img.shape]
    zooms = img.header.get_zooms()
    spacing = [float(z) for z in zooms[:len(shape)]]
    return {
        "shape": shape,
        "spacing": spacing,
        "affine": img.affine.tolist(),
        "orientation": "".join(aff2axcodes(img.affine)),
        "dtype": str(img.get_data_dtype()),
    }