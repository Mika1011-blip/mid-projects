# app/services/get_predict.py

import tensorflow as tf
import numpy as np
import os

def get_efficientNetB3(
    input_size: int = 224,
    num_classes: int = 5,
    backbone_trainable: bool = False,
    dropout_rate: float = 0.5,
    l2_reg: float = 0.01,
    l1_activity_reg: float = 0.002,
    learning_rate: float = 1e-3,
):
    base = tf.keras.applications.EfficientNetB3(
        include_top=False,
        weights="imagenet",
        input_shape=(input_size, input_size, 3),
        pooling="avg",
    )
    base.trainable = backbone_trainable
    inputs = tf.keras.Input(shape=(input_size, input_size, 3))
    x = tf.keras.applications.efficientnet.preprocess_input(inputs)
    x = base(x)
    x = tf.keras.layers.BatchNormalization(momentum=0.99, epsilon=1e-3)(x)
    x = tf.keras.layers.Dropout(dropout_rate)(x)
    x = tf.keras.layers.Dense(
        units=num_classes,
        activation="softmax",
        kernel_regularizer=tf.keras.regularizers.l2(l2_reg),
        activity_regularizer=tf.keras.regularizers.l1(l1_activity_reg),
    )(x)

    model = tf.keras.Model(inputs, x, name="EffNetB3_transfer")
    model.compile(
        optimizer=tf.keras.optimizers.Adamax(learning_rate=learning_rate),
        loss="categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model

import_weight = False

if not import_weight:
    model = get_efficientNetB3(backbone_trainable=True)
    model.load_weights(f"{os.getcwd()}/app/services/model_weights/multi_classification_weights.h5")
    import_weight = True

def predict(img: np.ndarray):
    """
    img should be a NumPy array of shape (1, 224, 224, 3) 
    or (batch_size, 224, 224, 3) already preprocessed.
    """
    probabilities = model.predict(img)
    return int(np.argmax(probabilities))

#print("TF Version:", tf.__version__)
