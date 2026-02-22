import tensorflow as tf 
import numpy as np
import os,cv2

def get_cnn_model(
    name="cnn_model",
    num_classes=2,
    grayscale=False,
    zoom_factor=0.1,
    rotation_factor=0.1,
):
    # determine channels & output settings
    color_channels = 1 if grayscale else 3
    if num_classes == 2:
        final_units = 1
        final_activation = "sigmoid"
        loss = tf.keras.losses.BinaryCrossentropy()
        metrics = ["accuracy"]
    else:
        final_units = num_classes
        final_activation = "softmax"
        loss = tf.keras.losses.CategoricalCrossentropy()
        metrics = ["accuracy"]

    model = tf.keras.Sequential(
        [
            tf.keras.layers.InputLayer(input_shape=(224, 224, color_channels)),
            tf.keras.layers.Rescaling(1.0 / 255.0),
            tf.keras.layers.RandomFlip("horizontal_and_vertical"),
            tf.keras.layers.RandomRotation(rotation_factor),
            tf.keras.layers.RandomZoom(zoom_factor),

            tf.keras.layers.Conv2D(32, 3, activation="relu", padding="same"),
            tf.keras.layers.MaxPooling2D(),

            tf.keras.layers.Conv2D(64, 3, activation="relu", padding="same"),
            tf.keras.layers.MaxPooling2D(),

            tf.keras.layers.Flatten(),
            tf.keras.layers.Dense(64, activation="relu"),
            tf.keras.layers.Dropout(0.5),
            tf.keras.layers.Dense(final_units, activation=final_activation),
        ],
        name=name,
    )

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss=loss,
        metrics=metrics,
    )
    return model

def general_preprocess(image, img_size=224):
    resized = cv2.resize(
        image,
        (img_size, img_size),
        interpolation=cv2.INTER_AREA
    )
    blur = cv2.GaussianBlur(resized, (0, 0), sigmaX=10)
    pre_clahe = cv2.addWeighted(resized, 2, blur, -2, 128)
    lab = cv2.cvtColor(pre_clahe, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l2 = clahe.apply(l)
    lab2 = cv2.merge((l2, a, b))
    post_clahe = cv2.cvtColor(lab2, cv2.COLOR_LAB2RGB)
    return np.clip(post_clahe, 0, 255).astype(np.uint8)

import_weight = False
if not import_weight:        
    verify_retina_model = get_cnn_model(grayscale = True)
    verify_retina_model.load_weights(f"{os.getcwd()}/app/services/model_weights/binary_classification_weights.h5")
    import_weights = True


def verify_retina(img: np.ndarray):
    # 1) Preprocess & grayscale
    prpced = general_preprocess(img)                           # (224,224,3) uint8
    gray = tf.image.rgb_to_grayscale(prpced)                   # (224,224,1) uint8/float

    # 2) Add batch dim & cast to float32
    inp = tf.expand_dims(gray, axis=0)                         # (1,224,224,1)
    inp = tf.cast(inp, tf.float32)                             # ensure float32

    # 3) Predict
    prob = verify_retina_model.predict(inp)[0, 0]               # scalar in [0,1]

    # 4) Threshold to get class (0 or 1)
    return int(prob > 0.5)
