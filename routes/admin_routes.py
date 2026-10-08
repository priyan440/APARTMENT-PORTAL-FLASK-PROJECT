from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from datetime import datetime
from services.auth_service import login_required, role_required, create_user
from services.analytics_service import get_dashboard_summary
from services.audit_service import get_recent_logs, log_action
from database.mongodb import get_db, get_next_sequence

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

@admin_bp.before_request
@login_required
@role_required("ADMIN")
def check_admin_access():
    pass

@admin_bp.route("/dashboard")
def dashboard():
    summary = get_dashboard_summary()
    db = get_db()
    recent_users = list(db.users.find().sort("created_at", -1).limit(6))
    recent_logs = get_recent_logs(8)
    return render_template("admin/dashboard.html", summary=summary, recent_users=recent_users, recent_logs=recent_logs)

@admin_bp.route("/users", methods=["GET", "POST"])
def users():
    db = get_db()
    role_filter = request.args.get("role")
    
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create_staff":
            role = request.form.get("role", "MANAGER").upper()
            data = {
                "name": request.form.get("name", "").strip(),
                "email": request.form.get("email", "").strip().lower(),
                "phone": request.form.get("phone", "").strip(),
                "password": request.form.get("password", "staff123"),
                "role": role,
                "specialization": request.form.get("specialization", "Plumbing"),
                "block": request.form.get("block", "").strip().upper(),
                "flat": request.form.get("flat", "").strip().upper(),
                "resident_type": request.form.get("resident_type", "OWNER").upper()
            }
            success, msg, new_u = create_user(data, creator_role="ADMIN")
            if success:
                log_action(session["user_id"], session["name"], "ADMIN", "CREATE_USER", "USER", new_u["user_id"], f"Created {data['role']} account for {data['name']}")
                flash(msg, "success")
            else:
                flash(msg, "danger")
        elif action == "toggle_status":
            uid = request.form.get("user_id")
            u = db.users.find_one({"user_id": uid})
            if u:
                new_status = "INACTIVE" if u.get("status") == "ACTIVE" else "ACTIVE"
                db.users.update_one({"user_id": uid}, {"$set": {"status": new_status, "updated_at": datetime.now()}})
                log_action(session["user_id"], session["name"], "ADMIN", "TOGGLE_USER_STATUS", "USER", uid, f"Status changed to {new_status}")
                flash(f"User {uid} status updated to {new_status}.", "info")
        return redirect(url_for("admin.users", role=role_filter))

    query = {}
    if role_filter:
        query["role"] = role_filter

    users_list = list(db.users.find(query).sort("created_at", -1))
    blocks = list(db.blocks.find({}, {"_id": 0, "code": 1, "name": 1}))
    vacant_flats = list(db.flats.find({"status": "VACANT"}, {"_id": 0, "flat_number": 1, "block": 1}).sort("flat_number", 1))
    return render_template("admin/users.html", users=users_list, active_role=role_filter, blocks=blocks, vacant_flats=vacant_flats)

@admin_bp.route("/blocks", methods=["GET", "POST"])
def blocks():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create_block":
            code = request.form.get("code", "").strip().upper()
            name = request.form.get("name", "").strip()
            floors = int(request.form.get("floors", 4))
            flats_per_floor = int(request.form.get("flats_per_floor", 4))

            block_id = f"BLK-{code}"
            if db.blocks.find_one({"block_id": block_id}):
                flash(f"Block with code {code} already exists.", "danger")
            else:
                db.blocks.insert_one({
                    "block_id": block_id,
                    "code": code,
                    "name": name,
                    "total_floors": floors,
                    "description": request.form.get("description", "")
                })

                # Auto-generate flats
                new_flats = []
                for fl in range(1, floors + 1):
                    for un in range(1, flats_per_floor + 1):
                        f_no = f"{code}-{fl}0{un}"
                        new_flats.append({
                            "flat_id": f"FLT-{f_no}",
                            "flat_number": f_no,
                            "block_id": block_id,
                            "block": code,
                            "floor": fl,
                            "bhk": 3 if fl >= 3 else 2,
                            "status": "VACANT",
                            "resident_id": None,
                            "resident_name": None
                        })
                db.flats.insert_many(new_flats)
                log_action(session["user_id"], session["name"], "ADMIN", "CREATE_BLOCK", "BLOCK", block_id, f"Created {name} with {len(new_flats)} flats")
                flash(f"Block {name} and {len(new_flats)} units created successfully.", "success")
        return redirect(url_for("admin.blocks"))

    blocks_list = list(db.blocks.find())
    for b in blocks_list:
        b["total_flats"] = db.flats.count_documents({"block": b.get("code")})
        b["occupied_flats"] = db.flats.count_documents({"block": b.get("code"), "status": "OCCUPIED"})
    return render_template("admin/blocks.html", blocks=blocks_list)

@admin_bp.route("/audit-logs")
def audit_logs():
    logs = get_recent_logs(150)
    return render_template("admin/audit_logs.html", logs=logs)
