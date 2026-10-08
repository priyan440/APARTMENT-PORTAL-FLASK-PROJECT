from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from services.auth_service import login_required
from services.notification_service import get_user_notifications, get_unread_count, mark_as_read, mark_all_read

notification_bp = Blueprint("notifications", __name__, url_prefix="/notifications")

@notification_bp.before_request
@login_required
def check_login():
    pass

@notification_bp.route("")
@notification_bp.route("/")
def list_notifications():
    user_id = session["user_id"]
    notifs = get_user_notifications(user_id, limit=40)
    return render_template("notifications/index.html", notifications=notifs)

@notification_bp.route("/<notif_id>/read", methods=["POST"])
def read_notification(notif_id):
    mark_as_read(notif_id, session["user_id"])
    return jsonify({"success": True})

@notification_bp.route("/read-all", methods=["POST"])
def read_all():
    mark_all_read(session["user_id"])
    flash("All notifications marked as read.", "info")
    return redirect(request.referrer or url_for("notifications.list_notifications"))

@notification_bp.route("/api/unread-count")
def unread_count():
    count = get_unread_count(session["user_id"])
    return jsonify({"count": count})
