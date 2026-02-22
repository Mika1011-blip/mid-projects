from collections import Counter
from pathlib import Path
from typing import Any, Tuple
import re

import nibabel as nib
import numpy as np
from nibabel.processing import resample_to_output, resample_from_to

_MODALITY_NAMES = ("T1CE", "FLAIR", "T1", "T2", "SEG")
_MODALITY_PATTERNS = {
    name: re.compile(rf"(?<![A-Z0-9]){name}(?![A-Z0-9])", re.IGNORECASE)
    for name in _MODALITY_NAMES
}
_SEG_LIKE_PATTERN = re.compile(r"(?<![A-Z0-9])(SEG|USER|MODEL)(?![A-Z0-9])", re.IGNORECASE)

ModalityMap = dict[str, nib.Nifti1Image]
Shape3D = tuple[int, int, int]
Spacing3D = tuple[float, float, float]
CropSlices3D = tuple[slice, slice, slice]


def _filename_has_modality(filename: str, modality: str) -> bool:
    pattern = _MODALITY_PATTERNS.get(modality.upper())
    if pattern is None:
        return False
    return pattern.search(filename or "") is not None


def _extract_modality_token(filename: str) -> str | None:
    for modality in _MODALITY_NAMES:
        if _filename_has_modality(filename, modality):
            return modality
    return None


def _is_seg_filename(filename: str) -> bool:
    return _SEG_LIKE_PATTERN.search(filename or "") is not None


def _summarize_modalities(modalities: dict[str, nib.Nifti1Image | None]) -> dict[str, Any]:
    files = {}
    for fname, image in modalities.items():
        spacing = tuple(float(v) for v in image.header.get_zooms()[:3]) if image is not None else ()
        shape = tuple(int(v) for v in image.shape[:3]) if image is not None else ()
        files[fname] = {
            "modality": _extract_modality_token(fname),
            "is_seg": _is_seg_filename(fname),
            "shape": shape,
            "spacing": spacing,
            "dtype": str(image.get_data_dtype()) if image is not None else None,
        }
    return {
        "count": len(files),
        "files": files,
    }


def _summarize_array(arr: np.ndarray | None) -> dict[str, Any] | None:
    if arr is None:
        return None
    return {
        "shape": tuple(int(v) for v in arr.shape),
        "dtype": str(arr.dtype),
    }


def list_files(path : Path) -> list[Path]:
    return [p for p in path.iterdir() if p.is_file()]
def load_nifti(path : Path) -> tuple[nib.Nifti1Image, np.ndarray]:
    """
    nii: has header + affine (metadata)
    data: the actual 3D array
    """
    nii = nib.load(str(path))
    data = nii.get_fdata(dtype=np.float32)
    return nii, data
def inspect_volume(name: str, nii: nib.Nifti1Image) -> None:
    data = nii.get_fdata(dtype=np.float32)
    spacing = nii.header.get_zooms()[:3]   # (sx, sy, sz) in mm
    print(f"\n[{name}]")
    print("  shape:", data.shape)
    print("  spacing(mm):", spacing)
    print("  dtype:", data.dtype)
    """
    min/max -> smallest and largest voxel value in the volume
    why do we care ?
    Detect background convention
    - Many MRIs use 0 as background. Some use -1024, some use tiny noise.
    Catch broken scaling
    - If you expect MRI-like values and see min=-3e9, something is wrong.
    Differentiate image vs mask
    - Image: wide range (hundreds or thousands)
    - Mask: tiny discrete range (e.g. {0,1,2,3})

    Example
        min=0, max=2069 → looks like MRI intensity
        min=0, max=3 → almost certainly a segmentation mask
    """
    print("  min/max:", float(np.min(data)), float(np.max(data)))
    """
    mean / std
    What it is
        Average intensity and spread of intensities.
    
    Why you care
        This tells you about intensity distribution, which matters a lot in MRI.
        
    You use it to:
        Detect dataset shift between sources
        Decide normalization strategy
        Catch volumes that are:
            mostly empty
            saturated
            badly preprocessed
    
    Subtle but important
        MRI intensities are not standardized.
        So:
            Different scanners → different mean/std     
            Different sequences → wildly different stats
            
            That’s exactly why you inspect them.
    
    Example
        Dataset A: mean=80, std=180
        Dataset B: mean=400, std=900
            → if you don’t normalize, your model learns scanner identity instead of tumors.
    Do you need it?
        Yes to design preprocessing
        No to log every batch forever
    """
    print("  mean/std:", float(np.mean(data)), float(np.std(data)))
    print("  unique (mask-ish check):", np.unique(data)[:10])
