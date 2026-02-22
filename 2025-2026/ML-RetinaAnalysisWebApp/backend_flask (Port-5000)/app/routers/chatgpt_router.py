from app.services.chatgpt import ask_chatgpt
from flask import Blueprint, request, jsonify, current_app,session



chatgpt_bp = Blueprint('chatgpt', __name__)
@chatgpt_bp.route("/api/chatgpt",methods=["POST"])
def api_chatgpt ():

    if "history" not in session:
        session["history"] = []

    data = request.get_json()
    user_message = data.get("message","").strip()
    if not user_message :
        return jsonify({"error": "No message"}), 400
    history = session["history"]
    reply = ask_chatgpt(user_message,history)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})
    session["history"] = history

    return jsonify({"reply": reply})


