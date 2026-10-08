from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response, send_file
from io import BytesIO
from datetime import datetime
from services.auth_service import login_required, role_required, hash_password, verify_password
from services.complaint_service import create_complaint, submit_service_rating, CATEGORIES, PRIORITIES
from services.booking_service import validate_and_create_booking, get_amenity_calendar_slots
from services.billing_service import process_test_payment
from services.security_service import create_expected_visitor, create_emergency_sos
from services.receipt_service import generate_booking_pdf, generate_payment_pdf
from services.notification_service import get_user_notifications, get_unread_count
from services.parking_service import (
    register_vehicle, update_vehicle, release_vehicle, get_parking_slots_status, check_parking_slot_conflict
)
from database.mongodb import get_db, get_next_sequence

resident_bp = Blueprint("resident", __name__, url_prefix="/resident")

@resident_bp.before_request
@login_required
@role_required("RESIDENT")
def check_resident_access():
    pass

@resident_bp.route("/dashboard")
def dashboard():
    db = get_db()
    user_id = session["user_id"]
    user = db.users.find_one({"user_id": user_id})

    # Stats cards
    pending_bill = db.bills.find_one({"resident_id": user_id, "status": "PENDING"})
    
    # Community Contributions
    pending_community_payments = list(db.community_collection_payments.find({
        "resident_id": user_id,
        "status": {"$in": ["PENDING", "OVERDUE"]}
    }))
    pending_community_amount = sum(float(p.get("total_amount", p.get("amount", 0))) for p in pending_community_payments)

    open_complaints_count = db.complaints.count_documents({
        "resident_id": user_id,
        "status": {"$in": ["OPEN", "ASSIGNED", "IN_PROGRESS"]}
    })
    upcoming_bookings = list(db.bookings.find({
        "resident_id": user_id,
        "status": {"$in": ["PENDING", "APPROVED"]}
    }).sort("booking_date", 1).limit(3))
    
    unread_notifs = get_unread_count(user_id)
    family_count = len(user.get("family_members", []))
    vehicle_count = len(user.get("vehicles", []))
    
    # Recent notices
    block = user.get("block", "A")
    announcements = list(db.announcements.find({
        "target": {"$in": ["ALL", f"BLOCK_{block}", block]}
    }).sort("created_at", -1).limit(4))

    recent_complaints = list(db.complaints.find({"resident_id": user_id}).sort("created_at", -1).limit(3))

    return render_template(
        "resident/dashboard.html",
        user=user,
        pending_bill=pending_bill,
        pending_community_payments=pending_community_payments,
        pending_community_amount=pending_community_amount,
        open_complaints_count=open_complaints_count,
        upcoming_bookings=upcoming_bookings,
        unread_notifs=unread_notifs,
        family_count=family_count,
        vehicle_count=vehicle_count,
        announcements=announcements,
        recent_complaints=recent_complaints
    )

# ----------------- PROFILE & EMBEDDED DOCUMENTS ----------------- #
@resident_bp.route("/profile", methods=["GET", "POST"])
def profile():
    db = get_db()
    user_id = session["user_id"]
    user = db.users.find_one({"user_id": user_id})

    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_details":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            db.users.update_one(
                {"user_id": user_id},
                {"$set": {"name": name, "phone": phone, "updated_at": datetime.now()}}
            )
            session["name"] = name
            flash("Profile details updated successfully.", "success")
        elif action == "change_password":
            current_pwd = request.form.get("current_password")
            new_pwd = request.form.get("new_password")
            confirm_pwd = request.form.get("confirm_password")
            if not verify_password(user["password"], current_pwd):
                flash("Incorrect current password.", "danger")
            elif new_pwd != confirm_pwd:
                flash("New passwords do not match.", "danger")
            elif len(new_pwd) < 6:
                flash("Password must be at least 6 characters.", "danger")
            else:
                db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"password": hash_password(new_pwd), "updated_at": datetime.now()}}
                )
                flash("Password updated successfully.", "success")
        return redirect(url_for("resident.profile"))

    return render_template("resident/profile.html", user=user)

