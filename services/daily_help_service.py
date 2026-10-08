import uuid
from datetime import datetime, date, time
from database.mongodb import get_db, get_next_sequence
from services.notification_service import create_notification
from services.audit_service import log_action
from services.gridfs_service import save_file_to_gridfs

DAILY_HELP_TYPES = [
    "MAID",
    "COOK",
    "DRIVER",
    "CLEANER",
    "BABYSITTER",
    "CARETAKER",
    "NEWSPAPER",
    "MILK_DELIVERY",
    "OTHER"
]

DAYS_OF_WEEK = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
DAY_MAP = {0: "MON", 1: "TUE", 2: "WED", 3: "THU", 4: "FRI", 5: "SAT", 6: "SUN"}

VERIFICATION_STATUSES = ["PENDING", "APPROVED", "REJECTED"]
HELP_STATUSES = ["ACTIVE", "INACTIVE", "SUSPENDED", "BLOCKED"]


def register_daily_help(resident_user: dict, data: dict, photo_file=None, id_proof_file=None) -> tuple[bool, str, dict]:
    """Registers domestic daily help for a resident."""
    db = get_db()
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    service_type = data.get("service_type", "MAID").strip().upper()
    gender = data.get("gender", "Female").strip()
    address = data.get("address", "").strip()

    if not name or not phone:
        return False, "Name and phone number are required.", None

    if service_type not in DAILY_HELP_TYPES:
        service_type = "OTHER"

    # Working schedule
    working_days = data.getlist("working_days") if hasattr(data, "getlist") else data.get("working_days", [])
    if isinstance(working_days, str):
        working_days = [d.strip().upper() for d in working_days.split(",") if d.strip()]
    if not working_days:
        working_days = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]

    entry_time = data.get("entry_time", "08:00").strip()
    exit_time = data.get("exit_time", "11:00").strip()

    # Upload documents if provided
    photo_file_id = None
    id_proof_file_id = None

    if photo_file and photo_file.filename:
        try:
            saved_photo = save_file_to_gridfs(photo_file)
            if saved_photo:
                photo_file_id = saved_photo["file_id"]
        except Exception:
            pass

    if id_proof_file and id_proof_file.filename:
        try:
            saved_id = save_file_to_gridfs(id_proof_file)
            if saved_id:
                id_proof_file_id = saved_id["file_id"]
        except Exception:
            pass

    help_id = get_next_sequence("daily_help", prefix="HELP", padding=3)
    now = datetime.now()

    help_doc = {
        "help_id": help_id,
        "resident_id": resident_user["user_id"],
        "resident_name": resident_user["name"],
        "resident_phone": resident_user.get("phone", ""),
        "flat_id": resident_user.get("flat", "N/A"),
        "block": resident_user.get("block", "A"),
        "person": {
            "name": name,
            "phone": phone,
            "service_type": service_type,
            "gender": gender,
            "address": address,
            "emergency_contact": data.get("emergency_contact", "").strip()
        },
        "schedule": {
            "days": working_days,
            "entry_time": entry_time,
            "exit_time": exit_time
        },
        "documents": {
            "photo_file_id": photo_file_id,
            "id_proof_file_id": id_proof_file_id
        },
        "verification_status": "PENDING",  # PENDING, APPROVED, REJECTED
        "rejection_reason": None,
        "verified_by": None,
        "verified_at": None,
        "status": "ACTIVE",  # ACTIVE, INACTIVE, SUSPENDED, BLOCKED
        "notes": data.get("notes", "").strip(),
        "created_at": now,
        "updated_at": now
    }

    db.daily_help.insert_one(help_doc)

    # Notify managers for verification
    managers = list(db.users.find({"role": "MANAGER"}))
    for mgr in managers:
        create_notification(
            user_id=mgr["user_id"],
            title="Daily Help Verification Request",
            message=f"{resident_user['name']} (Flat {resident_user.get('flat')}) registered {name} as {service_type}. Verification needed.",
            link="/manager/daily-help",
            n_type="INFO"
        )

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="REGISTER_DAILY_HELP",
        entity="DAILY_HELP",
        entity_id=help_id,
        details=f"Registered domestic help {name} ({service_type}) for Flat {resident_user.get('flat')}"
    )

    return True, f"Daily Help {help_id} ({name}) registered successfully. Manager verification is pending.", help_doc


