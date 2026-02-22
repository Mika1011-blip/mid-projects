from flask import Flask, render_template, session, redirect, url_for
from flask_session import Session
from flask_wtf.csrf import CSRFProtect, generate_csrf
from app.config import Config
from app.routers.testing_router import testing_bp
from app.routers.classify_router import classify_bp
from app.routers.chatgpt_router import chatgpt_bp
from app.routers.auth_router import auth_bp
from app.routers.management_router import pp_bp
from app.routers.patient_router import patient_bp

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)
app.config.from_object(Config)
csrf = CSRFProtect(app)

csrf.exempt(auth_bp)
csrf.exempt(classify_bp)
csrf.exempt(chatgpt_bp)
csrf.exempt(pp_bp)
csrf.exempt(patient_bp)

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf)

# initialize server-side sessions
Session(app)

# register blueprints
app.register_blueprint(testing_bp)
app.register_blueprint(classify_bp)
app.register_blueprint(chatgpt_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(pp_bp)
app.register_blueprint(patient_bp)

# ensure per-user chat history
@app.before_request
def ensure_history():
    if "history" not in session:
        session["history"] = []

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chatgpt")
def chatgpt():
    return render_template("chatgpt.html")

@app.route("/login")
def login():
    return redirect(url_for("auth.login"))

@app.route("/register")
def register():
    return redirect(url_for("auth.register"))

@app.route("/style")
def style():
    return render_template("style.css")

@app.route('/account')
def account():
    return render_template('account.html')

@app.route('/management')
def management():
    return render_template('management.html')


@app.route('/patients')
def patients():
    return render_template('patients.html')


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
