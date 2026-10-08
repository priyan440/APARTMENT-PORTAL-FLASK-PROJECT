from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from services.auth_service import login_required, role_required
from services.complaint_service import (
    update_complaint_status_by_technician,
    submit_technician_work_report
)
from database.mongodb import get_db

technician_bp = Blueprint("technician", __name__, url_prefix="/technician")

@technician_bp.before_request
@login_required
@role_required("TECHNICIAN")
def check_technician_access():
    pass

@technician_bp.route("/dashboard")
def dashboard():
    db = get_db()
    tech_id = session["user_id"]
    tech = db.users.find_one({"user_id": tech_id})

    new_assignments = list(db.complaints.find({"technician_id": tech_id, "status": "ASSIGNED"}).sort("created_at", -1))
    active_tasks = list(db.complaints.find({"technician_id": tech_id, "status": "IN_PROGRESS"}).sort("updated_at", -1))
    completed_tasks = list(db.complaints.find({"technician_id": tech_id, "status": {"$in": ["RESOLVED", "CLOSED"]}}).sort("updated_at", -1).limit(5))

    return render_template(
        "technician/dashboard.html",
        tech=tech,
        new_assignments=new_assignments,
        active_tasks=active_tasks,
        completed_tasks=completed_tasks
    )

@technician_bp.route("/assignments")
@technician_bp.route("/tasks")
def assignments():
    db = get_db()
    tech_id = session["user_id"]
    status_filter = request.args.get("status")
    
    query = {"technician_id": tech_id}
    if status_filter:
        query["status"] = status_filter

    tasks = list(db.complaints.find(query).sort("created_at", -1))
    return render_template("technician/assignments.html", tasks=tasks, active_status=status_filter)

@technician_bp.route("/tasks/<complaint_id>/update-status", methods=["POST"])
def update_status(complaint_id):
    db = get_db()
    tech = db.users.find_one({"user_id": session["user_id"]})
    new_status = request.form.get("status")
    notes = request.form.get("notes", "").strip()
    completion_file = request.files.get("completion_media") or request.files.get("after_image")

    if new_status == "RESOLVED" or request.form.get("is_work_report") == "true":
        before_file = request.files.get("before_image")
        after_file = request.files.get("after_image") or completion_file
        success, msg, _ = submit_technician_work_report(
            complaint_id=complaint_id,
            tech_user=tech,
            form_data=request.form,
            before_image=before_file,
            after_image=after_file
        )
    else:
        success, msg = update_complaint_status_by_technician(
            complaint_id=complaint_id,
            new_status=new_status,
            tech_user=tech,
            notes=notes,
            completion_file=completion_file
        )
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("technician.dashboard"))

@technician_bp.route("/tasks/<complaint_id>/complete", methods=["POST"])
def complete_task(complaint_id):
    db = get_db()
    tech = db.users.find_one({"user_id": session["user_id"]})
    before_file = request.files.get("before_image")
    after_file = request.files.get("after_image") or request.files.get("completion_media")

    success, msg, _ = submit_technician_work_report(
        complaint_id=complaint_id,
        tech_user=tech,
        form_data=request.form,
        before_image=before_file,
        after_image=after_file
    )
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("technician.dashboard"))

