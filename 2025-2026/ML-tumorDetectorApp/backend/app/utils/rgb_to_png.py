import io
from PIL import Image
import numpy as np

def rgb_to_png_bytes(rgb: np.ndarray) -> bytes:
    if rgb.ndim != 3 or rgb.shape[-1] != 3:
        raise ValueError("Expected (H,W,3) RGB uint8 array")
    im = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()