def update_daily_help(resident_user: dict, help_id: str, data: dict, photo_file=None, id_proof_file=None) -> tuple[bool, str]:
    db = get_db()
    dh = db.daily_help.find_one({"help_id": help_id, "resident_id": resident_user["user_id"]})
    if not dh:
        return False, "Daily Help record not found or does not belong to you."

    name = data.get("name", dh["person"]["name"]).strip()
    phone = data.get("phone", dh["person"]["phone"]).strip()
    service_type = data.get("service_type", dh["person"]["service_type"]).strip().upper()
    gender = data.get("gender", dh["person"].get("gender", "Female")).strip()
    address = data.get("address", dh["person"].get("address", "")).strip()

    working_days = data.getlist("working_days") if hasattr(data, "getlist") else data.get("working_days", dh["schedule"]["days"])
    if isinstance(working_days, str):
        working_days = [d.strip().upper() for d in working_days.split(",") if d.strip()]

    entry_time = data.get("entry_time", dh["schedule"].get("entry_time", "08:00")).strip()
    exit_time = data.get("exit_time", dh["schedule"].get("exit_time", "11:00")).strip()

    update_fields = {
        "person.name": name,
        "person.phone": phone,
        "person.service_type": service_type,
        "person.gender": gender,
        "person.address": address,
        "person.emergency_contact": data.get("emergency_contact", dh["person"].get("emergency_contact", "")).strip(),
        "schedule.days": working_days,
        "schedule.entry_time": entry_time,
        "schedule.exit_time": exit_time,
        "notes": data.get("notes", dh.get("notes", "")).strip(),
        "updated_at": datetime.now()
    }

    # If was rejected, reset to pending upon re-submission
    if dh.get("verification_status") == "REJECTED":
        update_fields["verification_status"] = "PENDING"
        update_fields["rejection_reason"] = None

    if photo_file and photo_file.filename:
        try:
            saved_p = save_file_to_gridfs(photo_file)
            if saved_p:
                update_fields["documents.photo_file_id"] = saved_p["file_id"]
        except Exception:
            pass

    if id_proof_file and id_proof_file.filename:
        try:
            saved_id = save_file_to_gridfs(id_proof_file)
            if saved_id:
                update_fields["documents.id_proof_file_id"] = saved_id["file_id"]
        except Exception:
            pass

    db.daily_help.update_one({"help_id": help_id}, {"$set": update_fields})

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="UPDATE_DAILY_HELP",
        entity="DAILY_HELP",
        entity_id=help_id,
        details=f"Updated details for daily help {help_id} ({name})"
    )

    return True, f"Daily Help {help_id} updated successfully."


def deactivate_daily_help(resident_user: dict, help_id: str) -> tuple[bool, str]:
    """Deactivates a daily help record without deleting historical attendance."""
    db = get_db()
    dh = db.daily_help.find_one({"help_id": help_id, "resident_id": resident_user["user_id"]})
    if not dh:
        return False, "Daily Help record not found."

    db.daily_help.update_one(
        {"help_id": help_id},
        {"$set": {"status": "INACTIVE", "updated_at": datetime.now()}}
    )

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="DEACTIVATE_DAILY_HELP",
        entity="DAILY_HELP",
        entity_id=help_id,
        details=f"Deactivated domestic help {dh['person']['name']} ({help_id})"
    )

    return True, f"Daily Help {dh['person']['name']} marked as Inactive."


# =========================================================================
# MANAGER VERIFICATION & STATUS
# =========================================================================

