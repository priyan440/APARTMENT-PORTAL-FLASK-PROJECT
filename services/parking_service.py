import pymongo
from datetime import datetime
from database.mongodb import get_db, get_next_sequence
from services.audit_service import log_action

# Standard designated parking slots in the residential community
DEFAULT_PARKING_SLOTS = (
    [f"P-A{str(i).zfill(2)}" for i in range(1, 26)] +
    [f"P-B{str(i).zfill(2)}" for i in range(1, 26)] +
    [f"B-{str(i).zfill(2)}" for i in range(1, 21)] +
    [f"P-C{str(i).zfill(2)}" for i in range(1, 26)] +
    [f"P-D{str(i).zfill(2)}" for i in range(1, 26)]
)

def get_slot_block(slot_name: str) -> str:
    """Infer block identifier from slot name."""
    slot_upper = slot_name.upper()
    if "P-A" in slot_upper or slot_upper.startswith("A-"):
        return "Block A"
    elif "P-B" in slot_upper or slot_upper.startswith("B-"):
        return "Block B"
    elif "P-C" in slot_upper or slot_upper.startswith("C-"):
        return "Block C"
    elif "P-D" in slot_upper or slot_upper.startswith("D-"):
        return "Block D"
    return "General / Visitor"

def check_parking_slot_conflict(parking_slot: str, exclude_vehicle_id: str = None) -> dict:
    """
    Check if a parking slot is already assigned to an ACTIVE vehicle in MongoDB.
    Returns the conflicting vehicle document if found, else None.
    """
    if not parking_slot:
        return None
    
    db = get_db()
    slot_clean = parking_slot.strip().upper()
    
    query = {
        "parking_slot": slot_clean,
        "status": "ACTIVE"
    }
    if exclude_vehicle_id:
        query["vehicle_id"] = {"$ne": exclude_vehicle_id}
    
    # 1. Primary check on dedicated vehicles collection
    existing_veh = db.vehicles.find_one(query)
    if existing_veh:
        return existing_veh
    
    # 2. Fallback check across users.vehicles array (ensuring backward compatibility)
    user_query = {
        "status": "ACTIVE",
        "vehicles": {
            "$elemMatch": {
                "parking_slot": slot_clean,
                **({"vehicle_id": {"$ne": exclude_vehicle_id}} if exclude_vehicle_id else {})
            }
        }
    }
    conflicting_user = db.users.find_one(user_query)
    if conflicting_user:
        # Find the specific vehicle in user's array
        for v in conflicting_user.get("vehicles", []):
            if v.get("parking_slot", "").upper() == slot_clean:
                if not exclude_vehicle_id or v.get("vehicle_id") != exclude_vehicle_id:
                    return {
                        "vehicle_id": v.get("vehicle_id", "N/A"),
                        "resident_id": conflicting_user.get("user_id"),
                        "resident_name": conflicting_user.get("name"),
                        "flat": conflicting_user.get("flat"),
                        "block": conflicting_user.get("block"),
                        "parking_slot": slot_clean,
                        "type": v.get("type", "Vehicle"),
                        "registration_number": v.get("registration_number", "N/A"),
                        "status": "ACTIVE"
                    }
    
    return None

def get_all_active_occupied_slots() -> dict:
    """Returns a dictionary mapping uppercase parking_slot -> vehicle document."""
    db = get_db()
    occupied = {}
    
    # From db.vehicles
    for veh in db.vehicles.find({"status": "ACTIVE", "parking_slot": {"$ne": None}}):
        slot = veh["parking_slot"].strip().upper()
        occupied[slot] = veh
        
    # From db.users.vehicles
    for u in db.users.find({"status": "ACTIVE", "vehicles": {"$exists": True, "$ne": []}}):
        for v in u.get("vehicles", []):
            slot = v.get("parking_slot", "").strip().upper()
            if slot and slot not in occupied:
                occupied[slot] = {
                    "vehicle_id": v.get("vehicle_id"),
                    "resident_id": u.get("user_id"),
                    "resident_name": u.get("name"),
                    "flat": u.get("flat"),
                    "block": u.get("block"),
                    "parking_slot": slot,
                    "type": v.get("type"),
                    "registration_number": v.get("registration_number"),
                    "status": "ACTIVE"
                }
    return occupied

