from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
from services.auth_service import login_required, role_required, create_user
from services.complaint_service import assign_technician, get_technician_workload_list, approve_work_report, reopen_complaint, CATEGORIES, PRIORITIES, STATUSES
from services.booking_service import approve_booking, reject_booking
from services.billing_service import generate_bill
from services.analytics_service import get_dashboard_summary, get_analytics_charts_data
from services.audit_service import get_recent_logs, log_action
from services.parking_service import get_parking_overview, release_vehicle, detect_parking_duplicates
from database.mongodb import get_db, get_next_sequence

manager_bp = Blueprint("manager", __name__, url_prefix="/manager")

@manager_bp.before_request
@login_required
@role_required("MANAGER", "ADMIN")
def check_manager_access():
    pass

@manager_bp.route("/dashboard")
def dashboard():
    summary = get_dashboard_summary()
    db = get_db()
    
    # Recent items needing manager attention
    pending_complaints = list(db.complaints.find({"status": "OPEN"}).sort("created_at", -1).limit(5))
    pending_bookings = list(db.bookings.find({"status": "PENDING"}).sort("created_at", -1).limit(5))
    recent_visitors = list(db.visitors.find().sort("created_at", -1).limit(5))
    active_alerts = list(db.emergency_alerts.find({"status": "ACTIVE"}).sort("created_at", -1))

    return render_template(
        "manager/dashboard.html",
        summary=summary,
        pending_complaints=pending_complaints,
        pending_bookings=pending_bookings,
        recent_visitors=recent_visitors,
        active_alerts=active_alerts
    )

# ----------------- BLOCK-WISE RESIDENTS (Section 15) ----------------- #
@manager_bp.route("/residents")
def block_residents():
    db = get_db()
    selected_block = request.args.get("block", "A").upper()

    blocks = list(db.blocks.find())
    
    # Metrics for selected block
    total_flats = db.flats.count_documents({"block": selected_block})
    occupied_flats = db.flats.count_documents({"block": selected_block, "status": "OCCUPIED"})
    vacant_flats = total_flats - occupied_flats
    total_residents = db.users.count_documents({"role": "RESIDENT", "block": selected_block, "status": "ACTIVE"})
    open_complaints = db.complaints.count_documents({"block": selected_block, "status": {"$in": ["OPEN", "ASSIGNED", "IN_PROGRESS"]}})
    
    # Pending bills in this block
    pending_bills_count = db.bills.count_documents({"block": selected_block, "status": {"$ne": "PAID"}})

    # Flats list for this block
    flats = list(db.flats.find({"block": selected_block}).sort("flat_number", 1))

    # Pre-fetch resident details if occupied
    for f in flats:
        if f.get("resident_id"):
            f["resident"] = db.users.find_one({"user_id": f["resident_id"]})
        else:
            f["resident"] = None

    selected_flat_number = request.args.get("flat")
    flat_details = None
    if selected_flat_number:
        flat_doc = db.flats.find_one({"flat_number": selected_flat_number})
        if flat_doc:
            resident = db.users.find_one({"user_id": flat_doc.get("resident_id")}) if flat_doc.get("resident_id") else None
            bills = list(db.bills.find({"flat": selected_flat_number}).sort("created_at", -1).limit(5))
            complaints = list(db.complaints.find({"flat": selected_flat_number}).sort("created_at", -1).limit(5))
            bookings = list(db.bookings.find({"flat": selected_flat_number}).sort("created_at", -1).limit(5))
            flat_details = {
                "flat": flat_doc,
                "resident": resident,
                "bills": bills,
                "complaints": complaints,
                "bookings": bookings
            }

    return render_template(
        "manager/residents.html",
        blocks=blocks,
        selected_block=selected_block,
        total_flats=total_flats,
        occupied_flats=occupied_flats,
        vacant_flats=vacant_flats,
        total_residents=total_residents,
        open_complaints=open_complaints,
        pending_bills_count=pending_bills_count,
        flats=flats,
        flat_details=flat_details
    )