def verify_daily_help(manager_user: dict, help_id: str, action: str, reason: str = "") -> tuple[bool, str]:
    db = get_db()
    dh = db.daily_help.find_one({"help_id": help_id})
    if not dh:
        return False, "Daily Help record not found."

    now = datetime.now()
    action = action.upper()

    if action == "APPROVE":
        db.daily_help.update_one(
            {"help_id": help_id},
            {"$set": {
                "verification_status": "APPROVED",
                "verified_by": manager_user.get("user_id"),
                "verified_at": now.isoformat(),
                "status": "ACTIVE",
                "rejection_reason": None,
                "updated_at": now
            }}
        )
        # Notify resident
        create_notification(
            user_id=dh["resident_id"],
            title="✓ Daily Help Approved",
            message=f"{dh['person']['name']} ({dh['person']['service_type']}) has been verified and approved by management. Security gate access is now active.",
            link="/resident/daily-help",
            n_type="SUCCESS"
        )
        msg = f"Daily Help {dh['person']['name']} ({help_id}) approved successfully."

    elif action == "REJECT":
        if not reason:
            reason = "ID Proof / verification documents insufficient or unclear."
        db.daily_help.update_one(
            {"help_id": help_id},
            {"$set": {
                "verification_status": "REJECTED",
                "rejection_reason": reason,
                "verified_by": manager_user.get("user_id"),
                "verified_at": now.isoformat(),
                "status": "INACTIVE",
                "updated_at": now
            }}
        )
        create_notification(
            user_id=dh["resident_id"],
            title="⚠️ Daily Help Registration Rejected",
            message=f"Registration for {dh['person']['name']} was rejected: {reason}. Please update details.",
            link="/resident/daily-help",
            n_type="WARNING"
        )
        msg = f"Daily Help {dh['person']['name']} rejected. Reason: {reason}"

    elif action == "SUSPEND":
        db.daily_help.update_one(
            {"help_id": help_id},
            {"$set": {"status": "SUSPENDED", "status_reason": reason or "Suspended by manager", "updated_at": now}}
        )
        create_notification(
            user_id=dh["resident_id"],
            title="⚠️ Daily Help Access Suspended",
            message=f"Gate access for {dh['person']['name']} has been temporarily suspended by management.",
            link="/resident/daily-help",
            n_type="WARNING"
        )
        msg = f"Daily Help {dh['person']['name']} suspended."

    elif action == "REACTIVATE":
        db.daily_help.update_one(
            {"help_id": help_id},
            {"$set": {"status": "ACTIVE", "status_reason": None, "updated_at": now}}
        )
        msg = f"Daily Help {dh['person']['name']} reactivated."
    else:
        return False, f"Unknown verification action: {action}"

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action=f"{action}_DAILY_HELP",
        entity="DAILY_HELP",
        entity_id=help_id,
        details=f"{action} daily help {help_id} ({dh['person']['name']}). Notes: {reason}"
    )

    return True, msg


# =========================================================================
# SECURITY GATE CHECK-IN & ATTENDANCE
# =========================================================================

def get_todays_expected_daily_help() -> list:
    """Returns all approved, active daily help scheduled for today."""
    db = get_db()
    today_weekday = DAY_MAP[date.today().weekday()]
    today_str = date.today().strftime("%Y-%m-%d")

    helpers = list(db.daily_help.find({
        "verification_status": "APPROVED",
        "status": "ACTIVE",
        "schedule.days": today_weekday
    }).sort("schedule.entry_time", 1))

    # Decorate with today's attendance state
    for h in helpers:
        att = db.daily_help_attendance.find_one({"help_id": h["help_id"], "date": today_str})
        h["today_attendance"] = att

    return helpers


def security_search_daily_help(query_str: str) -> list:
    """Search helper by Name, Phone, Help ID, or Flat."""
    db = get_db()
    today_str = date.today().strftime("%Y-%m-%d")

    q = query_str.strip()
    if not q:
        return []

    regex = {"$regex": q, "$options": "i"}
    filter_doc = {
        "$or": [
            {"person.name": regex},
            {"person.phone": regex},
            {"help_id": regex},
            {"flat_id": regex}
        ]
    }

    results = list(db.daily_help.find(filter_doc).limit(30))
    for h in results:
        att = db.daily_help_attendance.find_one({"help_id": h["help_id"], "date": today_str})
        h["today_attendance"] = att

    return results