def get_parking_slots_status(current_vehicle_id: str = None) -> list:
    """
    Returns a unified list of all designated parking slots with availability status.
    If current_vehicle_id is provided, that vehicle's current slot is flagged as occupied_by_current.
    """
    db = get_db()
    occupied_map = get_all_active_occupied_slots()
    
    # Collect all known slot identifiers (defaults + any custom existing in db)
    all_slots_set = set(DEFAULT_PARKING_SLOTS)
    for slot in occupied_map.keys():
        all_slots_set.add(slot)
    
    sorted_slots = sorted(list(all_slots_set))
    
    result = []
    for slot in sorted_slots:
        occupied_data = occupied_map.get(slot)
        is_occupied = occupied_data is not None
        is_current_vehicle = False
        
        if is_occupied and current_vehicle_id:
            if occupied_data.get("vehicle_id") == current_vehicle_id:
                is_occupied = False  # Available for the vehicle that already holds it
                is_current_vehicle = True
                
        result.append({
            "slot": slot,
            "block": get_slot_block(slot),
            "is_occupied": is_occupied,
            "is_current": is_current_vehicle,
            "occupied_by": {
                "vehicle_id": occupied_data.get("vehicle_id"),
                "resident_name": occupied_data.get("resident_name"),
                "flat": occupied_data.get("flat"),
                "registration_number": occupied_data.get("registration_number")
            } if (occupied_data and not is_current_vehicle) else None
        })
    return result