@manager_bp.route("/residents/register", methods=["POST"])
def register_resident():
    """Manager registers / onboards a new resident to a flat."""
    db = get_db()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "resident123")
    block = request.form.get("block", "").strip().upper()
    flat = request.form.get("flat", "").strip().upper()
    resident_type = request.form.get("resident_type", "OWNER").upper()

    if not name or not email or not phone or not flat:
        flash("Name, email, phone, and flat number are required.", "danger")
        return redirect(url_for("manager.block_residents", block=block))

    # Check if flat is already occupied
    flat_doc = db.flats.find_one({"flat_number": flat})
    if not flat_doc:
        flash(f"Flat {flat} not found in society.", "danger")
        return redirect(url_for("manager.block_residents", block=block))

    if flat_doc.get("status") == "OCCUPIED" and flat_doc.get("resident_id"):
        flash(f"Flat {flat} is already occupied by {flat_doc.get('resident_name')}.", "danger")
        return redirect(url_for("manager.block_residents", block=block, flat=flat))

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

    success, msg, user = create_user(data, creator_role="MANAGER")
    if success:
        log_action(session["user_id"], session["name"], "MANAGER", "REGISTER_RESIDENT", "USER", user["user_id"], f"Onboarded resident {name} to Flat {flat}")
        flash(f"Resident {name} ({user['user_id']}) successfully registered and assigned to Flat {flat}.", "success")
    else:
        flash(msg, "danger")

    return redirect(url_for("manager.block_residents", block=block, flat=flat))

@manager_bp.route("/residents/<user_id>/update", methods=["POST"])
def update_resident(user_id):
    """Manager updates resident details."""
    db = get_db()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    resident_type = request.form.get("resident_type", "OWNER").upper()
    block = request.form.get("block", "A")

    user = db.users.find_one({"user_id": user_id})
    if not user:
        flash("Resident record not found.", "danger")
        return redirect(url_for("manager.block_residents", block=block))

    db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "name": name,
            "email": email,
            "phone": phone,
            "resident_type": resident_type,
            "updated_at": datetime.now()
        }}
    )
    if user.get("flat"):
        db.flats.update_one(
            {"flat_number": user["flat"]},
            {"$set": {"resident_name": name}}
        )

    log_action(session["user_id"], session["name"], "MANAGER", "UPDATE_RESIDENT", "USER", user_id, f"Updated resident details for {name}")
    flash(f"Resident profile for {name} ({user_id}) updated successfully.", "success")
    return redirect(url_for("manager.block_residents", block=user.get("block", block), flat=user.get("flat")))

@manager_bp.route("/residents/vacate/<flat_number>", methods=["POST"])
def vacate_flat(flat_number):
    """Manager unlinks resident and marks flat vacant."""
    db = get_db()
    flat_doc = db.flats.find_one({"flat_number": flat_number})
    if not flat_doc:
        flash(f"Flat {flat_number} not found.", "danger")
        return redirect(url_for("manager.block_residents"))

    old_res_id = flat_doc.get("resident_id")
    old_res_name = flat_doc.get("resident_name")

    db.flats.update_one(
        {"flat_number": flat_number},
        {"$set": {
            "status": "VACANT",
            "resident_id": None,
            "resident_name": None
        }}
    )

    if old_res_id:
        db.users.update_one(
            {"user_id": old_res_id},
            {"$set": {
                "flat": "",
                "status": "INACTIVE",
                "updated_at": datetime.now()
            }}
        )

    log_action(session["user_id"], session["name"], "MANAGER", "VACATE_FLAT", "FLAT", flat_number, f"Vacated Flat {flat_number} (formerly {old_res_name})")
    flash(f"Flat {flat_number} has been marked VACANT. Resident {old_res_name or ''} unlinked.", "info")
    return redirect(url_for("manager.block_residents", block=flat_doc.get("block", "A")))