def daily_help_check_in(security_user: dict, help_id: str) -> tuple[bool, str, dict]:
    """Strict security check-in for approved active domestic help."""
    db = get_db()
    dh = db.daily_help.find_one({"help_id": help_id})
    if not dh:
        return False, "Daily Help record not found in system.", None

    # Strict Security Rules
    if dh.get("verification_status") != "APPROVED":
        return False, f"ACCESS DENIED: Verification status is {dh.get('verification_status')}. Manager approval is required before gate entry.", None

    if dh.get("status") != "ACTIVE":
        return False, f"ACCESS DENIED: Gate pass is {dh.get('status')} ({dh.get('status_reason', 'Not authorized')}). Cannot enter.", None

    today_str = date.today().strftime("%Y-%m-%d")
    now_time_str = datetime.now().strftime("%H:%M")

    # Check if already checked in today
    existing_att = db.daily_help_attendance.find_one({
        "help_id": help_id,
        "date": today_str,
        "status": "CHECKED_IN"
    })
    if existing_att:
        return False, "Daily Help is already checked in.", existing_att

    # Check if any prior attendance record exists today to update rather than creating multiple for the same day
    prior_att = db.daily_help_attendance.find_one({"help_id": help_id, "date": today_str})

    flat_val = dh.get("flat_id") or dh.get("flat") or "N/A"
    person_name = dh.get("person", {}).get("name", "Daily Help")
    service_type = dh.get("person", {}).get("service_type", "OTHER")
    phone = dh.get("person", {}).get("phone", "")

    now = datetime.now()

    if prior_att:
        db.daily_help_attendance.update_one(
            {"_id": prior_att["_id"]},
            {"$set": {
                "check_in": now_time_str,
                "check_out": None,
                "status": "CHECKED_IN",
                "flat_number": flat_val,
                "flat_id": flat_val,
                "person_name": person_name,
                "help_name": person_name,
                "updated_at": now
            }}
        )
        att_doc = db.daily_help_attendance.find_one({"_id": prior_att["_id"]})
    else:
        att_id = get_next_sequence("daily_help_attendance", prefix="ATT", padding=3)
        att_doc = {
            "attendance_id": att_id,
            "help_id": help_id,
            "resident_id": dh.get("resident_id"),
            "resident_name": dh.get("resident_name"),
            "flat_number": flat_val,
            "flat_id": flat_val,
            "block": dh.get("block", "A"),
            "person_name": person_name,
            "help_name": person_name,
            "service_type": service_type,
            "phone": phone,
            "date": today_str,
            "check_in": now_time_str,
            "check_out": None,
            "status": "CHECKED_IN",
            "logged_by_security": security_user.get("user_id") if security_user else None,
            "logged_by_name": security_user.get("name") if security_user else None,
            "created_at": now,
            "updated_at": now
        }
        db.daily_help_attendance.insert_one(att_doc)

    # Instant notification to resident
    if dh.get("resident_id"):
        create_notification(
            user_id=dh["resident_id"],
            title=f"🚪 Daily Help Arrived: {person_name}",
            message=f"{person_name} ({service_type}) has checked in at the apartment gate at {now.strftime('%I:%M %p')}.",
            link="/resident/daily-help",
            n_type="INFO"
        )

    if security_user:
        log_action(
            user_id=security_user.get("user_id"),
            user_name=security_user.get("name"),
            role=security_user.get("role", "SECURITY"),
            action="DAILY_HELP_CHECK_IN",
            entity="DAILY_HELP",
            entity_id=help_id,
            details=f"Gate check-in for {person_name} ({service_type}) -> Flat {flat_val}"
        )

    return True, f"Check-in recorded for {person_name} at {now_time_str}. Resident notified.", att_doc