class Patient:
    def __init__(self, patient_id: str, images: ModalityMap):
        self.id: str = patient_id
        self.images: ModalityMap = images

    def get_modalities(self) -> list[str]:
        return list(self.images.keys())

    def get_image(self, modality: str) -> nib.Nifti1Image | None:
        return self.images.get(modality)
    
def load_patients(p_path : Path, sample_percentage : float = 1.0) -> list[Patient]:
    #collect folder only
    patients_folder = [f for f in p_path.iterdir() if f.is_dir()]
    total = len(patients_folder)
    if total == 0 :
        return []
    #validate and get sample size
    if sample_percentage is None :
        sample_percentage = 1.0
    if not(0 < sample_percentage <= 1) :
        raise ValueError("sample_percentage must be in (0, 1].")
    sample_size = max(1,int(sample_percentage*total)) if sample_percentage < 1 else total

    #get patients
    patients = []
    for folder in patients_folder[:sample_size]:
        files = list_files(folder)
        dict_files = {}
        for file in files :
            try :
                dict_files[file.name] = nib.load(str(file))
            except :
                #skip file that's not .nii (nifti)
                continue
        patients.append(Patient(folder.name,dict_files))
    return patients
def get_img_by_type(images: ModalityMap, typeImg: str) -> tuple[str, nib.Nifti1Image]:
    modality = (typeImg or "").strip().upper()
    if modality not in _MODALITY_NAMES:
        raise ValueError(f"Unsupported modality type: {typeImg}")

    files = [(fname, image) for fname, image in images.items() if _filename_has_modality(fname, modality)]
    if len(files) == 1:
        return files[0]
    if len(files) > 1:
        raise ValueError(f"Multiple {modality}")
    raise ValueError(f"Missing {modality}")
    
def canonicalize_volume(
    image: nib.Nifti1Image,
    order: int = 1, #1 for image, 0 for mask (segmentation)
    template_ref: nib.Nifti1Image | None = None,
) -> nib.Nifti1Image:
    """
    1) Reorient to closest canonical (RAS-like) using affine
    2) Resample either:
       - onto a reference grid (sample_ref) using resample_from_to, or
       - to a global voxel spacing (1,1,1) using resample_to_output

    order: interpolation order
      - 1 for images (linear)
      - 0 for masks (nearest)
    """
    out = nib.as_closest_canonical(image)

    if template_ref is not None:
        ref = nib.as_closest_canonical(template_ref)
        out = resample_from_to(out, ref, order=order)
    else:
        out = resample_to_output(out, voxel_sizes=(1.0, 1.0, 1.0), order=order)

    return out