@resident_bp.route("/family", methods=["GET", "POST"])
def family_members():
    db = get_db()
    user_id = session["user_id"]

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name = request.form.get("name", "").strip()
            relationship = request.form.get("relationship", "Other").strip()
            age = int(request.form.get("age", 0))
            mem_id = get_next_sequence("family_member", prefix="FAM", padding=3)

            new_member = {
                "member_id": mem_id,
                "name": name,
                "relationship": relationship,
                "age": age
            }
            db.users.update_one(
                {"user_id": user_id},
                {"$push": {"family_members": new_member}}
            )
            flash(f"Family member {name} added.", "success")
        elif action == "delete":
            member_id = request.form.get("member_id")
            db.users.update_one(
                {"user_id": user_id},
                {"$pull": {"family_members": {"member_id": member_id}}}
            )
            flash("Family member removed.", "info")
        return redirect(url_for("resident.family_members"))

    user = db.users.find_one({"user_id": user_id})
    return render_template("resident/family.html", family_members=user.get("family_members", []))

@resident_bp.route("/vehicles", methods=["GET", "POST"])
def vehicles():
    db = get_db()
    user_id = session["user_id"]
    user = db.users.find_one({"user_id": user_id})

    if request.method == "POST":
        is_json = request.is_json or request.headers.get("Accept") == "application/json"
        form_data = request.get_json() if request.is_json else request.form
        action = form_data.get("action", "add")

        if action == "add":
            success, msg_or_doc, code = register_vehicle(user, form_data)
            if is_json:
                return jsonify({
                    "success": success,
                    "message": msg_or_doc if not success else "Vehicle registered successfully.",
                    "data": msg_or_doc if success else None
                }), code
            if success:
                flash(f"Vehicle {form_data.get('registration_number', '').upper()} registered with Slot {form_data.get('parking_slot', '').upper()}.", "success")
            else:
                flash(msg_or_doc, "danger")

        elif action in ["edit", "update"]:
            veh_id = form_data.get("vehicle_id")
            success, msg, code = update_vehicle(veh_id, user, form_data)
            if is_json:
                return jsonify({"success": success, "message": msg}), code
            if success:
                flash(msg, "success")
            else:
                flash(msg, "danger")

        elif action in ["delete", "release"]:
            veh_id = form_data.get("vehicle_id")
            success, msg, code = release_vehicle(veh_id, user_id)
            if is_json:
                return jsonify({"success": success, "message": msg}), code
            if success:
                flash(msg, "info")
            else:
                flash(msg, "danger")

        return redirect(url_for("resident.vehicles"))

    # Fetch vehicles from db.vehicles (ACTIVE only) with fallback
    resident_vehicles = list(db.vehicles.find({"resident_id": user_id, "status": "ACTIVE"}).sort("created_at", -1))
    for v in resident_vehicles:
        if "_id" in v:
            v["_id"] = str(v["_id"])
    if not resident_vehicles:
        # Check in user document
        resident_vehicles = [v for v in user.get("vehicles", []) if v.get("status", "ACTIVE") == "ACTIVE"]

    parking_slots = get_parking_slots_status()
    return render_template("resident/vehicles.html", vehicles=resident_vehicles, parking_slots=parking_slots)

@resident_bp.route("/api/parking/available-slots", methods=["GET"])
def api_available_parking_slots():
    """API endpoint returning all parking slots with real-time MongoDB availability."""
    current_vehicle_id = request.args.get("vehicle_id")
    slots = get_parking_slots_status(current_vehicle_id=current_vehicle_id)
    return jsonify({
        "success": True,
        "total_slots": len(slots),
        "available_slots": [s for s in slots if not s["is_occupied"]],
        "slots": slots
    })

