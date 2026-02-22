from flask import Blueprint, request, session, redirect, url_for, flash, render_template, current_app
from app.services.firebase_service import init_firebase, create_user, sign_in_user, get_user
from werkzeug.security import generate_password_hash
from app.services.db_management import add_user

# Blueprint for authentication API routes
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.before_app_request
def initialize_firebase():
    """
    Ensure Firebase SDKs are initialized before handling any request.
    """
    if not getattr(current_app, 'firebase_initialized', False):
        init_firebase()
        current_app.firebase_initialized = True

@auth_bp.route('/register', methods=['POST','GET'])
def register():
    if "user_data" in session :
        return redirect(url_for('index'))
    if request.method == 'POST':
        # 1) Create user in Firebase Auth
        uid = create_user(
            email=request.form['email'],
            password=request.form['password'],
            display_name=f"{request.form['first_name']} {request.form['last_name']}"
        )
        # 2) Store extra doctor data locally
        #hashed_pw = generate_password_hash(request.form['password'])
        #flash('Inscription réussie! Vous pouvez maintenant vous connecter.', 'success')
        add_user(uid=uid)

        return redirect(url_for('login'))
    return render_template('register.html')

@auth_bp.route('/login', methods=['POST','GET'])
def login():
    if "user_data" in session :
        return redirect(url_for('index'))
    if request.method == 'POST':
        try:
            # Authenticate via Firebase
            auth_resp = sign_in_user(request.form['email'], request.form['password'])
            uid = auth_resp['localId']
            print("user found")

            # Fetch Firebase and local profile
            user_record = get_user(uid)

            # Set session data
            session['user_data'] = {
                'uid': uid,
                'name': user_record.display_name,
                'email': user_record.email,
            }
            #flash('Connexion réussie', 'success')
            return redirect(url_for('index'))
        except Exception:
            flash('Email ou mot de passe pas trouvé', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout', methods=['POST','GET'])
def logout():
    # Clear session on logout
    session.clear()
    #flash('Déconnexion réussie', 'success')
    return redirect(url_for('index'))