@manager_bp.route("/complaints")
def complaints():
    db = get_db()
    block_filter = request.args.get("block")
    category_filter = request.args.get("category")
    priority_filter = request.args.get("priority")
    status_filter = request.args.get("status")

    query = {}
    if block_filter:
        query["block"] = block_filter
    if category_filter:
        query["category"] = category_filter
    if priority_filter:
        query["priority"] = priority_filter
    if status_filter:
        query["status"] = status_filter

    complaints_list = list(db.complaints.find(query).sort("created_at", -1))
    technicians = list(db.users.find({"role": "TECHNICIAN", "status": "ACTIVE"}))
    vendors_list = list(db.vendors.find({"status": "ACTIVE"}).sort("company.name", 1))
    work_reports = list(db.service_work_reports.find().sort("submitted_at", -1))

    return render_template(
        "manager/complaints.html",
        complaints=complaints_list,
        technicians=technicians,
        vendors=vendors_list,
        work_reports=work_reports,
        categories=CATEGORIES,
        priorities=PRIORITIES,
        statuses=STATUSES,
        filters={
            "block": block_filter,
            "category": category_filter,
            "priority": priority_filter,
            "status": status_filter
        }
    )

@manager_bp.route("/complaints/<complaint_id>/assign", methods=["POST"])
def assign_complaint_technician(complaint_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    tech_id = request.form.get("technician_id")
    priority = request.form.get("priority")

    success, msg = assign_technician(complaint_id, tech_id, mgr, priority)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("manager.complaints"))

@manager_bp.route("/complaints/<complaint_id>/approve-work", methods=["POST"])
def approve_complaint_work(complaint_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    success, msg = approve_work_report(mgr, complaint_id)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("manager.complaints"))

