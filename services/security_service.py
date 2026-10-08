from datetime import datetime
from database.mongodb import get_db, get_next_sequence
from services.notification_service import create_notification
from services.audit_service import log_action

def create_expected_visitor(resident_user: dict, data: dict) -> tuple[bool, str, dict]:
    db = get_db()
    name = data.get("visitor_name", "").strip()
    phone = data.get("phone", "").strip()
    purpose = data.get("purpose", "Guest").strip()
    expected_date = data.get("expected_date", "").strip()
    expected_time = data.get("expected_time", "").strip()

    if not name or not expected_date:
        return False, "Visitor name and expected date are required.", None

    visitor_id = get_next_sequence("visitor", prefix="VIS", padding=3)
    doc = {
        "visitor_id": visitor_id,
        "visitor_name": name,
        "phone": phone,
        "purpose": purpose,
        "expected_date": expected_date,
        "expected_time": expected_time,
        "check_in_time": None,
        "check_out_time": None,
        "status": "EXPECTED", # EXPECTED, CHECKED_IN, CHECKED_OUT
        "flat": resident_user.get("flat", ""),
        "block": resident_user.get("block", ""),
        "resident_id": resident_user["user_id"],
        "resident_name": resident_user["name"],
        "vehicle_number": data.get("vehicle_number", "").strip(),
        "created_at": datetime.now()
    }
    db.visitors.insert_one(doc)

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="PREAUTHORIZE_VISITOR",
        entity="VISITOR",
        entity_id=visitor_id,
        details=f"Invited visitor {name} for {expected_date}"
    )

    return True, f"Visitor pass {visitor_id} created for {name}.", doc

def check_in_visitor(security_user: dict, visitor_id: str = None, walk_in_data: dict = None) -> tuple[bool, str, dict]:
    db = get_db()
    now = datetime.now()

    if visitor_id:
        visitor = db.visitors.find_one({"visitor_id": visitor_id})
        if not visitor:
            return False, "Visitor record not found.", None
        
        db.visitors.update_one(
            {"visitor_id": visitor_id},
            {"$set": {"status": "CHECKED_IN", "check_in_time": now.isoformat()}}
        )

        create_notification(
            user_id=visitor["resident_id"],
            title="Visitor Arrived!",
            message=f"Your expected guest {visitor['visitor_name']} has checked in at the main security gate.",
            link="/resident/visitors",
            n_type="INFO"
        )

        log_action(
            user_id=security_user["user_id"],
            user_name=security_user["name"],
            role="SECURITY",
            action="VISITOR_CHECK_IN",
            entity="VISITOR",
            entity_id=visitor_id,
            details=f"Checked in {visitor['visitor_name']} for Flat {visitor.get('flat')}"
        )
        return True, f"Visitor {visitor['visitor_name']} checked in.", visitor

    elif walk_in_data:
        # Walk-in visitor
        flat_number = walk_in_data.get("flat", "").strip().upper()
        resident = db.users.find_one({"role": "RESIDENT", "flat": flat_number})
        if not resident:
            return False, f"Flat {flat_number} does not have an active registered resident.", None

        new_id = get_next_sequence("visitor", prefix="VIS", padding=3)
        doc = {
            "visitor_id": new_id,
            "visitor_name": walk_in_data.get("visitor_name", "").strip(),
            "phone": walk_in_data.get("phone", "").strip(),
            "purpose": walk_in_data.get("purpose", "Delivery / Walk-in").strip(),
            "expected_date": now.strftime("%Y-%m-%d"),
            "expected_time": now.strftime("%H:%M"),
            "check_in_time": now.isoformat(),
            "check_out_time": None,
            "status": "CHECKED_IN",
            "flat": flat_number,
            "block": resident.get("block", ""),
            "resident_id": resident["user_id"],
            "resident_name": resident["name"],
            "vehicle_number": walk_in_data.get("vehicle_number", "").strip(),
            "created_at": now
        }
        db.visitors.insert_one(doc)

        create_notification(
            user_id=resident["user_id"],
            title="Visitor Arrival at Security Gate",
            message=f"{doc['visitor_name']} has checked in to visit your flat {flat_number}.",
            link="/resident/visitors",
            n_type="INFO"
        )
        return True, f"Walk-in visitor {doc['visitor_name']} logged and checked in.", doc

    return False, "Invalid check-in request.", None

