from flask import Blueprint, request, jsonify, current_app, session
from app.services.db_management import add_user,update_user_role,db_remove_user,search_user,add_patients,update_patient,remove_patient,search_patients
from app.services.firebase_service import fetch_all_users,fb_remove_user


pp_bp = Blueprint('management',__name__,url_prefix='/management')

@pp_bp.route("/list_users",methods= ["POST"])
def list_users():
    data = request.get_json() or {}
    email = data.get('email')

    if email:
        users = fetch_all_users(email=email)
    else :
        users = fetch_all_users()
    
    if users :
        for user in users:
            local = search_user(user["uid"])
            user["role"] = local["role"] if local else None
        return jsonify(users),200
    else :
        return jsonify({"error":"No users found"}),400

@pp_bp.route('/remove_user', methods=['POST'])
def remove_user_route():
    data = request.get_json() or {}
    uid = data.get('uid')
    if not uid:
        return jsonify({ 'success': False, 'error': 'Missing uid' }), 400

    # call your service
    db_remove_user(uid)  # or import and call your remove_user function
    fb_remove_user(uid)

    return jsonify({ 'success': True })

@pp_bp.route("/update_user", methods=["POST"])
def update_user():
    data = request.get_json() or {}
    uid = data.get("uid")
    role = data.get("role")

    if uid is None or role is None:
        return jsonify({ "success": False, "error": "Missing uid or role" }), 400

    try:
        updated = update_user_role(uid, int(role))
    except Exception as e:
        return jsonify({ "success": False, "error": str(e) }), 500

    if not updated:
        return jsonify({ "success": False, "error": "User not found or no change" }), 404

    return jsonify({ "success": True }), 200
