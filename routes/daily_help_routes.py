from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, abort
from datetime import datetime, date
from services.auth_service import login_required, role_required
from services.gridfs_service import stream_gridfs_file
from services.daily_help_service import (
    DAILY_HELP_TYPES,
    DAYS_OF_WEEK,
    VERIFICATION_STATUSES,
    HELP_STATUSES,
    register_daily_help,
    update_daily_help,
    deactivate_daily_help,
    verify_daily_help,
    get_todays_expected_daily_help,
    security_search_daily_help,
    daily_help_check_in,
    daily_help_check_out,
    get_daily_help_analytics
)
from database.mongodb import get_db

daily_help_bp = Blueprint("daily_help", __name__)

@daily_help_bp.route("/daily-help/document/<file_id>", methods=["GET"])
def download_help_document(file_id):
    """Stream GridFS document or photo for daily help."""
    response = stream_gridfs_file(file_id)
    if not response:
        abort(404)
    return response

# =========================================================================
# RESIDENT ROUTES
# =========================================================================

@daily_help_bp.route("/resident/daily-help", methods=["GET"])
@login_required
@role_required("RESIDENT")
def resident_daily_help_list():
    db = get_db()
    user_id = session["user_id"]
    user = db.users.find_one({"user_id": user_id})

    helpers = list(db.daily_help.find({"resident_id": user_id}).sort("created_at", -1))
    
    # Fetch recent attendance records for this resident's helpers
    help_ids = [h["help_id"] for h in helpers]
    attendance_records = list(db.daily_help_attendance.find({"resident_id": user_id}).sort("date", -1).limit(30))

    return render_template(
        "resident/daily_help.html",
        user=user,
        helpers=helpers,
        helps=helpers,
        attendance_records=attendance_records,
        service_types=DAILY_HELP_TYPES,
        days_of_week=DAYS_OF_WEEK
    )


@daily_help_bp.route("/resident/daily-help/add", methods=["POST"], endpoint="resident_add_help")
@daily_help_bp.route("/resident/daily-help/add-help", methods=["POST"], endpoint="resident_add_daily_help")
@login_required
@role_required("RESIDENT")
def resident_add_help():
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    photo_file = request.files.get("photo")
    id_proof_file = request.files.get("id_proof")
    success, msg, _ = register_daily_help(user, request.form, photo_file, id_proof_file)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("daily_help.resident_daily_help_list"))


@daily_help_bp.route("/resident/daily-help/<help_id>/edit", methods=["POST"])
@login_required
@role_required("RESIDENT")
def resident_edit_daily_help(help_id):
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    photo_file = request.files.get("photo")
    id_proof_file = request.files.get("id_proof")
    success, msg = update_daily_help(user, help_id, request.form, photo_file, id_proof_file)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("daily_help.resident_daily_help_list"))