def daily_help_check_out(security_user: dict, help_id: str) -> tuple[bool, str, dict]:
    """Gate check-out for domestic help (updates the SAME attendance record)."""
    db = get_db()
    dh = db.daily_help.find_one({"help_id": help_id})
    if not dh:
        return False, "Daily Help record not found in system.", None

    today_str = date.today().strftime("%Y-%m-%d")
    now_time_str = datetime.now().strftime("%H:%M")
    now = datetime.now()
    person_name = dh.get("person", {}).get("name", "Daily Help")
    service_type = dh.get("person", {}).get("service_type", "OTHER")

    # Find the active check-in record for today
    att = db.daily_help_attendance.find_one({"help_id": help_id, "date": today_str, "status": "CHECKED_IN"})
    if not att:
        # Fallback to any record for today
        att = db.daily_help_attendance.find_one({"help_id": help_id, "date": today_str})

    if not att:
        return False, f"No active check-in record found for {person_name} today.", None

    # Update the SAME attendance document (do NOT create another attendance document)
    db.daily_help_attendance.update_one(
        {"_id": att["_id"]},
        {"$set": {
            "check_out": now_time_str,
            "status": "CHECKED_OUT",
            "updated_at": now
        }}
    )

    # Instant notification to resident
    if dh.get("resident_id"):
        create_notification(
            user_id=dh["resident_id"],
            title=f"🚪 Daily Help Left: {person_name}",
            message=f"{person_name} ({service_type}) has checked out through the apartment gate at {now.strftime('%I:%M %p')}.",
            link="/resident/daily-help",
            n_type="INFO"
        )

    if security_user:
        log_action(
            user_id=security_user.get("user_id"),
            user_name=security_user.get("name"),
            role=security_user.get("role", "SECURITY"),
            action="DAILY_HELP_CHECK_OUT",
            entity="DAILY_HELP",
            entity_id=help_id,
            details=f"Gate check-out for {person_name} at {now_time_str}"
        )

    updated_att = db.daily_help_attendance.find_one({"_id": att["_id"]})
    return True, f"Check-out recorded for {person_name} at {now_time_str}. Resident notified.", updated_att


# =========================================================================
# DAILY HELP ANALYTICS & STATS
# =========================================================================

def get_daily_help_analytics() -> dict:
    """MongoDB Aggregations for Daily Help."""
    db = get_db()
    today_str = date.today().strftime("%Y-%m-%d")

    total_count = db.daily_help.count_documents({})
    approved_count = db.daily_help.count_documents({"verification_status": "APPROVED", "status": "ACTIVE"})
    pending_count = db.daily_help.count_documents({"verification_status": "PENDING"})
    suspended_count = db.daily_help.count_documents({"status": "SUSPENDED"})
    inactive_count = db.daily_help.count_documents({"status": "INACTIVE"})

    # Attendance stats for today
    currently_inside = db.daily_help_attendance.count_documents({"date": today_str, "status": "CHECKED_IN"})
    completed_visits_today = db.daily_help_attendance.count_documents({"date": today_str, "status": "COMPLETED"})

    # By category
    cat_pipeline = [
        {"$group": {"_id": "$person.service_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    by_category = list(db.daily_help.aggregate(cat_pipeline))

    # Block-wise daily help count
    block_pipeline = [
        {"$group": {"_id": "$block", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    by_block = list(db.daily_help.aggregate(block_pipeline))

    return {
        "total_count": total_count,
        "total_help": total_count,
        "approved_count": approved_count,
        "active_help": approved_count,
        "pending_count": pending_count,
        "pending_verification": pending_count,
        "suspended_count": suspended_count,
        "suspended_help": suspended_count,
        "inactive_count": inactive_count,
        "inactive_help": inactive_count,
        "currently_inside": currently_inside,
        "completed_visits_today": completed_visits_today,
        "today_entries": currently_inside + completed_visits_today,
        "today_exits": completed_visits_today,
        "by_category": by_category,
        "by_block": by_block
    }