# ----------------- COMPLAINTS ----------------- #
@resident_bp.route("/complaints", methods=["GET", "POST"])
def complaints():
    db = get_db()
    user_id = session["user_id"]
    user = db.users.find_one({"user_id": user_id})

    if request.method == "POST":
        file = request.files.get("media")
        success, msg, _ = create_complaint(user, request.form, file)
        if success:
            flash(msg, "success")
        else:
            flash(msg, "danger")
        return redirect(url_for("resident.complaints"))

    status_filter = request.args.get("status")
    query = {"resident_id": user_id}
    if status_filter:
        query["status"] = status_filter

    user_complaints = list(db.complaints.find(query).sort("created_at", -1))
    return render_template(
        "resident/complaints.html",
        complaints=user_complaints,
        categories=CATEGORIES,
        priorities=PRIORITIES,
        active_status=status_filter
    )

@resident_bp.route("/complaints/<complaint_id>")
def complaint_detail(complaint_id):
    db = get_db()
    user_id = session["user_id"]
    complaint = db.complaints.find_one({"complaint_id": complaint_id, "resident_id": user_id})
    if not complaint:
        flash("Complaint not found.", "danger")
        return redirect(url_for("resident.complaints"))
    return render_template("resident/complaint_detail.html", complaint=complaint)

@resident_bp.route("/complaints/<complaint_id>/rate", methods=["POST"])
def rate_complaint(complaint_id):
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    rating = int(request.form.get("rating", 5))
    feedback = request.form.get("feedback", "").strip()

    success, msg = submit_service_rating(complaint_id, user, rating, feedback)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("resident.complaint_detail", complaint_id=complaint_id))

# ----------------- AMENITY BOOKING ----------------- #
@resident_bp.route("/amenities")
def amenities():
    db = get_db()
    amenities_list = list(db.amenities.find({"is_active": True}))
    return render_template("resident/amenities.html", amenities=amenities_list)

@resident_bp.route("/amenities/check-slots")
def check_slots():
    """AJAX endpoint for calendar view & collision avoidance."""
    amenity_id = request.args.get("amenity_id")
    booking_date = request.args.get("date")
    if not amenity_id or not booking_date:
        return jsonify([])
    slots = get_amenity_calendar_slots(amenity_id, booking_date)
    return jsonify(slots)

@resident_bp.route("/amenities/book", methods=["POST"])
def book_amenity():
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    success, msg, bk = validate_and_create_booking(user, request.form)
    if success:
        flash(msg, "success")
        return redirect(url_for("resident.bookings"))
    else:
        flash(msg, "danger")
        return redirect(url_for("resident.amenities"))

@resident_bp.route("/bookings")
def bookings():
    db = get_db()
    user_id = session["user_id"]
    user_bookings = list(db.bookings.find({"resident_id": user_id}).sort("created_at", -1))
    return render_template("resident/bookings.html", bookings=user_bookings)

@resident_bp.route("/bookings/<booking_id>/receipt")
def booking_receipt(booking_id):
    db = get_db()
    booking = db.bookings.find_one({"booking_id": booking_id, "resident_id": session["user_id"]})
    if not booking or booking.get("status") != "APPROVED":
        flash("Receipt is only available for approved bookings.", "warning")
        return redirect(url_for("resident.bookings"))
    return render_template("resident/booking_receipt.html", booking=booking)

@resident_bp.route("/bookings/<booking_id>/receipt/pdf")
def download_booking_pdf(booking_id):
    db = get_db()
    booking = db.bookings.find_one({"booking_id": booking_id, "resident_id": session["user_id"]})
    if not booking or booking.get("status") != "APPROVED":
        flash("PDF receipt is only available for approved bookings.", "warning")
        return redirect(url_for("resident.bookings"))
    pdf_bytes = generate_booking_pdf(booking)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Booking_Receipt_{booking_id}.pdf"
    )