def extract_metadata(
    image: nib.Nifti1Image,
    canonical: bool = True,
    expect_axcodes: tuple[str, str, str] = ("R", "A", "S"),
    affine_mismatch_tol: float = 1e-3,
) -> dict[str, Any]:
    """
    Inspection helper:
    - Extract metadata (shape/spacing/fov/affine/origin)
    - Emit warnings if header/world-xform looks suspicious
    - Does NOT raise exceptions (inspection only)
    """

    report = {"warnings": [], "ok": True}
    img = image

    # 1) Basic header codes BEFORE canonical (useful diagnostic)
    qcode0 = int(img.header['qform_code'])
    scode0 = int(img.header['sform_code'])
    ax0 = nib.aff2axcodes(img.affine)

    if qcode0 == 0 and scode0 == 0:
        report["warnings"].append("NO_WORLD_XFORM: qform_code=0 and sform_code=0 (world mapping may be unreliable)")
        report["ok"] = False

    # 2) Optional: check qform vs sform disagreement (only if both exist)
    # (This is a warning, not a failure by itself.)
    if qcode0 > 0 and scode0 > 0:
        qaff = img.get_qform()
        saff = img.get_sform()
        if qaff is not None and saff is not None:
            diff = np.linalg.norm(qaff - saff)
            if diff > affine_mismatch_tol:
                report["warnings"].append(f"QFORM_SFORM_MISMATCH: ||qform-sform||={diff:.4g} (may indicate inconsistent headers)")

    # 3) Canonicalize if requested
    if canonical:
        img_can = nib.as_closest_canonical(img)
    else:
        img_can = img

    shape = img_can.shape[:3]
    spacing = img_can.header.get_zooms()[:3]
    affine = img_can.affine
    origin = affine[:3, 3]
    ax1 = nib.aff2axcodes(affine)
    fov_mm = (np.array(shape, dtype=np.float32) * np.array(spacing, dtype=np.float32)).tolist()

    # 4) After canonical checks
    if canonical and (ax1 != expect_axcodes):
        report["warnings"].append(f"AXCODES_AFTER_CANONICAL_UNEXPECTED: {ax1} (expected {expect_axcodes})")
        # not necessarily fatal, but suspicious
        report["ok"] = False

    # 5) Basic sanity checks
    if any(s <= 0 for s in spacing):
        report["warnings"].append(f"BAD_SPACING: spacing={spacing}")
        report["ok"] = False

    if any(d <= 0 for d in shape):
        report["warnings"].append(f"BAD_SHAPE: shape={shape}")
        report["ok"] = False

    # Pack results
    report.update({
        "shape": tuple(shape),
        "spacing": tuple(spacing),
        "fov_mm": tuple(fov_mm),
        "axcodes_before": ax0,
        "axcodes_after": ax1,
        "origin_mm": tuple(origin.tolist()),
        "affine": affine,
        "qform_code_before": qcode0,
        "sform_code_before": scode0,
    })

    return report

def compute_spatial_targets(patients : list[Patient]) -> dict[str, Any]:
    def get_spacingMode(values: list[Spacing3D], step: float = 0.1) -> Spacing3D:
        q = [tuple(round(v/step)*step for v in t) for t in values]
        return Counter(q).most_common(1)[0][0]

    def get_fovMode(fovs_mm: list[Spacing3D], step: float = 5.0) -> Shape3D:
        q = [tuple(int(round(v/step)*step) for v in f) for f in fovs_mm]
        return Counter(q).most_common(1)[0][0]

    def percentile_triplets(values: list[Spacing3D], p: float = 90) -> Spacing3D:
        arr = np.array(values, dtype=np.float32)   # shape (N,3)
        return tuple(np.percentile(arr, p, axis=0).tolist())

    def shape_from_fov_and_spacing(fov_mm: Spacing3D, spacing_mm: Spacing3D) -> Shape3D:
        fov = np.array(fov_mm, dtype=np.float32)
        sp  = np.array(spacing_mm, dtype=np.float32)
        shape = np.ceil(fov / sp).astype(int)
        return tuple(shape.tolist())

    def get_originTarget(spacing: Spacing3D, shape: Shape3D) -> Spacing3D:
        spacing = np.array(spacing,dtype=np.float32)
        shape = np.array(shape,dtype=np.float32)
        return tuple((-0.5 * spacing * shape).tolist())#require further explaination on this calculation
    list_spacings: list[Spacing3D] = []
    list_fovs: list[Spacing3D] = []
    seg_fallback_spacings: list[Spacing3D] = []
    seg_fallback_fovs: list[Spacing3D] = []
    origin_target = None
    for patient in patients :
        for fname, image in patient.images.items():
            metadata = extract_metadata(image=image)
            if not _is_seg_filename(fname):
                list_spacings.append(metadata["spacing"])
                list_fovs.append(metadata["fov_mm"])
                if origin_target is None:
                    origin_target = metadata["origin_mm"]
            else:
                seg_fallback_spacings.append(metadata["spacing"])
                seg_fallback_fovs.append(metadata["fov_mm"])
                if origin_target is None:
                    origin_target = metadata["origin_mm"]
    if not list_spacings:
        list_spacings = seg_fallback_spacings
        list_fovs = seg_fallback_fovs
    if not list_spacings:
        raise ValueError("No valid NIfTI volumes found to compute spatial targets.")
    if origin_target is None:
        origin_target = (0.0, 0.0, 0.0)
    spacingMode = get_spacingMode(list_spacings)
    fovP90 = percentile_triplets(list_fovs, p=90)
    shape_target = shape_from_fov_and_spacing(fovP90, spacingMode)
    #origin_target = get_originTarget(spacing=spacingMode, shape = shape_target)
    assert all(s > 0 for s in spacingMode), "Bad spacing target"
    assert all(n > 0 for n in shape_target), "Bad shape target"
    return {
        "spacing_target" : spacingMode,
        "fov_target" : fovP90,
        "shape_target" : shape_target,
        "origin_target" : origin_target
    }

