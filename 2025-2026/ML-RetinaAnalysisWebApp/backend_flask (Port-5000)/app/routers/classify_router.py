# app/routers/image_router.py

import os, uuid, numpy as np
from flask import Blueprint, request, jsonify, current_app, session
from PIL import Image

from app.services.get_classification import classify
from app.services.get_preprocess import preprocess
from app.services.chatgpt import ask_chatgpt
from app.services.verify_retina import verify_retina

classes = ["0 - No_DR",
"1 - Mild",
"2 - Moderate",
"3 - Severe",
"4 - Proliferate_DR"]

classify_bp = Blueprint("classify", __name__)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "tif", "tiff"}

def allowed_file(fn: str) -> bool:
    return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS

@classify_bp.route("/api/classify", methods=["POST"])
def api_classify():
    content_len = request.content_length
    keys = list(request.files.keys())
    current_app.logger.info(f"[api_classify] content_length={content_len}, files={keys}")

    if "image" not in request.files:
        return jsonify({
            "error": "No file part named 'image'",
            "files_received": keys,
            "content_length": content_len
        }), 400

    file = request.files["image"]
    filename = file.filename
    current_app.logger.info(f"[api_classify] filename={filename!r}")

    if filename == "":
        return jsonify({
            "error": "Empty filename",
            "filename": filename
        }), 400

    ext = os.path.splitext(filename)[1].lower()
    if not allowed_file(filename):
        return jsonify({
            "error": "Invalid extension",
            "filename": filename,
            "extension": ext,
            "allowed": sorted(ALLOWED_EXTENSIONS)
        }), 400

    # Save raw upload
    raw_name = f"{uuid.uuid4().hex}.png"
    up_dir = os.path.join(current_app.root_path, "static/uploads")
    os.makedirs(up_dir, exist_ok=True)
    raw_path = os.path.join(up_dir, raw_name)
    file.save(raw_path)

    size_on_disk = os.path.getsize(raw_path)
    current_app.logger.info(f"[api_classify] saved to {raw_path} ({size_on_disk} bytes)")

    try:
        img = Image.open(raw_path).convert("RGB")
        arr = np.array(img)

        if not verify_retina(arr):
            return jsonify({
                "error": "Invalid retina image",
                "filename":filename,
                "extension": ext,
                "allowed": sorted(ALLOWED_EXTENSIONS)
            }), 400

        proc = preprocess(arr)
        pred_int  = classify(arr)
        label = classes[pred_int]
        proc_name = f"{uuid.uuid4().hex}.png"
        proc_dir  = os.path.join(current_app.root_path, "static/processed")
        os.makedirs(proc_dir, exist_ok=True)
        proc_path = os.path.join(proc_dir, proc_name)
        Image.fromarray(proc).save(proc_path, format="PNG")

        raw_url  = f"/static/uploads/{raw_name}"
        proc_url = f"/static/processed/{proc_name}"
    except Exception as e:
        current_app.logger.exception("Error in preprocessing/classify")
        return jsonify({"error": str(e)}), 500

    # ChatGPT
    if "history" not in session:
        session["history"] = []
    diag = f"Diabetic Retinopathy: {label}"
    prompt = f"'ROLE : SYSTEM' -> Explain the diagnosis (reply this message only to explain, do not reply like you are responding to a message): {diag}"
    reply = ask_chatgpt(user_message=prompt, history=session["history"], diagnosed=diag)
    h = session["history"]
    h.append({"role":"user",      "content":prompt})
    h.append({"role":"assistant", "content":reply})
    session["history"] = h

    return jsonify({
        "raw_url":       raw_url,
        "processed_url": proc_url,
        "classification": label,
        "chatgpt_reply":  reply
    }), 200
