import threading
from flask import current_app

# Hold references to initialized apps
i_admin_app = None
_pyrebase_app = None
_lock = threading.Lock()

# Custom exceptions
class FirebaseAuthError(Exception):
    """Generic Firebase authentication error"""
    pass


def _load_firebase_admin():
    # Lazy import to avoid protobuf version conflicts when TF loads
    import firebase_admin
    from firebase_admin import credentials, auth as admin_auth
    return firebase_admin, credentials, admin_auth


def _load_pyrebase():
    import pyrebase
    return pyrebase


def _load_smtp():
    import smtplib
    from email.message import EmailMessage
    return smtplib, EmailMessage


def init_firebase():
    """
    Initializes Firebase Admin SDK and Pyrebase client for Authentication only.
    This function is thread-safe and idempotent.
    """
    global i_admin_app, _pyrebase_app

    with _lock:
        if i_admin_app is None:
            firebase_admin, credentials, admin_auth = _load_firebase_admin()
            cred_path = current_app.config['FIREBASE_CREDENTIALS']
            cred = credentials.Certificate(cred_path)
            i_admin_app = firebase_admin.initialize_app(
                credential=cred
            )
        if _pyrebase_app is None:
            pyrebase = _load_pyrebase()
            _pyrebase_app = pyrebase.initialize_app(
                current_app.config['FIREBASE_CONFIG']
            )


def send_verification_email(to_email: str, verification_link: str) -> None:
    """
    Sends a verification email containing the provided link via SMTP.
    SMTP settings are loaded from Flask config.
    """
    smtplib, EmailMessage = _load_smtp()
    smtp_host = current_app.config.get('SMTP_HOST')
    smtp_port = current_app.config.get('SMTP_PORT')
    smtp_user = current_app.config.get('SMTP_USER')
    smtp_pass = current_app.config.get('SMTP_PASS')
    from_email = current_app.config.get('SMTP_FROM')

    if not all([smtp_host, smtp_port, smtp_user, smtp_pass, from_email]):
        raise FirebaseAuthError("SMTP configuration is incomplete.")

    msg = EmailMessage()
    msg['Subject'] = 'Please verify your email'
    msg['From'] = from_email
    msg['To'] = to_email
    msg.set_content(f"Click the link to verify your email: {verification_link}")

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        raise FirebaseAuthError(f"Failed to send verification email: {e}")


def create_user(email: str, password: str, display_name: str = None) -> dict:
    """
    Creates a new Firebase Auth user. Generates and optionally sends an email verification link.
    Returns a dict containing {'uid': str, 'verification_link': str}.
    """
    init_firebase()
    _, _, admin_auth = _load_firebase_admin()

    try:
        user = admin_auth.create_user(
            email=email,
            password=password,
            display_name=display_name
        )
    except Exception as e:
        raise FirebaseAuthError(f"Failed to create user: {e}")

    try:
        link = admin_auth.generate_email_verification_link(email)
        #send_verification_email(email, link)
        print("*****_VERIFICATION_LINK ***** : ", link)
    except Exception as e:
        raise FirebaseAuthError(f"Failed to generate/send verification link: {e}")

    return {"uid": user.uid, "verification_link": link}


def delete_user(uid: str) -> None:
    """
    Deletes the specified Firebase Auth user.
    """
    init_firebase()
    _, _, admin_auth = _load_firebase_admin()
    admin_auth.delete_user(uid)

def _user_record_to_dict(user_record):
    return {
        'created_at':     user_record.user_metadata.creation_timestamp,
        #'disabled':       user_record.disabled,
        'email_verified': user_record.email_verified,
        'display_name':   user_record.display_name,
        'email':          user_record.email,
        'uid':            user_record.uid
    }

def fetch_all_users(email=None):
    """
    If `email` is None, returns a list of dicts for *all* users.
    If `email` is provided, returns a single-element list of that user (or None if not found).
    """
    init_firebase()
    _, _, admin_auth = _load_firebase_admin()
    all_users = []

    if email is None:
        # list every user, paginated under the hood
        for user_record in admin_auth.list_users().iterate_all():
            all_users.append(_user_record_to_dict(user_record))
    else:
        # look up exactly one user
        try:
            user_record = admin_auth.get_user_by_email(email)
        except admin_auth.UserNotFoundError:
            print(f"No user found with email={email!r}")
            return None
        all_users.append(_user_record_to_dict(user_record))

    return all_users

def fb_remove_user(uid: str) -> bool:
    init_firebase()
    _, _, admin_auth = _load_firebase_admin()
    try:
        admin_auth.delete_user(uid)
        print(f"Successfully deleted user {uid}")
        return True
    except admin_auth.UserNotFoundError:
        print(f"No user found with UID {uid}")
        return False
    except Exception as e:
        print(f"Error deleting user {uid}: {e}")
        return False



def sign_in_user(email: str, password: str, check_email_verified: bool = False) -> dict:
    """
    Signs in a user with email/password via Pyrebase client.
    Returns the authentication response containing tokens and UID.

    Raises:
        FirebaseAuthError: if authentication fails or email is unverified (if requested).
    """
    # ensure Firebase (and Pyrebase app) is initialized
    init_firebase()

    if _pyrebase_app is None:
        raise RuntimeError("Pyrebase not initialized. Call init_firebase() first.")

    # Use the initialized app—not the module—to get the auth client
    auth_client = _pyrebase_app.auth()

    try:
        auth_resp = auth_client.sign_in_with_email_and_password(email, password)
    except Exception as e:
        raise FirebaseAuthError(f"Authentication failed: {e}")

    # Optionally enforce email verification
    if check_email_verified:
        _, _, admin_auth = _load_firebase_admin()
        user_record = admin_auth.get_user(auth_resp['localId'])
        if not user_record.email_verified:
            raise FirebaseAuthError("Email address not verified.")

    return auth_resp


def get_user(uid: str):
    """
    Retrieves a Firebase Auth user record by UID via Admin SDK.
    Returns a UserRecord object.
    """
    init_firebase()
    _, _, admin_auth = _load_firebase_admin()
    return admin_auth.get_user(uid)