def get_globalSpatialTemplate(patients : list[Patient]) -> nib.Nifti1Image:
    spatialTargets = compute_spatial_targets(patients = patients)
    def make_affineRasTemplate(
        spacing_target: Spacing3D,
        origin_mm: Spacing3D = (0.0, 0.0, 0.0),
    ) -> np.ndarray:
        affine = np.eye(4,dtype=np.float32)
        affine[0,0] = spacing_target[0]
        affine[1,1] = spacing_target[1]
        affine[2,2] = spacing_target[2]
        affine[:3,3] = np.array(origin_mm,dtype=np.float32)
        return affine
    affine = make_affineRasTemplate(spacing_target = spatialTargets["spacing_target"],
                                   origin_mm = spatialTargets["origin_target"])
    data = np.zeros(spatialTargets["shape_target"], dtype=np.uint8)
    template_ref = nib.Nifti1Image(data,affine)
    return template_ref

def zscore_intensity(
    image: nib.Nifti1Image,
    epsilon: float = 1e-8
) -> nib.Nifti1Image:
    #get mask
    data = image.get_fdata(dtype=np.float32)
    data[~np.isfinite(data)] = 0.0

    fg = data != 0
    if not np.any(fg) :
        out = nib.Nifti1Image(data.astype(np.float32), image.affine, header=image.header.copy())
        out.set_data_dtype(np.float32)
        return out

    #compute zscore
    mean = data[fg].mean()
    std = data[fg].std()

    data[fg] = (data[fg] - mean)/(std + epsilon)
    data[~fg] = 0.0
    data = data.astype(np.float32)

    out = nib.Nifti1Image(data,image.affine, header =  image.header.copy())
    out.set_data_dtype(np.float32)
    return out  

def pipeline_0(
    modalities : ModalityMap,
    template_ref_bool: bool = False,
    allowed_modality_types : set[str] | None = None
) -> dict[str, Any]:
    raw_input_summary = _summarize_modalities(modalities)
    reference_shape_3d = None
    
    preprocessed_modalities = {}        

    template_ref = None
    if template_ref_bool :
        template_patient = Patient(patient_id = "", images = modalities)
        template_ref = get_globalSpatialTemplate(patients = [template_patient])
    
    if not allowed_modality_types is None :
        allowed_modalities = {}
        for typeImg in allowed_modality_types :
            fname,image = get_img_by_type(images=modalities, typeImg=typeImg)
            allowed_modalities[fname] = image
        modalities = allowed_modalities
    effective_input_summary = _summarize_modalities(modalities)
    for fname,image in modalities.items():
        is_seg = _is_seg_filename(fname)
        interpolation_order = 0 if is_seg else 1
        preprocessed_modalities[fname] = canonicalize_volume(
            image = image,
            order = interpolation_order,
            template_ref = template_ref
        )
        if not is_seg :
            preprocessed_modalities[fname] = normalize_intensity(preprocessed_modalities[fname])
        #check if shape match reference shape (first modal shape)
        if reference_shape_3d is None :
            reference_shape_3d = preprocessed_modalities[fname].shape[:3]#first 3dims
        else :
            if reference_shape_3d != preprocessed_modalities[fname].shape[:3]:
                return { 
                    "preprocessed" : None,
                    "error" : "Unmatched canonicalized shape [:3] within same multimodal",
                    "success": False,
                    "summary": {
                        "pipeline": "pipeline_0",
                        "input": raw_input_summary,
                        "effective_input": effective_input_summary,
                        "partial_output": _summarize_modalities(preprocessed_modalities),
                        "template_ref_enabled": template_ref_bool,
                        "allowed_modality_types": sorted(allowed_modality_types) if allowed_modality_types else None,
                    },
                       }
        
    return {
        "preprocessed" : preprocessed_modalities,
        "success" : True,
        "summary": {
            "pipeline": "pipeline_0",
            "input": raw_input_summary,
            "effective_input": effective_input_summary,
            "output": _summarize_modalities(preprocessed_modalities),
            "template_ref_enabled": template_ref_bool,
            "allowed_modality_types": sorted(allowed_modality_types) if allowed_modality_types else None,
        },
    }
