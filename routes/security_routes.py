from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from services.auth_service import login_required, role_required
from services.security_service import check_in_visitor, check_out_visitor, record_delivery
from services.notification_service import create_notification
from database.mongodb import get_db

security_bp = Blueprint("security", __name__, url_prefix="/security")

@security_bp.before_request
@login_required
@role_required("SECURITY", "MANAGER", "ADMIN")
def check_security_access():
    pass

@security_bp.route("/dashboard")
def dashboard():
    db = get_db()
    today_str = datetime.now().strftime("%Y-%m-%d")

    expected_today = list(db.visitors.find({"expected_date": today_str, "status": "EXPECTED"}).sort("expected_time", 1))
    currently_inside = list(db.visitors.find({"status": "CHECKED_IN"}).sort("check_in_time", -1))
    recent_deliveries = list(db.deliveries.find({"status": "RECEIVED"}).sort("arrival_time", -1))
    active_sos = list(db.emergency_alerts.find({"status": "ACTIVE"}).sort("created_at", -1))

    return render_template(
        "security/dashboard.html",
        expected_today=expected_today,
        currently_inside=currently_inside,
        recent_deliveries=recent_deliveries,
        active_sos=active_sos
    )

@security_bp.route("/visitors", methods=["GET", "POST"])
def visitors():
    db = get_db()
    sec_user = db.users.find_one({"user_id": session["user_id"]})

    if request.method == "POST":
        action = request.form.get("action")
        if action == "walk_in":
            success, msg, _ = check_in_visitor(sec_user, walk_in_data=request.form)
            if success:
                flash(msg, "success")
            else:
                flash(msg, "danger")
        elif action == "check_in":
            vis_id = request.form.get("visitor_id")
            success, msg, _ = check_in_visitor(sec_user, visitor_id=vis_id)
            if success:
                flash(msg, "success")
            else:
                flash(msg, "danger")
        elif action == "check_out":
            vis_id = request.form.get("visitor_id")
            success, msg = check_out_visitor(sec_user, visitor_id=vis_id)
            if success:
                flash(msg, "info")
            else:
                flash(msg, "danger")
        return redirect(url_for("security.visitors"))

    search_query = request.args.get("search", "").strip()
    status_filter = request.args.get("status")

    query = {}
    if search_query:
        query["$or"] = [
            {"visitor_name": {"$regex": search_query, "$options": "i"}},
            {"phone": {"$regex": search_query, "$options": "i"}},
            {"flat": {"$regex": search_query, "$options": "i"}},
            {"vehicle_number": {"$regex": search_query, "$options": "i"}}
        ]
    if status_filter:
        query["status"] = status_filter

    visitors_list = list(db.visitors.find(query).sort("created_at", -1).limit(60))
    occupied_flats = list(db.flats.find({"status": "OCCUPIED"}).sort("flat_number", 1))

    return render_template(
        "security/visitors.html",
        visitors=visitors_list,
        occupied_flats=occupied_flats,
        search_query=search_query,
        active_status=status_filter
    )

@security_bp.route("/deliveries", methods=["GET", "POST"])
def deliveries():
    db = get_db()
    sec_user = db.users.find_one({"user_id": session["user_id"]})

    if request.method == "POST":
        action = request.form.get("action")
        if action == "record":
            success, msg, _ = record_delivery(sec_user, request.form)
            if success:
                flash(msg, "success")
            else:
                flash(msg, "danger")
        elif action == "mark_collected":
            del_id = request.form.get("delivery_id")
            db.deliveries.update_one(
                {"delivery_id": del_id},
                {"$set": {"status": "COLLECTED", "collected_at": datetime.now().isoformat()}}
            )
            flash("Delivery marked as collected.", "info")
        return redirect(url_for("security.deliveries"))

    deliveries_list = list(db.deliveries.find().sort("created_at", -1).limit(50))
    occupied_flats = list(db.flats.find({"status": "OCCUPIED"}).sort("flat_number", 1))
    return render_template("security/deliveries.html", deliveries=deliveries_list, occupied_flats=occupied_flats)

@security_bp.route("/emergency", methods=["GET", "POST"])
def emergency():
    db = get_db()
    if request.method == "POST":
        alert_id = request.form.get("alert_id")
        action_note = request.form.get("action_note", "Attended and resolved by security.")
        db.emergency_alerts.update_one(
            {"alert_id": alert_id},
            {"$set": {
                "status": "RESOLVED",
                "resolved_at": datetime.now(),
                "resolved_by": session["name"],
                "resolution_notes": action_note
            }}
        )
        flash(f"Emergency alert {alert_id} marked as resolved.", "success")
        return redirect(url_for("security.emergency"))

    active_alerts = list(db.emergency_alerts.find({"status": "ACTIVE"}).sort("created_at", -1))
    resolved_alerts = list(db.emergency_alerts.find({"status": "RESOLVED"}).sort("resolved_at", -1).limit(20))
    return render_template("security/emergency.html", active_alerts=active_alerts, resolved_alerts=resolved_alerts)
