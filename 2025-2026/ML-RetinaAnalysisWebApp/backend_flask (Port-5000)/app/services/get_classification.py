# app/services/class_predict.py
import numpy as np
from app.services.get_predict import predict
from app.services.get_preprocess import preprocess

def classify(img: np.ndarray):
    """
    Accepts a raw RGB image as a NumPy array (height×width×3).
    1) Calls preprocess(...) → yields a (224×224×3) uint8 array.
    2) Converts that to the shape (1, 224, 224, 3) float32 (or whatever your model expects).
    3) Calls predict(...) → returns integer class index.
    """
    preprocessed_img = preprocess(img)  # (224, 224, 3) uint8
    img_batch = preprocessed_img.astype("float32")  # (224,224,3)
    img_batch = np.expand_dims(img_batch, axis=0)   # (1,224,224,3)
    return predict(img_batch)