def normalize_intensity(image: nib.Nifti1Image) -> nib.Nifti1Image:
    #extract data and cast to np.float32
    data = image.get_fdata(dtype=np.float32)
    #set all voxels that has inf value to 0
    data[~np.isfinite(data)] = 0.0
    #foreground mask
    #we need mask because we don't want too much background voxels to be included in our calculation which can produce statistical error
    nonzero = data != 0
    if not np.any(nonzero):
        return nib.Nifti1Image(data.astype(np.float32), image.affine, header=image.header.copy())
    #Use only nonzero voxels to compute percentiles
    p1 = np.percentile(data[nonzero], 1)
    mask = (data > p1) & nonzero
    #clip outliers
    lo = np.percentile(data[mask],1)
    hi = np.percentile(data[mask],99)
    data = np.clip(data,lo,hi)
    #Recompute mask after clipping
    p1 = np.percentile(data[nonzero], 1)
    mask = (data > p1) & nonzero
    #apply background = 0
    data[~mask] = 0.0
    data = data.astype(np.float32)
    #wrap back in nifti
    out = nib.Nifti1Image(data, image.affine, header=image.header.copy())
    out.set_data_dtype(np.float32)
    return out
def crop(
    modalities: ModalityMap,
    margins: tuple[int, int, int] = (10, 10, 10),
    threshold: float | None = 0,
) -> tuple[ModalityMap, CropSlices3D]:
    x_mins = []
    x_maxs = []
    y_mins = []
    y_maxs = []
    z_mins = []
    z_maxs = []
    preprocessed_modalities = {}
    for _,image in modalities.items():
        data = np.asanyarray(image.dataobj)
        if threshold is None:
            fg = data != 0
        else:
            fg = data > threshold
        if not np.any(fg):
            #nothing to crop
            continue
            #crop_slices = (slice(0,data.shape[0]),slice(0,data.shape[1]),slice(0,data.shape[2]))
            #return data,crop_slices
        xs,ys,zs = np.where(fg)
        mx,my,mz = margins
    
        x_mins.append(max(xs.min() - mx,0))
        x_maxs.append(min(xs.max() + mx + 1,data.shape[0]))
        y_mins.append(max(ys.min() - my,0))
        y_maxs.append(min(ys.max() + my + 1,data.shape[1]))
        z_mins.append(max(zs.min() - mz,0))
        z_maxs.append(min(zs.max() + mz + 1,data.shape[2]))

    if len(x_mins) == len(x_maxs) == len(y_mins) == len(y_maxs) == len(z_mins) == len(z_maxs) == 0 :
        for fname,image in modalities.items():
            data = np.asanyarray(image.dataobj)
            crop_slices = (slice(0,data.shape[0]),slice(0,data.shape[1]),slice(0,data.shape[2]))
            cropped = data[crop_slices]
            new_affine = image.affine.copy()
            cropped_nifti = nib.Nifti1Image(cropped, new_affine, header=image.header.copy())
            preprocessed_modalities[fname] = cropped_nifti
        return preprocessed_modalities,crop_slices
    
    x_min = min(x_mins)
    x_max = max(x_maxs)
    y_min = min(y_mins)
    y_max = max(y_maxs)
    z_min = min(z_mins)
    z_max = max(z_maxs)
    crop_slices = (slice(x_min,x_max),
                   slice(y_min,y_max),
                   slice(z_min,z_max))
    #get reference image to create new affine
    ref_image = None
    for fname, img in modalities.items():
        if "seg" not in fname.lower():
            ref_image = img
            break
    # fallback: if only seg exists, then just use it
    if ref_image is None:
        ref_image = next(iter(modalities.values()))
    new_affine = ref_image.affine.copy()
    new_affine[:3,3] = (ref_image.affine @ np.array([x_min,y_min,z_min,1.0]))[:3]

    for fname,image in modalities.items():
        data = np.asanyarray(image.dataobj)
        cropped = data[crop_slices]
        cropped_nifti = nib.Nifti1Image(cropped, new_affine, header=image.header.copy())
        preprocessed_modalities[fname] = cropped_nifti

    return preprocessed_modalities,crop_slices