def register_vehicle(resident_user: dict, form_data: dict):
    """
    Registers a new vehicle for a resident.
    Enforces that parking_slot is globally unique among all active vehicles.
    """
    db = get_db()
    v_type = form_data.get("type", "Car").strip()
    reg_num = form_data.get("registration_number", "").strip().upper()
    slot = form_data.get("parking_slot", "").strip().upper()
    
    if not reg_num:
        return False, "Registration number plate is required.", 400
    if not slot:
        return False, "Parking slot selection is required.", 400
    
    # 1. Check for parking slot conflict across ALL residents
    conflict = check_parking_slot_conflict(slot)
    if conflict:
        return False, f"Parking slot {slot} is already assigned to another resident. Please select another available parking slot.", 409
    
    # 2. Check if registration number already active
    existing_reg = db.vehicles.find_one({"registration_number": reg_num, "status": "ACTIVE"})
    if existing_reg:
        return False, f"Vehicle with registration {reg_num} is already registered.", 409
    
    veh_id = get_next_sequence("vehicle", prefix="VEH", padding=3)
    
    vehicle_doc = {
        "vehicle_id": veh_id,
        "resident_id": resident_user["user_id"],
        "resident_name": resident_user.get("name", "Resident"),
        "block": resident_user.get("block", ""),
        "flat": resident_user.get("flat", ""),
        "type": v_type,
        "registration_number": reg_num,
        "parking_slot": slot,
        "status": "ACTIVE",
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    
    try:
        # Insert into vehicles collection (guarded by MongoDB unique index)
        db.vehicles.insert_one(vehicle_doc)
        
        # Sync into user's embedded array
        db.users.update_one(
            {"user_id": resident_user["user_id"]},
            {"$push": {"vehicles": {
                "vehicle_id": veh_id,
                "type": v_type,
                "registration_number": reg_num,
                "parking_slot": slot,
                "status": "ACTIVE"
            }}}
        )
        
        log_action(
            resident_user["user_id"],
            resident_user.get("name", "Resident"),
            "RESIDENT",
            "REGISTER_VEHICLE",
            "VEHICLE",
            veh_id,
            f"Registered vehicle {reg_num} to slot {slot}"
        )
        return True, vehicle_doc, 201
        
    except pymongo.errors.DuplicateKeyError:
        return False, f"Parking slot {slot} was just assigned to another resident. Please select another slot.", 409
    except Exception as e:
        return False, f"Failed to register vehicle: {str(e)}", 500

def update_vehicle(vehicle_id: str, resident_user: dict, form_data: dict):
    """
    Updates vehicle details. If parking slot is changed, ensures target slot is free.
    Allows keeping the current slot without conflict.
    """
    db = get_db()
    v_type = form_data.get("type", "Car").strip()
    reg_num = form_data.get("registration_number", "").strip().upper()
    slot = form_data.get("parking_slot", "").strip().upper()
    
    if not reg_num or not slot:
        return False, "Registration number and parking slot are required.", 400
    
    # Check if vehicle exists
    veh = db.vehicles.find_one({"vehicle_id": vehicle_id})
    if not veh:
        # Check in user doc
        user = db.users.find_one({"user_id": resident_user["user_id"]})
        found_in_user = any(v.get("vehicle_id") == vehicle_id for v in user.get("vehicles", []))
        if not found_in_user:
            return False, "Vehicle record not found.", 404
    
    # Check conflict excluding current vehicle_id
    conflict = check_parking_slot_conflict(slot, exclude_vehicle_id=vehicle_id)
    if conflict:
        return False, f"Parking slot {slot} is already assigned to another vehicle.", 409
    
    try:
        # Update db.vehicles
        db.vehicles.update_one(
            {"vehicle_id": vehicle_id},
            {
                "$set": {
                    "type": v_type,
                    "registration_number": reg_num,
                    "parking_slot": slot,
                    "status": "ACTIVE",
                    "updated_at": datetime.now()
                }
            },
            upsert=True
        )
        
        # Update in db.users.vehicles
        db.users.update_one(
            {"user_id": resident_user["user_id"], "vehicles.vehicle_id": vehicle_id},
            {
                "$set": {
                    "vehicles.$.type": v_type,
                    "vehicles.$.registration_number": reg_num,
                    "vehicles.$.parking_slot": slot,
                    "vehicles.$.status": "ACTIVE"
                }
            }
        )
        
        log_action(
            resident_user["user_id"],
            resident_user.get("name", "Resident"),
            "RESIDENT",
            "UPDATE_VEHICLE",
            "VEHICLE",
            vehicle_id,
            f"Updated vehicle {reg_num} slot to {slot}"
        )
        return True, "Vehicle details updated successfully.", 200
        
    except pymongo.errors.DuplicateKeyError:
        return False, f"Parking slot {slot} was just assigned to another resident. Please select another slot.", 409
    except Exception as e:
        return False, f"Failed to update vehicle: {str(e)}", 500

def release_vehicle(vehicle_id: str, resident_user_id: str = None):
    """
    Deactivates a vehicle record, marking status as INACTIVE.
    This immediately frees up the parking slot while preserving history.
    """
    db = get_db()
    
    query = {"vehicle_id": vehicle_id}
    if resident_user_id:
        query["resident_id"] = resident_user_id
        
    veh = db.vehicles.find_one(query)
    
    now = datetime.now()
    # Update status to INACTIVE in db.vehicles
    db.vehicles.update_one(
        {"vehicle_id": vehicle_id},
        {"$set": {"status": "INACTIVE", "deactivated_at": now, "updated_at": now}}
    )
    
    # Remove or mark INACTIVE in users collection
    if resident_user_id:
        db.users.update_one(
            {"user_id": resident_user_id},
            {"$pull": {"vehicles": {"vehicle_id": vehicle_id}}}
        )
    else:
        # Manager / Admin removing vehicle
        db.users.update_one(
            {"vehicles.vehicle_id": vehicle_id},
            {"$pull": {"vehicles": {"vehicle_id": vehicle_id}}}
        )
        
    slot = veh.get("parking_slot", "N/A") if veh else "N/A"
    return True, f"Vehicle registration released. Parking slot {slot} is now available.", 200

def detect_parking_duplicates():
    """
    Runs aggregation to detect any active parking slots assigned to multiple vehicles.
    """
    db = get_db()
    try:
        pipeline = [
            {"$match": {"parking_slot": {"$ne": None}, "status": "ACTIVE"}},
            {"$group": {
                "_id": "$parking_slot",
                "count": {"$sum": 1},
                "vehicles": {"$push": "$vehicle_id"},
                "residents": {"$push": "$resident_id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        return list(db.vehicles.aggregate(pipeline))
    except Exception as e:
        print(f"Error detecting duplicates: {e}")
        return []

def get_parking_overview(search_query: str = None, block_filter: str = None, status_filter: str = None):
    """
    Returns complete parking data and analytics for Manager/Admin portal.
    """
    slots_data = get_parking_slots_status()
    duplicates = detect_parking_duplicates()
    
    total_slots = len(slots_data)
    occupied_count = sum(1 for s in slots_data if s["is_occupied"])
    available_count = total_slots - occupied_count
    occupancy_rate = round((occupied_count / total_slots * 100), 1) if total_slots > 0 else 0
    
    filtered_slots = []
    q = (search_query or "").strip().lower()
    b_filter = (block_filter or "").strip()
    s_filter = (status_filter or "").strip().upper()
    
    for s in slots_data:
        # Status Filter
        if s_filter == "OCCUPIED" and not s["is_occupied"]:
            continue
        if s_filter == "AVAILABLE" and s["is_occupied"]:
            continue
            
        # Block Filter
        if b_filter and b_filter != "ALL":
            if b_filter not in s["block"] and not s["slot"].startswith(f"P-{b_filter}") and not s["slot"].startswith(f"{b_filter}-"):
                continue
                
        # Search Query
        if q:
            occ = s.get("occupied_by") or {}
            slot_match = q in s["slot"].lower()
            veh_match = q in (occ.get("vehicle_id") or "").lower()
            reg_match = q in (occ.get("registration_number") or "").lower()
            res_match = q in (occ.get("resident_name") or "").lower()
            flat_match = q in (occ.get("flat") or "").lower()
            block_match = q in s["block"].lower()
            
            if not (slot_match or veh_match or reg_match or res_match or flat_match or block_match):
                continue
                
        filtered_slots.append(s)
        
    return {
        "total_slots": total_slots,
        "occupied_slots": occupied_count,
        "available_slots": available_count,
        "occupancy_rate": occupancy_rate,
        "duplicates": duplicates,
        "slots": filtered_slots
    }
