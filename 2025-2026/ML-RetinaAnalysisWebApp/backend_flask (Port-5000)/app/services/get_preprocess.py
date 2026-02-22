import numpy as np
import cv2


def preprocess(
    img: np.ndarray,
    IMG_SIZE: int = 224,
    sigmaX: float = None,
    clahe_clip: float = 2.0,
    clahe_grid: tuple = (8,8),
    gain: float = 2.0,
    background_value: int = 1
) -> np.ndarray:
    """
    1) Find the “retina” circle (gray-threshold → largest contour → min-enclosing circle).
    2) Mask out (zero-out) everything outside that circle, then crop to the bounding square.
    3) Resize to (IMG_SIZE×IMG_SIZE).
    4) Do your unsharp mask / CLAHE steps on that cropped‐and‐resized ROI.
    5) Build a final circular mask (same size IMG_SIZE×IMG_SIZE) so that:
         - pixels INSIDE the circle come from your preprocessed image,
         - pixels OUTSIDE the circle become `background_value`.
    6) Return that final composite.
    """

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    _, thresh = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if len(contours) > 0:
        cnt = max(contours, key=cv2.contourArea)
        (x, y), r = cv2.minEnclosingCircle(cnt)
        x, y, r = int(x), int(y), int(r)
        mask0 = np.zeros_like(gray, dtype=np.uint8)
        cv2.circle(mask0, (x, y), r, 255, thickness=-1)
        img_masked = cv2.bitwise_and(img, img, mask=mask0)
        x1, y1 = max(0, x - r), max(0, y - r)
        x2, y2 = min(img.shape[1], x + r), min(img.shape[0], y + r)
        roi = img_masked[y1:y2, x1:x2]
    else:
        roi = img.copy()
    roi_resized = cv2.resize(roi, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)
    if sigmaX is None:
        sigmaX = 0.1 * IMG_SIZE
    blur = cv2.GaussianBlur(roi_resized, (0,0), sigmaX=sigmaX)
    sharpened = cv2.addWeighted(roi_resized, gain, blur, -gain, 128)
    lab = cv2.cvtColor(sharpened, cv2.COLOR_RGB2LAB)
    L, A, B = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=clahe_grid)
    L2 = clahe.apply(L)
    lab2 = cv2.merge((L2, A, B))
    final_roi = cv2.cvtColor(lab2, cv2.COLOR_LAB2RGB)

    if background_value is None:
        background_value = np.mean(final_roi, axis=(0, 1)).astype(np.uint8)

    h, w = IMG_SIZE, IMG_SIZE
    circ_mask = np.zeros((h, w), dtype=np.uint8)
    center = (w // 2, h // 2)
    radius = w // 2
    cv2.circle(circ_mask, center, radius, 1, thickness=-1)
    mask_3ch = np.stack([circ_mask]*3, axis=-1)
    out = np.full((h, w, 3), background_value, dtype=np.uint8)
    out[mask_3ch == 1] = final_roi[mask_3ch == 1]

    return out
