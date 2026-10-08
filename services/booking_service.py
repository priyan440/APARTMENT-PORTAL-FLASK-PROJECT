from datetime import datetime, timedelta, date, time
from config import Config
from database.mongodb import get_db, get_next_sequence
from services.notification_service import create_notification
from services.audit_service import log_action
from services.receipt_service import generate_qr_code_base64

def time_to_minutes(time_str: str) -> int:
    """Converts 'HH:MM' string to total minutes from midnight."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])

def expire_stale_pending_bookings():
    """Expire PENDING bookings that have exceeded configured expiry limit."""
    db = get_db()
    expiry_limit_minutes = Config.PENDING_BOOKING_EXPIRY_MINUTES
    cutoff_time = datetime.now() - timedelta(minutes=expiry_limit_minutes)
    
    stale_bookings = list(db.bookings.find({
        "status": "PENDING",
        "created_at": {"$lt": cutoff_time}
    }))
    
    for bk in stale_bookings:
        db.bookings.update_one(
            {"_id": bk["_id"]},
            {"$set": {
                "status": "EXPIRED",
                "updated_at": datetime.now(),
                "cancellation_reason": f"Pending approval expired after {expiry_limit_minutes} minutes without manager action."
            }}
        )
        create_notification(
            user_id=bk["resident_id"],
            title="Amenity Booking Request Expired",
            message=f"Your booking request {bk['booking_id']} for {bk['amenity_name']} on {bk['booking_date']} has expired due to pending timeout.",
            link="/resident/bookings",
            n_type="WARNING"
        )

def check_booking_conflict(amenity_id: str, booking_date: str, requested_start: str, requested_end: str, exclude_booking_id: str = None) -> tuple[bool, str]:
    """
    Checks for overlapping bookings for same amenity and date.
    Strict overlap rule: existing_start < requested_end AND existing_end > requested_start
    Checks both PENDING and APPROVED bookings.
    """
    db = get_db()
    expire_stale_pending_bookings() # Cleanup first

    req_start_min = time_to_minutes(requested_start)
    req_end_min = time_to_minutes(requested_end)

    query = {
        "amenity_id": amenity_id,
        "booking_date": booking_date,
        "status": {"$in": ["PENDING", "APPROVED"]}
    }
    if exclude_booking_id:
        query["booking_id"] = {"$ne": exclude_booking_id}

    existing_bookings = list(db.bookings.find(query))
    for eb in existing_bookings:
        eb_start_min = time_to_minutes(eb["start_time"])
        eb_end_min = time_to_minutes(eb["end_time"])

        # Overlap check
        if eb_start_min < req_end_min and eb_end_min > req_start_min:
            status_text = "awaiting manager approval" if eb["status"] == "PENDING" else "already confirmed/approved"
            return True, f"This time slot ({eb['start_time']} - {eb['end_time']}) is {status_text}. Please select another time."

    return False, ""

def validate_and_create_booking(resident: dict, data: dict) -> tuple[bool, str, dict]:
    """Validates all booking conditions and creates booking."""
    db = get_db()
    expire_stale_pending_bookings()

    amenity_id = data.get("amenity_id")
    booking_date = data.get("booking_date") # YYYY-MM-DD
    start_time = data.get("start_time")     # HH:MM
    end_time = data.get("end_time")         # HH:MM
    purpose = data.get("purpose", "").strip()
    guests_count = int(data.get("guests_count", 1))

    if not amenity_id or not booking_date or not start_time or not end_time:
        return False, "Amenity, date, start time, and end time are required.", None

    amenity = db.amenities.find_one({"amenity_id": amenity_id})
    if not amenity:
        return False, "Selected amenity not found.", None

    if not amenity.get("is_active", True):
        return False, "This amenity is currently unavailable or under maintenance.", None

    # Validate date
    try:
        b_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
        if b_date < date.today():
            return False, "Booking date cannot be in the past.", None
    except ValueError:
        return False, "Invalid date format. Use YYYY-MM-DD.", None

    # Validate times
    try:
        start_min = time_to_minutes(start_time)
        end_min = time_to_minutes(end_time)
    except Exception:
        return False, "Invalid time format. Use HH:MM.", None

    if start_min >= end_min:
        return False, "End time must be later than start time.", None

    duration_hours = (end_min - start_min) / 60.0
    max_duration = amenity.get("max_duration_hours", 4)
    if duration_hours > max_duration:
        return False, f"Maximum booking duration for {amenity['name']} is {max_duration} hours.", None

    # Validate operating hours
    op_hours = amenity.get("operating_hours", {"type": "24_HOURS"})
    if op_hours.get("type") == "FIXED":
        open_time = op_hours.get("open", "00:00")
        close_time = op_hours.get("close", "23:59")
        open_min = time_to_minutes(open_time)
        close_min = time_to_minutes(close_time)

        if start_min < open_min or end_min > close_min:
            return False, f"The selected time is outside operating hours ({open_time} to {close_time}).", None

    # Check capacity
    capacity = amenity.get("capacity", 50)
    if guests_count > capacity:
        return False, f"Guest count ({guests_count}) exceeds facility capacity ({capacity} people).", None

    # Check for conflicts
    has_conflict, conflict_msg = check_booking_conflict(amenity_id, booking_date, start_time, end_time)
    if has_conflict:
        return False, conflict_msg, None

    # Create Booking - ALL bookings MUST strictly be PENDING awaiting Manager verification & approval
    booking_id = get_next_sequence("booking", prefix="BK", padding=3)
    created_at = datetime.now()
    expires_at = created_at + timedelta(minutes=Config.PENDING_BOOKING_EXPIRY_MINUTES)

    booking_doc = {
        "booking_id": booking_id,
        "amenity_id": amenity_id,
        "amenity_name": amenity["name"],
        "resident_id": resident["user_id"],
        "resident_name": resident["name"],
        "flat": resident.get("flat", ""),
        "block": resident.get("block", ""),
        "booking_date": booking_date,
        "start_time": start_time,
        "end_time": end_time,
        "duration_hours": duration_hours,
        "purpose": purpose or "General Leisure / Family Event",
        "guests_count": guests_count,
        "status": "PENDING", # Strictly PENDING until verified & approved by Manager
        "created_at": created_at,
        "updated_at": created_at,
        "expires_at": expires_at,
        "approval": {
            "status": "PENDING",
            "approved_by": None,
            "approved_by_name": None,
            "approved_at": None,
            "remarks": "Awaiting Manager conflict verification & approval"
        },
        "receipt_number": None,
        "qr_code_data": None
    }

    db.bookings.insert_one(booking_doc)

    log_action(
        user_id=resident["user_id"],
        user_name=resident["name"],
        role="RESIDENT",
        action="BOOK_AMENITY_REQUEST",
        entity="BOOKING",
        entity_id=booking_id,
        details=f"Requested {amenity['name']} for {booking_date} ({start_time}-{end_time}). Held as PENDING for Manager review."
    )

    # Notify all Apartment Managers to verify conflicts and approve
    managers = list(db.users.find({"role": "MANAGER"}))
    for mgr in managers:
        create_notification(
            user_id=mgr["user_id"],
            title="Amenity Booking Awaiting Approval",
            message=f"{resident['name']} (Flat {resident.get('flat')}) requested {amenity['name']} for {booking_date} ({start_time}-{end_time}). Please verify conflict and approve.",
            link="/manager/amenity-bookings",
            n_type="WARNING"
        )

    msg = f"Booking request {booking_id} submitted! Slot is held as PENDING. The Apartment Manager will verify slot conflicts and review approval before your confirmed pass is issued."

    return True, msg, booking_doc

def verify_booking_conflict_for_manager(booking: dict) -> dict:
    """
    Detailed conflict diagnostics for Manager verification console.
    Checks for overlapping PENDING and APPROVED bookings on the same date and amenity.
    """
    db = get_db()
    expire_stale_pending_bookings()

    req_start_min = time_to_minutes(booking["start_time"])
    req_end_min = time_to_minutes(booking["end_time"])

    overlapping = list(db.bookings.find({
        "amenity_id": booking["amenity_id"],
        "booking_date": booking["booking_date"],
        "status": {"$in": ["PENDING", "APPROVED"]},
        "booking_id": {"$ne": booking["booking_id"]}
    }))

    conflicts = []
    for eb in overlapping:
        eb_start_min = time_to_minutes(eb["start_time"])
        eb_end_min = time_to_minutes(eb["end_time"])
        if eb_start_min < req_end_min and eb_end_min > req_start_min:
            conflicts.append(eb)

    if not conflicts:
        return {
            "has_conflict": False,
            "status": "CLEAR",
            "message": "Time slot verified! No overlapping bookings detected. Safe to approve."
        }
    
    # Conflict found
    approved_conflicts = [c for c in conflicts if c["status"] == "APPROVED"]
    pending_conflicts = [c for c in conflicts if c["status"] == "PENDING"]
    
    if approved_conflicts:
        conf_bk = approved_conflicts[0]
        return {
            "has_conflict": True,
            "status": "APPROVED_CONFLICT",
            "message": f"CRITICAL CONFLICT: Overlaps with already APPROVED booking {conf_bk['booking_id']} ({conf_bk['resident_name']}, {conf_bk['start_time']} - {conf_bk['end_time']}). Cannot approve this slot.",
            "conflicting_booking": conf_bk["booking_id"]
        }
    else:
        conf_bk = pending_conflicts[0]
        return {
            "has_conflict": True,
            "status": "PENDING_CONFLICT",
            "message": f"COMPETING PENDING REQUEST: Overlaps with pending request {conf_bk['booking_id']} ({conf_bk['resident_name']}, {conf_bk['start_time']} - {conf_bk['end_time']}). Manager must decide which resident gets priority.",
            "conflicting_booking": conf_bk["booking_id"]
        }

def approve_booking(booking_id: str, manager_user: dict, remarks: str = "") -> tuple[bool, str]:
    db = get_db()
    expire_stale_pending_bookings()

    booking = db.bookings.find_one({"booking_id": booking_id})
    if not booking:
        return False, "Booking not found."

    if booking["status"] == "APPROVED":
        return False, "Booking is already approved."

    if booking["status"] in ["REJECTED", "CANCELLED", "EXPIRED"]:
        return False, f"Cannot approve booking with status {booking['status']}."

    # Re-verify conflict in case another booking was approved in between
    has_conflict, conflict_msg = check_booking_conflict(
        amenity_id=booking["amenity_id"],
        booking_date=booking["booking_date"],
        requested_start=booking["start_time"],
        requested_end=booking["end_time"],
        exclude_booking_id=booking_id
    )
    if has_conflict:
        return False, f"Approval failed due to slot conflict: {conflict_msg}"

    receipt_number = f"RCP-{booking_id}"
    qr_code_data = generate_qr_code_base64({
        "booking_id": booking_id,
        "amenity": booking["amenity_name"],
        "date": booking["booking_date"],
        "time": f"{booking['start_time']}-{booking['end_time']}",
        "status": "APPROVED"
    })

    db.bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {
            "status": "APPROVED",
            "receipt_number": receipt_number,
            "qr_code_data": qr_code_data,
            "updated_at": datetime.now(),
            "approval": {
                "status": "APPROVED",
                "approved_by": manager_user["user_id"],
                "approved_by_name": manager_user["name"],
                "approved_at": datetime.now().isoformat(),
                "remarks": remarks or "Approved by management."
            }
        }}
    )

    create_notification(
        user_id=booking["resident_id"],
        title="Amenity Booking Approved!",
        message=f"Great news! Your booking {booking_id} for {booking['amenity_name']} on {booking['booking_date']} has been APPROVED. Receipt & QR generated.",
        link=f"/resident/bookings/{booking_id}/receipt",
        n_type="SUCCESS"
    )

    log_action(
        user_id=manager_user["user_id"],
        user_name=manager_user["name"],
        role=manager_user.get("role", "MANAGER"),
        action="APPROVE_BOOKING",
        entity="BOOKING",
        entity_id=booking_id,
        details=f"Approved booking {booking_id} for {booking['resident_name']}"
    )

    return True, f"Booking {booking_id} approved successfully! Slot receipt & QR code generated."

def reject_booking(booking_id: str, manager_user: dict, reason: str = "") -> tuple[bool, str]:
    db = get_db()
    booking = db.bookings.find_one({"booking_id": booking_id})
    if not booking:
        return False, "Booking not found."

    db.bookings.update_one(
        {"booking_id": booking_id},
        {"$set": {
            "status": "REJECTED",
            "updated_at": datetime.now(),
            "approval": {
                "status": "REJECTED",
                "approved_by": manager_user["user_id"],
                "approved_by_name": manager_user["name"],
                "approved_at": datetime.now().isoformat(),
                "remarks": reason or "Booking rejected by management."
            }
        }}
    )

    create_notification(
        user_id=booking["resident_id"],
        title="Amenity Booking Rejected",
        message=f"Your booking {booking_id} for {booking['amenity_name']} was rejected. Reason: {reason or 'Facility constraint'}",
        link="/resident/bookings",
        n_type="DANGER"
    )

    log_action(
        user_id=manager_user["user_id"],
        user_name=manager_user["name"],
        role=manager_user.get("role", "MANAGER"),
        action="REJECT_BOOKING",
        entity="BOOKING",
        entity_id=booking_id,
        details=f"Rejected booking {booking_id}. Reason: {reason}"
    )

    return True, f"Booking {booking_id} has been rejected."

def get_amenity_calendar_slots(amenity_id: str, booking_date: str):
    """Returns all existing reserved/pending slots for visual calendar display."""
    db = get_db()
    expire_stale_pending_bookings()
    return list(db.bookings.find({
        "amenity_id": amenity_id,
        "booking_date": booking_date,
        "status": {"$in": ["PENDING", "APPROVED"]}
    }, {"_id": 0, "booking_id": 1, "start_time": 1, "end_time": 1, "status": 1, "resident_name": 1}))