# ----------------- BILLS & PAYMENTS ----------------- #
@resident_bp.route("/bills")
def bills():
    db = get_db()
    user_id = session["user_id"]
    bills_list = list(db.bills.find({"resident_id": user_id}).sort("created_at", -1))
    payments_list = list(db.payments.find({"resident_id": user_id}).sort("created_at", -1))
    return render_template("resident/bills.html", bills=bills_list, payments=payments_list)

@resident_bp.route("/bills/<bill_id>/pay", methods=["POST"])
def pay_bill(bill_id):
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    method = request.form.get("payment_method", "CARD")
    success, msg, _ = process_test_payment(user, bill_id, method)
    if success:
        flash(msg, "success")
        return redirect(url_for("resident.bill_receipt", bill_id=bill_id))
    else:
        flash(msg, "danger")
        return redirect(url_for("resident.bills"))

@resident_bp.route("/bills/<bill_id>/receipt")
def bill_receipt(bill_id):
    db = get_db()
    bill = db.bills.find_one({"bill_id": bill_id, "resident_id": session["user_id"]})
    if not bill or bill.get("status") != "PAID":
        flash("Receipt only available for settled bills.", "warning")
        return redirect(url_for("resident.bills"))
    payment = db.payments.find_one({"payment_id": bill.get("payment_id")})
    return render_template("resident/bill_receipt.html", bill=bill, payment=payment)

@resident_bp.route("/bills/<bill_id>/receipt/pdf")
def download_bill_pdf(bill_id):
    db = get_db()
    bill = db.bills.find_one({"bill_id": bill_id, "resident_id": session["user_id"]})
    if not bill or bill.get("status") != "PAID":
        flash("Receipt only available for settled bills.", "warning")
        return redirect(url_for("resident.bills"))
    payment = db.payments.find_one({"payment_id": bill.get("payment_id")}) or {}
    pdf_bytes = generate_payment_pdf(bill, payment)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Payment_Receipt_{bill_id}.pdf"
    )

# ----------------- VISITORS & DELIVERIES ----------------- #
@resident_bp.route("/visitors", methods=["GET", "POST"])
def visitors():
    db = get_db()
    user_id = session["user_id"]
    user = db.users.find_one({"user_id": user_id})

    if request.method == "POST":
        action = request.form.get("action")
        if action == "preauthorize":
            success, msg, _ = create_expected_visitor(user, request.form)
            if success:
                flash(msg, "success")
            else:
                flash(msg, "danger")
        elif action == "cancel":
            vis_id = request.form.get("visitor_id")
            db.visitors.update_one(
                {"visitor_id": vis_id, "resident_id": user_id, "status": "EXPECTED"},
                {"$set": {"status": "CANCELLED"}}
            )
            flash("Visitor invitation cancelled.", "info")
        return redirect(url_for("resident.visitors"))

    visitors_list = list(db.visitors.find({"resident_id": user_id}).sort("created_at", -1))
    deliveries_list = list(db.deliveries.find({"resident_id": user_id}).sort("created_at", -1))
    return render_template("resident/visitors.html", visitors=visitors_list, deliveries=deliveries_list)

# ----------------- ANNOUNCEMENTS & SOS ----------------- #
@resident_bp.route("/announcements")
def announcements():
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    block = user.get("block", "A")
    items = list(db.announcements.find({
        "target": {"$in": ["ALL", f"BLOCK_{block}", block]}
    }).sort("created_at", -1))
    return render_template("resident/announcements.html", announcements=items)

@resident_bp.route("/emergency", methods=["GET", "POST"])
def emergency():
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})

    if request.method == "POST":
        alert_type = request.form.get("alert_type", "Medical")
        notes = request.form.get("notes", "").strip()
        success, msg, _ = create_emergency_sos(user, alert_type, notes)
        if success:
            flash(msg, "danger")
        return redirect(url_for("resident.emergency"))

    active_alerts = list(db.emergency_alerts.find({"resident_id": user["user_id"]}).sort("created_at", -1).limit(5))
    return render_template("resident/emergency.html", active_alerts=active_alerts)
