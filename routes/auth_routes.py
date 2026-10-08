from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort
from services.auth_service import authenticate_user, create_user
from services.gridfs_service import stream_gridfs_file
from database.mongodb import get_db

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/")
def index():
    return render_template("landing.html")

@auth_bp.route("/dashboard")
def role_dashboard_redirect():
    if "user_id" in session:
        role_dashboards = {
            "ADMIN": "admin.dashboard",
            "MANAGER": "manager.dashboard",
            "RESIDENT": "resident.dashboard",
            "TECHNICIAN": "technician.dashboard",
            "SECURITY": "security.dashboard"
        }
        return redirect(url_for(role_dashboards.get(session.get("role"), "auth.login")))
    return redirect(url_for("auth.login"))

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("auth.role_dashboard_redirect"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        
        user, err = authenticate_user(identifier, password)
        if err:
            flash(err, "danger")
            return render_template("auth/login.html", identifier=identifier)

        # Set session
        session.permanent = True
        session["user_id"] = user["user_id"]
        session["name"] = user["name"]
        session["email"] = user["email"]
        session["role"] = user["role"]
        session["block"] = user.get("block", "")
        session["flat"] = user.get("flat", "")

        flash(f"Welcome back, {user['name']}!", "success")

        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)

        role_dashboards = {
            "ADMIN": "admin.dashboard",
            "MANAGER": "manager.dashboard",
            "RESIDENT": "resident.dashboard",
            "TECHNICIAN": "technician.dashboard",
            "SECURITY": "security.dashboard"
        }
        return redirect(url_for(role_dashboards.get(user["role"], "auth.login")))

    return render_template("auth/login.html")

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Resident self-registration."""
    db = get_db()
    blocks = list(db.blocks.find({}, {"_id": 0, "code": 1, "name": 1}))
    # Find vacant flats
    vacant_flats = list(db.flats.find({"status": "VACANT"}, {"_id": 0, "flat_number": 1, "block": 1}).sort("flat_number", 1))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        block = request.form.get("block", "").strip().upper()
        flat = request.form.get("flat", "").strip().upper()
        resident_type = request.form.get("resident_type", "OWNER").upper()

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("auth/register.html", blocks=blocks, vacant_flats=vacant_flats, form=request.form)

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return render_template("auth/register.html", blocks=blocks, vacant_flats=vacant_flats, form=request.form)

        data = {
            "name": name,
            "email": email,
            "phone": phone,
            "password": password,
            "role": "RESIDENT",
            "block": block,
            "flat": flat,
            "resident_type": resident_type
        }

        success, msg, user = create_user(data)
        if not success:
            flash(msg, "danger")
            return render_template("auth/register.html", blocks=blocks, vacant_flats=vacant_flats, form=request.form)

        flash("Registration successful! Please log in with your credentials.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", blocks=blocks, vacant_flats=vacant_flats)

@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route("/media/<file_id>")
def get_media(file_id):
    """Secure endpoint to stream GridFS images/videos."""
    response = stream_gridfs_file(file_id)
    if not response:
        abort(404)
    return response
