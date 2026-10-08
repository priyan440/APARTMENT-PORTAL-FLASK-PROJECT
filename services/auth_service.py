from functools import wraps
from flask import session, redirect, url_for, flash, request, abort
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pymongo
from database.mongodb import get_db, get_next_sequence, sync_counter_max

def hash_password(password: str) -> str:
    return generate_password_hash(password)

def verify_password(hashed_password: str, password: str) -> bool:
    return check_password_hash(hashed_password, password)

def create_user(data: dict, creator_role: str = None) -> tuple[bool, str, dict]:
    db = get_db()
    email = data.get("email", "").strip().lower()
    
    if not email or "@" not in email:
        return False, "Valid email is required.", None
    
    if db.users.find_one({"email": email}):
        return False, "An account with this email already exists.", None

    role = data.get("role", "RESIDENT").upper()
    prefix_map = {
        "ADMIN": ("user_adm", "ADM"),
        "MANAGER": ("user_mgr", "MGR"),
        "RESIDENT": ("user_res", "RES"),
        "TECHNICIAN": ("user_tech", "TECH"),
        "SECURITY": ("user_sec", "SEC")
    }
    
    seq_name, prefix = prefix_map.get(role, (f"user_{role.lower()[:3]}", "USR"))
    
    # Sync counter with maximum numeric suffix already in users collection
    sync_counter_max(seq_name, "users", "user_id", prefix)

    flat_no = (data.get("flat") or data.get("flat_number") or "").strip().upper() if role == "RESIDENT" else ""
    block_code = data.get("block", "").strip().upper() if role == "RESIDENT" else ""

    # Check if flat is already occupied by an active resident
    if role == "RESIDENT" and flat_no:
        existing_flat_user = db.users.find_one({"flat": flat_no, "role": "RESIDENT", "status": "ACTIVE"})
        flat_record = db.flats.find_one({"flat_number": flat_no})
        if existing_flat_user or (flat_record and flat_record.get("status") == "OCCUPIED" and flat_record.get("resident_id")):
            return False, "This flat is already assigned to another resident.", None

    # Generate unique user_id
    user_id = None
    for _ in range(200):
        candidate_id = get_next_sequence(seq_name, prefix=prefix, padding=3)
        if not db.users.find_one({"user_id": candidate_id}):
            user_id = candidate_id
            break
    if not user_id:
        user_id = f"{prefix}{int(datetime.now().timestamp())}"

    user_doc = {
        "user_id": user_id,
        "name": data.get("name", "").strip(),
        "email": email,
        "phone": data.get("phone", "").strip(),
        "password": hash_password(data.get("password", "")),
        "role": role,
        "status": "ACTIVE",
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }

    if role == "RESIDENT":
        user_doc.update({
            "block": block_code,
            "flat": flat_no,
            "resident_type": data.get("resident_type", "OWNER").upper(), # OWNER or TENANT
            "family_members": [], # Embedded documents
            "vehicles": []        # Embedded documents
        })
    elif role == "TECHNICIAN":
        user_doc.update({
            "specialization": data.get("specialization", "Plumbing").strip(),
            "active_tasks": 0,
            "completed_tasks": 0,
            "rating": 5.0,
            "ratings_count": 0
        })

    try:
        result = db.users.insert_one(user_doc)
        if not result.inserted_id:
            return False, "Failed to save user account to database.", None

        if role == "RESIDENT":
            # Sync to residents collection
            resident_doc = {
                "resident_id": user_id,
                "user_id": user_id,
                "name": user_doc["name"],
                "email": user_doc["email"],
                "phone": user_doc["phone"],
                "block": block_code,
                "flat_number": flat_no,
                "resident_type": user_doc["resident_type"],
                "status": "ACTIVE",
                "created_at": user_doc["created_at"],
                "updated_at": user_doc["updated_at"]
            }
            res_result = db.residents.update_one(
                {"user_id": user_id},
                {"$set": resident_doc},
                upsert=True
            )

            # Update flat status
            if flat_no:
                db.flats.update_one(
                    {"flat_number": flat_no},
                    {"$set": {"status": "OCCUPIED", "resident_id": user_id, "resident_name": user_doc["name"]}}
                )

        # Verification step: Ensure record is actually retrievable from MongoDB
        verified_user = db.users.find_one({"user_id": user_id})
        if not verified_user:
            # Rollback if verification failed
            db.users.delete_one({"user_id": user_id})
            if role == "RESIDENT":
                db.residents.delete_one({"user_id": user_id})
                if flat_no:
                    db.flats.update_one({"flat_number": flat_no}, {"$set": {"status": "VACANT", "resident_id": None, "resident_name": None}})
            return False, "Database verification failed after user creation.", None

        return True, f"User {user_id} created successfully.", user_doc

    except pymongo.errors.DuplicateKeyError as e:
        err_msg = str(e)
        if "email" in err_msg:
            return False, "An account with this email already exists.", None
        elif "user_id" in err_msg:
            if role == "MANAGER":
                return False, "Manager ID already exists. Please use another account.", None
            return False, f"{role.capitalize()} ID already exists. Please try again.", None
        elif "flat_number" in err_msg or "flat" in err_msg:
            return False, "This flat is already assigned to another resident.", None
        return False, "A record with these credentials already exists.", None
    except Exception as e:
        return False, f"Unable to create account: {str(e)}", None


def authenticate_user(identifier: str, password: str):
    db = get_db()
    identifier = identifier.strip().lower()
    
    user = db.users.find_one({
        "$or": [
            {"email": identifier},
            {"user_id": identifier.upper()}
        ]
    })
    
    if not user:
        return None, "Invalid email/User ID or password."
    
    if user.get("status") != "ACTIVE":
        return None, "Your account has been deactivated. Please contact administrator."
    
    if not verify_password(user["password"], password):
        return None, "Invalid email/User ID or password."
        
    return user, None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for("auth.login", next=request.url))
        db = get_db()
        user = db.users.find_one({"user_id": session.get("user_id"), "status": "ACTIVE"})
        if not user:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                session.clear()
                flash("Your session has expired. Please log in again.", "warning")
                return redirect(url_for("auth.login", next=request.url))
            db = get_db()
            user = db.users.find_one({"user_id": session.get("user_id"), "status": "ACTIVE"})
            if not user:
                session.clear()
                flash("Your session has expired. Please log in again.", "warning")
                return redirect(url_for("auth.login"))
            user_role = user.get("role") or session.get("role")
            if user_role not in roles:
                flash("Access denied. You are not authorized to view that page.", "danger")
                role_dashboards = {
                    "ADMIN": "admin.dashboard",
                    "MANAGER": "manager.dashboard",
                    "RESIDENT": "resident.dashboard",
                    "TECHNICIAN": "technician.dashboard",
                    "SECURITY": "security.dashboard"
                }
                dest = role_dashboards.get(user_role, "auth.login")
                return redirect(url_for(dest))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
