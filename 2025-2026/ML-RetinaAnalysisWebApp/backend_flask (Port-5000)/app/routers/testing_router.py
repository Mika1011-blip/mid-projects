from flask import Blueprint,request,jsonify
from app.services.testing_service import concatenate_with_suffix

testing_bp = Blueprint("testing",__name__)

@testing_bp.route("/api/testing",methods=["POST"])
def api_testing():
    data = request.get_json()
    if not data or "text" not in data :
        return jsonify({"error": "Missing 'text' key in Json body"}),400
    
    return jsonify({"result": concatenate_with_suffix(data["text"])}), 200
