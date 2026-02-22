# app/routers/patient_router.py

from flask import Blueprint, request, jsonify
from app.services.db_management import (
    add_patients,
    update_patient,
    remove_patient,
    search_patients
)

patient_bp = Blueprint('patient', __name__, url_prefix='/patient')

@patient_bp.route('/add', methods=['POST'])
def add_patient_route():
    data = request.get_json() or {}
    # expects a single patient dict
    try:
        add_patients(data)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True}), 200

@patient_bp.route('/update', methods=['POST'])
def update_patient_route():
    data = request.get_json() or {}
    pid = data.get('id')
    updates = data.get('updates', {})
    if pid is None or not updates:
        return jsonify({'success': False, 'error': 'Missing id or updates'}), 400
    try:
        update_patient(pid, updates)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True}), 200

@patient_bp.route('/delete', methods=['POST'])
def delete_patient_route():
    data = request.get_json() or {}
    pid = data.get('id')
    if pid is None:
        return jsonify({'success': False, 'error': 'Missing id'}), 400
    remove_patient(pid)
    return jsonify({'success': True}), 200

@patient_bp.route('/search', methods=['POST'])
def search_patients_route():
    data = request.get_json() or {}
    email = data.get('email')
    telephone = data.get('telephone')
    try:
        results = search_patients(email=email, telephone=telephone)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify(results), 200


@patient_bp.route('/profile')
def patient_profile():
    # grab ?id= from the URL
    patient_id = request.args.get('id', type=int)
    if not patient_id:
        abort(400, "Missing patient id")

    # fetch by id – you could add a helper search_by_id,
    # but since search_patients only handles email/telephone,
    # let's pull them all and then filter, or better yet write a new function.
    results = search_patients(email=None, telephone=None)  # all patients
    patient = next((p for p in results if p['id'] == patient_id), None)
    if not patient:
        abort(404, "Patient not found")

    return render_template('patient_profile.html', patient=patient)