@manager_bp.route("/complaints/<complaint_id>/reopen", methods=["POST"])
def reopen_complaint_route(complaint_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    notes = request.form.get("notes", "Manager requested rework.")
    success, msg = reopen_complaint(mgr, complaint_id, notes)
    if success:
        flash(msg, "warning")
    else:
        flash(msg, "danger")
    return redirect(url_for("manager.complaints"))

@manager_bp.route("/technicians")
def technicians():
    techs = get_technician_workload_list()
    return render_template("manager/technicians.html", technicians=techs)

from services.booking_service import approve_booking, reject_booking, verify_booking_conflict_for_manager

# ----------------- AMENITY BOOKINGS (Section 22 & 23) ----------------- #
@manager_bp.route("/amenity-bookings")
def amenity_bookings():
    db = get_db()
    status_filter = request.args.get("status")
    query = {}
    if status_filter:
        query["status"] = status_filter
    
    bookings_list = list(db.bookings.find(query).sort("created_at", -1))
    for b in bookings_list:
        b["conflict_check"] = verify_booking_conflict_for_manager(b)

    return render_template("manager/amenity_bookings.html", bookings=bookings_list, active_status=status_filter)

@manager_bp.route("/amenity-bookings/<booking_id>/approve", methods=["POST"])
def approve_amenity_booking(booking_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    remarks = request.form.get("remarks", "")
    success, msg = approve_booking(booking_id, mgr, remarks)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("manager.amenity_bookings"))

@manager_bp.route("/amenity-bookings/<booking_id>/reject", methods=["POST"])
def reject_amenity_booking(booking_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    reason = request.form.get("reason", "")
    success, msg = reject_booking(booking_id, mgr, reason)
    if success:
        flash(msg, "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("manager.amenity_bookings"))

@manager_bp.route("/amenities", methods=["GET", "POST"])
def manage_amenities():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            amn_id = get_next_sequence("amenity", prefix="AMN", padding=3)
            op_type = request.form.get("op_type", "24_HOURS")
            op_hours = {"type": op_type}
            if op_type == "FIXED":
                op_hours["open"] = request.form.get("open_time", "10:00")
                op_hours["close"] = request.form.get("close_time", "18:00")

            doc = {
                "amenity_id": amn_id,
                "name": request.form.get("name", "").strip(),
                "description": request.form.get("description", "").strip(),
                "capacity": int(request.form.get("capacity", 50)),
                "max_duration_hours": int(request.form.get("max_duration_hours", 4)),
                "requires_approval": request.form.get("requires_approval") == "on",
                "is_active": True,
                "icon": request.form.get("icon", "fa-building"),
                "operating_hours": op_hours,
                "rules": request.form.get("rules", "")
            }
            db.amenities.insert_one(doc)
            flash(f"Amenity {doc['name']} created.", "success")
        elif action == "toggle_status":
            amn_id = request.form.get("amenity_id")
            current = db.amenities.find_one({"amenity_id": amn_id})
            if current:
                new_state = not current.get("is_active", True)
                db.amenities.update_one({"amenity_id": amn_id}, {"$set": {"is_active": new_state}})
                flash(f"Amenity status updated to {'Active' if new_state else 'Maintenance'}.", "info")
        return redirect(url_for("manager.manage_amenities"))

    amenities_list = list(db.amenities.find())
    return render_template("manager/amenities.html", amenities=amenities_list)

# ----------------- BILLS & PAYMENTS ----------------- #
@manager_bp.route("/bills", methods=["GET", "POST"])
def bills():
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})

    if request.method == "POST":
        success, msg, _ = generate_bill(mgr, request.form)
        if success:
            flash(msg, "success")
        else:
            flash(msg, "danger")
        return redirect(url_for("manager.bills"))

    bills_list = list(db.bills.find().sort("created_at", -1))
    occupied_flats = list(db.flats.find({"status": "OCCUPIED"}).sort("flat_number", 1))
    payments_list = list(db.payments.find().sort("created_at", -1).limit(20))
    return render_template("manager/bills.html", bills=bills_list, occupied_flats=occupied_flats, payments=payments_list)

# ----------------- VISITORS ----------------- #
@manager_bp.route("/visitors")
def visitors():
    db = get_db()
    visitors_list = list(db.visitors.find().sort("created_at", -1).limit(50))
    return render_template("manager/visitors.html", visitors=visitors_list)

# ----------------- ANNOUNCEMENTS ----------------- #
@manager_bp.route("/announcements", methods=["GET", "POST"])
def announcements():
    db = get_db()
    if request.method == "POST":
        ann_id = get_next_sequence("announcement", prefix="ANN", padding=3)
        doc = {
            "announcement_id": ann_id,
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "target": request.form.get("target", "ALL"),
            "priority": request.form.get("priority", "MEDIUM"),
            "published_by": f"{session['name']} (Manager)",
            "publish_date": datetime.now().strftime("%Y-%m-%d"),
            "expiry_date": request.form.get("expiry_date", ""),
            "created_at": datetime.now()
        }
        db.announcements.insert_one(doc)
        log_action(session["user_id"], session["name"], "MANAGER", "CREATE_ANNOUNCEMENT", "ANNOUNCEMENT", ann_id, doc["title"])
        flash(f"Notice {ann_id} published successfully.", "success")
        return redirect(url_for("manager.announcements"))

    notices = list(db.announcements.find().sort("created_at", -1))
    return render_template("manager/announcements.html", announcements=notices)

# ----------------- MONGODB ANALYTICS (Section 30 & 44) ----------------- #
@manager_bp.route("/analytics")
def analytics():
    return render_template("manager/analytics.html")

@manager_bp.route("/api/analytics-data")
def api_analytics_data():
    data = get_analytics_charts_data()
    return jsonify(data)

# ----------------- AUDIT LOGS ----------------- #
@manager_bp.route("/audit-logs")
def audit_logs():
    logs = get_recent_logs(100)
    return render_template("manager/audit_logs.html", logs=logs)

# ----------------- PARKING MANAGEMENT (Section 12 & 13) ----------------- #
@manager_bp.route("/parking", methods=["GET", "POST"])
def parking_management():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "release":
            veh_id = request.form.get("vehicle_id")
            success, msg, _ = release_vehicle(veh_id)
            if success:
                log_action(session["user_id"], session["name"], "MANAGER", "RELEASE_PARKING_SLOT", "VEHICLE", veh_id, msg)
                flash(msg, "success")
            else:
                flash(msg, "danger")
            return redirect(url_for("manager.parking_management"))

    search_query = request.args.get("search", "").strip()
    block_filter = request.args.get("block", "ALL").strip()
    status_filter = request.args.get("status", "ALL").strip()

    data = get_parking_overview(search_query=search_query, block_filter=block_filter, status_filter=status_filter)
    blocks = list(db.blocks.find())

    return render_template(
        "manager/parking.html",
        total_slots=data["total_slots"],
        occupied_slots=data["occupied_slots"],
        available_slots=data["available_slots"],
        occupancy_rate=data["occupancy_rate"],
        duplicates=data["duplicates"],
        slots=data["slots"],
        blocks=blocks,
        selected_block=block_filter,
        selected_status=status_filter,
        search_query=search_query
    )