def _get_reference_image(modalities: ModalityMap) -> nib.Nifti1Image | None:
    ref_image = None
    for fname, img in modalities.items():
        if not _is_seg_filename(fname):
            ref_image = img
            break
    if ref_image is None and modalities:
        ref_image = next(iter(modalities.values()))
    return ref_image


def _center_crop_slices(current_shape: Shape3D, target_shape: Shape3D) -> tuple[CropSlices3D, Shape3D]:
    slices = []
    offsets = []
    for current, target in zip(current_shape, target_shape):
        if current <= target:
            start = 0
            stop = current
        else:
            start = (current - target) // 2
            stop = start + target
        slices.append(slice(start, stop))
        offsets.append(start)
    return tuple(slices), tuple(offsets)


def _center_crop_modalities_to_target(
    modalities: ModalityMap,
    target_shape: Shape3D,
) -> tuple[ModalityMap, CropSlices3D]:
    if not modalities:
        raise ValueError("No modalities to crop.")

    ref_image = _get_reference_image(modalities)
    if ref_image is None:
        raise ValueError("No reference image found for center crop.")

    ref_shape = ref_image.shape[:3]
    for fname, image in modalities.items():
        if image.shape[:3] != ref_shape:
            raise ValueError(f"Shape mismatch after crop: {fname} has {image.shape[:3]}, expected {ref_shape}")

    center_crop_slices, center_offsets = _center_crop_slices(ref_shape, target_shape)
    ox, oy, oz = center_offsets

    cropped_modalities = {}
    for fname, image in modalities.items():
        data = np.asanyarray(image.dataobj)
        cropped = data[center_crop_slices]

        new_affine = image.affine.copy()
        new_affine[:3, 3] = (image.affine @ np.array([ox, oy, oz, 1.0]))[:3]
        cropped_modalities[fname] = nib.Nifti1Image(cropped, new_affine, header=image.header.copy())

    return cropped_modalities, center_crop_slices


def compute_pad_widths(
    modalities: ModalityMap,
    target_shape: Shape3D,
) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    ref_image = _get_reference_image(modalities)
    if ref_image is None:
        raise ValueError("No reference image available to compute pad widths.")

    current_shape = ref_image.shape[:3]

    pad_widths = []
    for c, t in zip(current_shape, target_shape):
        diff = t - c
        if diff <= 0:
            pad_widths.append((0, 0))
        else:
            left = diff // 2
            right = diff - left
            pad_widths.append((left, right))

    return tuple(pad_widths)

