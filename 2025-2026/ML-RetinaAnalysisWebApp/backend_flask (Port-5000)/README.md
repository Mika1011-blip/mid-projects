# 🔍 1. Data Preprocessing (preprocessing.ipynb)

# 

# Retina extraction: contour detection and circular masking to isolate the fundus region

# 

# Image normalization: resizing to 224×224 pixels and applying Gaussian blur

# 

# Contrast enhancement: CLAHE (Contrast Limited Adaptive Histogram Equalization)

# 

# Data augmentation: random rotations, flips, and color jitter for robustness

# 

# 🤖 2. Model Training (models\_training.ipynb)

# 

# Transfer learning: fine-tuning EfficientNet-B3 pretrained on ImageNet

# 

# Binary vs multi-class: separate pipelines for retina detection and disease severity classification

# 

# Training strategies: class weighting, early stopping, and learning-rate scheduling

# 

# Hyperparameter choices: optimizer (Adam), learning rate (1e-4), batch size (32), number of epochs

# 

# 🌐 3. Web Deployment (backend\_flask/app.py)

# 

# Flask REST API: GET / for UI and POST /predict for predictions

# 

# HTML templates: Bootstrap-based upload form and result display

# 

# End-to-end flow: from image upload to model inference and result rendering in browser