def check_out_visitor(security_user: dict, visitor_id: str) -> tuple[bool, str]:
    db = get_db()
    visitor = db.visitors.find_one({"visitor_id": visitor_id})
    if not visitor:
        return False, "Visitor record not found."

    db.visitors.update_one(
        {"visitor_id": visitor_id},
        {"$set": {
            "status": "CHECKED_OUT",
            "check_out_time": datetime.now().isoformat()
        }}
    )
    return True, f"Visitor {visitor['visitor_name']} checked out."

def record_delivery(security_user: dict, data: dict) -> tuple[bool, str, dict]:
    db = get_db()
    flat_number = data.get("flat", "").strip().upper()
    resident = db.users.find_one({"role": "RESIDENT", "flat": flat_number})
    if not resident:
        return False, f"Resident for Flat {flat_number} not found.", None

    del_id = get_next_sequence("delivery", prefix="DEL", padding=3)
    now = datetime.now()
    doc = {
        "delivery_id": del_id,
        "company": data.get("company", "Amazon / Courier").strip(),
        "delivery_person": data.get("delivery_person", "").strip(),
        "flat": flat_number,
        "block": resident.get("block", ""),
        "resident_id": resident["user_id"],
        "resident_name": resident["name"],
        "parcel_details": data.get("parcel_details", "Parcel at gate").strip(),
        "arrival_time": now.isoformat(),
        "collected_at": None,
        "status": "RECEIVED", # RECEIVED, COLLECTED
        "logged_by": security_user["name"],
        "created_at": now
    }
    db.deliveries.insert_one(doc)

    create_notification(
        user_id=resident["user_id"],
        title="Parcel Arrived at Gate",
        message=f"A parcel from {doc['company']} ({doc['parcel_details']}) was received by Security.",
        link="/resident/deliveries",
        n_type="INFO"
    )

    return True, f"Delivery {del_id} logged successfully.", doc

def create_emergency_sos(resident_user: dict, alert_type: str, notes: str = "") -> tuple[bool, str, dict]:
    db = get_db()
    sos_id = get_next_sequence("emergency_alert", prefix="SOS", padding=3)
    now = datetime.now()

    doc = {
        "alert_id": sos_id,
        "resident_id": resident_user["user_id"],
        "resident_name": resident_user["name"],
        "resident_phone": resident_user.get("phone", ""),
        "flat": resident_user.get("flat", ""),
        "block": resident_user.get("block", ""),
        "alert_type": alert_type, # Medical, Fire, Security, Electrical, Other
        "notes": notes,
        "status": "ACTIVE", # ACTIVE, RESOLVED
        "created_at": now,
        "resolved_at": None
    }
    db.emergency_alerts.insert_one(doc)

    # Notify all Managers and Security personnel
    staff = list(db.users.find({"role": {"$in": ["MANAGER", "SECURITY"]}}))
    for s in staff:
        create_notification(
            user_id=s["user_id"],
            title=f"EMERGENCY SOS: {alert_type.upper()} ALERT!",
            message=f"CRITICAL: {alert_type} SOS triggered at Flat {resident_user.get('flat')} by {resident_user['name']} (Ph: {resident_user.get('phone')})!",
            link="/security/emergency",
            n_type="DANGER"
        )

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="TRIGGER_SOS",
        entity="EMERGENCY_ALERT",
        entity_id=sos_id,
        details=f"Triggered {alert_type} SOS at Flat {resident_user.get('flat')}"
    )

    return True, f"Emergency alert {sos_id} dispatched immediately to Security and Management.", doc