def pipeline_1(
    modalities : ModalityMap,
    is_seg: bool = False,
    z_score_bool: bool = False,
    epsilon: float = 1e-8,
    margins: Tuple[int, int, int] = (10, 10, 10),
    threshold: float = 0,
    target_shape: Tuple[int, int, int] = (160, 160, 128),
    allowed_modality_types : set[str] | None = None
) -> dict[str, Any]:
    # Kept for backward compatibility with older callers.
    _ = is_seg
    raw_input_summary = _summarize_modalities(modalities)
    preprocessed_modalities = {}

    if not allowed_modality_types is None :
        allowed_modalities = {}
        for typeImg in allowed_modality_types :
            fname, image = get_img_by_type(images=modalities, typeImg=typeImg)
            allowed_modalities[fname] = image
        modalities = allowed_modalities
    effective_input_summary = _summarize_modalities(modalities)

    # z-score (images only)
    if z_score_bool:
        for fname, image in modalities.items():
            if "seg" in fname.lower():
                preprocessed_modalities[fname] = image
            else:
                preprocessed_modalities[fname] = zscore_intensity(image, epsilon=epsilon)
    else:
        preprocessed_modalities = modalities

    # crop (dict -> dict)
    crop_threshold = None if z_score_bool else threshold
    out, crop_slices = crop(preprocessed_modalities, margins=margins, threshold=crop_threshold)

    try:
        center_cropped, center_crop_slices = _center_crop_modalities_to_target(out, target_shape)
    except ValueError as exc:
        meta = {
            "crop_slices": crop_slices,
            "target_shape": target_shape,
            "error": str(exc),
        }
        return {
            "x": None,
            "y": None,
            "meta": meta,
            "success": False,
            "summary": {
                "pipeline": "pipeline_1",
                "input": raw_input_summary,
                "effective_input": effective_input_summary,
                "after_zscore": _summarize_modalities(preprocessed_modalities),
                "after_crop": _summarize_modalities(out),
                "target_shape": target_shape,
                "allowed_modality_types": sorted(allowed_modality_types) if allowed_modality_types else None,
                "z_score_enabled": z_score_bool,
            },
        }

    # shared pad widths from a reference modality inside the dict
    pad_widths = compute_pad_widths(center_cropped, target_shape)

    # pad every modality, and update affine translation for left padding
    padded_modalities = {}
    pxL, pyL, pzL = pad_widths[0][0], pad_widths[1][0], pad_widths[2][0]
    shift_vox = np.array([-pxL, -pyL, -pzL, 1.0], dtype=np.float64)

    for fname, img in center_cropped.items():
        data = np.asanyarray(img.dataobj)

        padded = np.pad(data, pad_widths, mode="constant", constant_values=0)

        new_affine = img.affine.copy()
        new_affine[:3, 3] = (img.affine @ shift_vox)[:3]

        # keep dtype sensible: float32 for images, keep seg integer-ish
        if "seg" in fname.lower():
            padded_nifti = nib.Nifti1Image(padded, new_affine, header=img.header.copy())
        else:
            padded_nifti = nib.Nifti1Image(padded.astype(np.float32), new_affine, header=img.header.copy())
            padded_nifti.set_data_dtype(np.float32)

        padded_modalities[fname] = padded_nifti

    # build stacked tensor in fixed order: FLAIR then T1CE
    def _find_by_keyword(mods: ModalityMap, keyword: str) -> tuple[str | None, nib.Nifti1Image | None]:
        wanted = keyword.upper()
        for fname, img in mods.items():
            if _extract_modality_token(fname) == wanted:
                return fname, img
        return None, None

    flair_name, flair_img = _find_by_keyword(padded_modalities, "flair")
    t1ce_name, t1ce_img = _find_by_keyword(padded_modalities, "t1ce")

    if flair_img is None or t1ce_img is None:
        meta = {
            "crop_slices": crop_slices,
            "center_crop_slices": center_crop_slices,
            "pad_widths": pad_widths,
            "target_shape": target_shape,
            "error": "Missing required modalities for stacking (need FLAIR and T1CE)."
        }
        return {
            "x": None,
            "y": None,
            "meta": meta,
            "success": False,
            "summary": {
                "pipeline": "pipeline_1",
                "input": raw_input_summary,
                "effective_input": effective_input_summary,
                "after_zscore": _summarize_modalities(preprocessed_modalities),
                "after_crop": _summarize_modalities(out),
                "after_center_crop": _summarize_modalities(center_cropped),
                "after_pad": _summarize_modalities(padded_modalities),
                "target_shape": target_shape,
                "allowed_modality_types": sorted(allowed_modality_types) if allowed_modality_types else None,
                "z_score_enabled": z_score_bool,
            },
        }

    x_flair = np.asanyarray(flair_img.dataobj).astype(np.float32, copy=False)
    x_t1ce  = np.asanyarray(t1ce_img.dataobj).astype(np.float32, copy=False)

    x = np.stack([x_flair, x_t1ce], axis=0)  # (C, X, Y, Z) with C=2

    # optional seg output
    seg_name, seg_img = _find_by_keyword(padded_modalities, "seg")
    y = None
    if seg_img is not None:
        y = np.asanyarray(seg_img.dataobj)

    meta = {
        "crop_slices": crop_slices,
        "center_crop_slices": center_crop_slices,
        "pad_widths": pad_widths,
        "target_shape": target_shape,
        "stack_order": ["flair", "t1ce"],
        "used_files": {"flair": flair_name, "t1ce": t1ce_name, "seg": seg_name},
    }

    return {
        "x": x,
        "y": y,
        "meta": meta,
        "success": True,
        "summary": {
            "pipeline": "pipeline_1",
            "input": raw_input_summary,
            "effective_input": effective_input_summary,
            "after_zscore": _summarize_modalities(preprocessed_modalities),
            "after_crop": _summarize_modalities(out),
            "after_center_crop": _summarize_modalities(center_cropped),
            "after_pad": _summarize_modalities(padded_modalities),
            "tensor": {
                "x": _summarize_array(x),
                "y": _summarize_array(y),
            },
            "target_shape": target_shape,
            "allowed_modality_types": sorted(allowed_modality_types) if allowed_modality_types else None,
            "z_score_enabled": z_score_bool,
        },
    }