@daily_help_bp.route("/resident/daily-help/<help_id>/deactivate", methods=["POST"], endpoint="resident_deactivate_help")
@daily_help_bp.route("/resident/daily-help/<help_id>/deactivate-help", methods=["POST"], endpoint="resident_deactivate_daily_help")
@login_required
@role_required("RESIDENT")
def resident_deactivate_help(help_id):
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    success, msg = deactivate_daily_help(user, help_id)
    if success:
        flash(msg, "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("daily_help.resident_daily_help_list"))


# =========================================================================
# MANAGER & ADMIN ROUTES
# =========================================================================

@daily_help_bp.route("/manager/daily-help", methods=["GET"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_daily_help_list():
    db = get_db()
    verification_filter = request.args.get("verification") or request.args.get("status")
    type_filter = request.args.get("type") or request.args.get("service_type")
    search_query = request.args.get("q", "").strip() or request.args.get("search", "").strip()

    query = {}
    if verification_filter:
        query["verification_status"] = verification_filter
    if type_filter:
        query["person.service_type"] = type_filter
    if search_query:
        query["$or"] = [
            {"person.name": {"$regex": search_query, "$options": "i"}},
            {"person.phone": {"$regex": search_query, "$options": "i"}},
            {"flat_id": {"$regex": search_query, "$options": "i"}},
            {"resident_name": {"$regex": search_query, "$options": "i"}},
            {"help_id": {"$regex": search_query, "$options": "i"}}
        ]

    helpers = list(db.daily_help.find(query).sort("created_at", -1))
    analytics = get_daily_help_analytics()

    return render_template(
        "manager/daily_help.html",
        helpers=helpers,
        helps=helpers,
        analytics=analytics,
        service_types=DAILY_HELP_TYPES,
        verification_statuses=VERIFICATION_STATUSES,
        help_statuses=HELP_STATUSES,
        active_verification=verification_filter,
        status_filter=verification_filter,
        active_type=type_filter,
        service_type_filter=type_filter,
        search_query=search_query
    )


@daily_help_bp.route("/manager/daily-help/<help_id>/verify", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_verify_daily_help(help_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    action = request.form.get("action", "APPROVE")
    reason = request.form.get("reason", "")
    success, msg = verify_daily_help(mgr, help_id, action, reason)
    if success:
        flash(msg, "success" if action in ["APPROVE", "REACTIVATE"] else "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("daily_help.manager_daily_help_list"))


@daily_help_bp.route("/manager/daily-help/<help_id>/approve", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_approve_help(help_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    success, msg = verify_daily_help(mgr, help_id, "APPROVE", "")
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("daily_help.manager_daily_help_list"))


@daily_help_bp.route("/manager/daily-help/<help_id>/reject", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_reject_help(help_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    reason = request.form.get("reason", "")
    success, msg = verify_daily_help(mgr, help_id, "REJECT", reason)
    if success:
        flash(msg, "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("daily_help.manager_daily_help_list"))


@daily_help_bp.route("/manager/daily-help/<help_id>/status", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_change_status(help_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    target_status = request.form.get("status", "ACTIVE")
    action = "REACTIVATE" if target_status == "ACTIVE" else "SUSPEND"
    success, msg = verify_daily_help(mgr, help_id, action, f"Status updated to {target_status} by manager")
    if success:
        flash(msg, "success" if target_status == "ACTIVE" else "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("daily_help.manager_daily_help_list"))


# =========================================================================
# SECURITY GATE ROUTES
# =========================================================================

@daily_help_bp.route("/security/daily-help", methods=["GET"])
@login_required
@role_required("SECURITY", "MANAGER", "ADMIN")
def security_daily_help_console():
    db = get_db()
    today_str = date.today().strftime("%Y-%m-%d")

    search_query = request.args.get("search", "").strip()
    if search_query:
        search_results = security_search_daily_help(search_query)
    else:
        search_results = None

    expected_today = get_todays_expected_daily_help()
    currently_inside = list(db.daily_help_attendance.find({"date": today_str, "status": "CHECKED_IN"}).sort("check_in", -1))
    recent_logs = list(db.daily_help_attendance.find({"date": today_str}).sort("updated_at", -1).limit(40))

    return render_template(
        "security/daily_help.html",
        expected_today=expected_today,
        currently_inside=currently_inside,
        inside_records=currently_inside,
        recent_logs=recent_logs,
        today_attendance=recent_logs,
        search_results=search_results,
        search_query=search_query,
        today_day=date.today().strftime("%a").upper()
    )


@daily_help_bp.route("/security/daily-help/check-in", methods=["POST"])
@daily_help_bp.route("/security/daily-help/<help_id>/check-in", methods=["POST"])
@login_required
@role_required("SECURITY", "MANAGER", "ADMIN")
def security_check_in(help_id=None):
    db = get_db()
    sec_user = db.users.find_one({"user_id": session["user_id"]})
    h_id = help_id or request.form.get("help_id") or request.args.get("help_id")
    success, msg, _ = daily_help_check_in(sec_user, h_id)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("daily_help.security_daily_help_console"))


@daily_help_bp.route("/security/daily-help/check-out", methods=["POST"])
@daily_help_bp.route("/security/daily-help/<help_id>/check-out", methods=["POST"])
@login_required
@role_required("SECURITY", "MANAGER", "ADMIN")
def security_check_out(help_id=None):
    db = get_db()
    sec_user = db.users.find_one({"user_id": session["user_id"]})
    h_id = help_id or request.form.get("help_id") or request.args.get("help_id")
    success, msg, _ = daily_help_check_out(sec_user, h_id)
    if success:
        flash(msg, "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("daily_help.security_daily_help_console"))
