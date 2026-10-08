from datetime import datetime
from database.mongodb import get_db, get_next_sequence
from services.notification_service import create_notification
from services.audit_service import log_action
from services.gridfs_service import save_file_to_gridfs

CATEGORIES = ["Plumbing", "Electrical", "Lift", "Cleaning", "Carpentry", "Security", "Other"]
PRIORITIES = ["LOW", "MEDIUM", "HIGH", "EMERGENCY"]
STATUSES = ["OPEN", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", "CANCELLED"]

def create_complaint(resident_user: dict, form_data: dict, file_storage=None) -> tuple[bool, str, dict]:
    db = get_db()
    
    title = form_data.get("title", "").strip()
    category = form_data.get("category", "Plumbing").strip()
    description = form_data.get("description", "").strip()
    priority = form_data.get("priority", "MEDIUM").strip().upper()

    if not title or not description:
        return False, "Title and description are required.", None

    if priority not in PRIORITIES:
        priority = "MEDIUM"
        
    complaint_id = get_next_sequence("complaint", prefix="CMP", padding=3)
    
    # Process optional media
    media_list = []
    if file_storage and file_storage.filename != "":
        try:
            saved_media = save_file_to_gridfs(file_storage)
            if saved_media:
                media_list.append(saved_media)
        except Exception as e:
            return False, f"Media upload error: {str(e)}", None

    now = datetime.now()
    initial_history_item = {
        "status": "OPEN",
        "changed_by": resident_user["user_id"],
        "changed_by_name": resident_user["name"],
        "role": "RESIDENT",
        "timestamp": now.isoformat(),
        "notes": "Complaint filed by resident."
    }

    complaint_doc = {
        "complaint_id": complaint_id,
        "title": title,
        "category": category,
        "description": description,
        "priority": priority,
        "resident_id": resident_user["user_id"],
        "resident_name": resident_user["name"],
        "resident_phone": resident_user.get("phone", ""),
        "flat": resident_user.get("flat", ""),
        "block": resident_user.get("block", ""),
        "status": "OPEN",
        "technician_id": None,
        "technician_name": None,
        "media": media_list,
        "status_history": [initial_history_item],
        "resolution_notes": None,
        "resolution_media": [],
        "rating": None,
        "feedback": None,
        "created_at": now,
        "updated_at": now
    }

    db.complaints.insert_one(complaint_doc)

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="CREATE_COMPLAINT",
        entity="COMPLAINT",
        entity_id=complaint_id,
        details=f"Filed {category} complaint: {title} ({priority})"
    )

    # Notify managers
    managers = list(db.users.find({"role": "MANAGER"}))
    for mgr in managers:
        create_notification(
            user_id=mgr["user_id"],
            title=f"New Complaint: {complaint_id} ({priority})",
            message=f"{resident_user['name']} (Flat {resident_user.get('flat')}) raised a {category} complaint: '{title}'",
            link="/manager/complaints",
            n_type="WARNING" if priority in ["HIGH", "EMERGENCY"] else "INFO"
        )

    return True, f"Complaint {complaint_id} registered successfully.", complaint_doc

def assign_technician(complaint_id: str, technician_id: str, manager_user: dict, priority_override: str = None) -> tuple[bool, str]:
    db = get_db()
    complaint = db.complaints.find_one({"complaint_id": complaint_id})
    if not complaint:
        return False, "Complaint not found."

    tech = db.users.find_one({"user_id": technician_id, "role": "TECHNICIAN"})
    if not tech:
        return False, "Selected technician not found."

    now = datetime.now()
    history_entry = {
        "status": "ASSIGNED",
        "changed_by": manager_user["user_id"],
        "changed_by_name": manager_user["name"],
        "role": manager_user.get("role", "MANAGER"),
        "timestamp": now.isoformat(),
        "notes": f"Assigned to {tech['name']} ({tech.get('specialization', 'Staff')})."
    }

    update_fields = {
        "status": "ASSIGNED",
        "technician_id": tech["user_id"],
        "technician_name": tech["name"],
        "updated_at": now
    }
    if priority_override and priority_override in PRIORITIES:
        update_fields["priority"] = priority_override

    # If reassigning, decrement previous technician active tasks
    if complaint.get("technician_id") and complaint["technician_id"] != tech["user_id"]:
        db.users.update_one(
            {"user_id": complaint["technician_id"]},
            {"$inc": {"active_tasks": -1}}
        )

    db.complaints.update_one(
        {"complaint_id": complaint_id},
        {
            "$set": update_fields,
            "$push": {"status_history": history_entry}
        }
    )

    # Increment technician active workload
    db.users.update_one(
        {"user_id": tech["user_id"]},
        {"$inc": {"active_tasks": 1}}
    )

    # Notify technician
    create_notification(
        user_id=tech["user_id"],
        title="New Task Assigned!",
        message=f"You have been assigned to complaint {complaint_id}: '{complaint['title']}' at Flat {complaint.get('flat')}.",
        link="/technician/assignments",
        n_type="INFO"
    )

    # Notify resident
    create_notification(
        user_id=complaint["resident_id"],
        title=f"Complaint {complaint_id} Assigned",
        message=f"Your complaint has been assigned to technician {tech['name']} ({tech.get('phone', '')}).",
        link="/resident/complaints",
        n_type="INFO"
    )

    log_action(
        user_id=manager_user["user_id"],
        user_name=manager_user["name"],
        role=manager_user.get("role", "MANAGER"),
        action="ASSIGN_TECHNICIAN",
        entity="COMPLAINT",
        entity_id=complaint_id,
        details=f"Assigned to {tech['name']} ({tech['user_id']})"
    )

    return True, f"Complaint {complaint_id} assigned to {tech['name']}."

def submit_technician_work_report(complaint_id: str, tech_user: dict, form_data: dict, before_image=None, after_image=None) -> tuple[bool, str, dict]:
    """Technician submits a completed work report with summary, parts used, time spent, and images."""
    db = get_db()
    complaint = db.complaints.find_one({"complaint_id": complaint_id, "technician_id": tech_user["user_id"]})
    if not complaint:
        return False, "Complaint record not found or not assigned to you.", None

    summary = (form_data.get("summary") or form_data.get("work_summary") or "").strip()
    details = (form_data.get("details") or form_data.get("work_performed") or "").strip()
    parts_raw = form_data.get("parts_used", "")
    if isinstance(parts_raw, str):
        parts_list = [p.strip() for p in parts_raw.split(",") if p.strip()]
    elif isinstance(parts_raw, list):
        parts_list = parts_raw
    else:
        parts_list = []

    try:
        time_spent = int(form_data.get("time_spent_minutes") or form_data.get("time_spent") or 60)
    except (ValueError, TypeError):
        time_spent = 60

    remarks = (form_data.get("remarks") or form_data.get("notes") or "").strip()

    if not summary:
        summary = f"Repairs completed for {complaint.get('title', 'complaint')}"
    if not details:
        details = remarks or summary

    before_image_id = None
    after_image_id = None

    if before_image and before_image.filename:
        try:
            saved_b = save_file_to_gridfs(before_image)
            if saved_b:
                before_image_id = saved_b["file_id"]
        except Exception:
            pass

    if after_image and after_image.filename:
        try:
            saved_a = save_file_to_gridfs(after_image)
            if saved_a:
                after_image_id = saved_a["file_id"]
        except Exception:
            pass

    report_id = get_next_sequence("service_work_report", prefix="WR", padding=3)
    now = datetime.now()

    report_doc = {
        "report_id": report_id,
        "complaint_id": complaint_id,
        "complaint_title": complaint.get("title", ""),
        "flat": complaint.get("flat", ""),
        "block": complaint.get("block", ""),
        "resident_id": complaint.get("resident_id"),
        "resident_name": complaint.get("resident_name"),
        "technician_id": tech_user["user_id"],
        "technician_name": tech_user["name"],
        "vendor_id": complaint.get("vendor_id"),
        "work": {
            "summary": summary,
            "details": details,
            "parts_used": parts_list,
            "time_spent_minutes": time_spent,
            "remarks": remarks
        },
        "media": {
            "before_image_id": before_image_id,
            "after_image_id": after_image_id
        },
        "status": "SUBMITTED",
        "submitted_at": now.isoformat(),
        "completion_date": now.strftime("%Y-%m-%d"),
        "created_at": now
    }

    db.service_work_reports.insert_one(report_doc)

    history_entry = {
        "status": "RESOLVED",
        "changed_by": tech_user["user_id"],
        "changed_by_name": tech_user["name"],
        "role": "TECHNICIAN",
        "timestamp": now.isoformat(),
        "notes": f"Work completed by {tech_user['name']}. Work Report Ref: {report_id}. Summary: {summary}"
    }

    resolution_media = []
    if after_image_id:
        resolution_media.append({"file_id": after_image_id, "doc_type": "After Repair Photo"})
    if before_image_id:
        resolution_media.append({"file_id": before_image_id, "doc_type": "Before Repair Photo"})

    db.complaints.update_one(
        {"complaint_id": complaint_id},
        {
            "$set": {
                "status": "RESOLVED",
                "work_report_id": report_id,
                "resolution_notes": f"{summary} - {details}",
                "resolution_media": resolution_media,
                "resolved_at": now,
                "updated_at": now
            },
            "$push": {"status_history": history_entry}
        }
    )

    # Update technician tasks
    db.users.update_one(
        {"user_id": tech_user["user_id"]},
        {"$inc": {"active_tasks": -1, "completed_tasks": 1}}
    )

    # Notify resident
    create_notification(
        user_id=complaint["resident_id"],
        title=f"Complaint Resolved: {complaint_id}",
        message=f"Technician {tech_user['name']} has completed repairs for your complaint '{complaint['title']}'. Work Summary: {summary}. Please rate the service!",
        link=f"/resident/complaints/{complaint_id}",
        n_type="SUCCESS"
    )

    # Notify managers
    for mgr in db.users.find({"role": "MANAGER"}):
        create_notification(
            user_id=mgr["user_id"],
            title=f"Work Report Submitted: {report_id}",
            message=f"{tech_user['name']} submitted work report for {complaint_id} (Flat {complaint.get('flat')}).",
            link="/manager/complaints",
            n_type="INFO"
        )

    log_action(
        user_id=tech_user["user_id"],
        user_name=tech_user["name"],
        role="TECHNICIAN",
        action="SUBMIT_WORK_REPORT",
        entity="WORK_REPORT",
        entity_id=report_id,
        details=f"Submitted work report for complaint {complaint_id}: {summary}"
    )

    return True, f"Work report {report_id} submitted and complaint {complaint_id} marked as resolved.", report_doc


def approve_work_report(manager_user: dict, report_id_or_complaint_id: str) -> tuple[bool, str]:
    """Manager approves technician completion report."""
    db = get_db()
    report = db.service_work_reports.find_one({
        "$or": [
            {"report_id": report_id_or_complaint_id},
            {"complaint_id": report_id_or_complaint_id}
        ]
    })
    
    complaint_id = report["complaint_id"] if report else report_id_or_complaint_id
    complaint = db.complaints.find_one({"complaint_id": complaint_id})
    if not complaint:
        return False, "Complaint record not found."

    now = datetime.now()
    if report:
        db.service_work_reports.update_one(
            {"report_id": report["report_id"]},
            {"$set": {"status": "APPROVED", "approved_by": manager_user.get("user_id"), "approved_at": now.isoformat()}}
        )

    history_entry = {
        "status": "RESOLVED",
        "changed_by": manager_user["user_id"],
        "changed_by_name": manager_user["name"],
        "role": manager_user.get("role", "MANAGER"),
        "timestamp": now.isoformat(),
        "notes": f"Completion approved by {manager_user['name']}."
    }

    db.complaints.update_one(
        {"complaint_id": complaint_id},
        {
            "$set": {"status": "RESOLVED", "updated_at": now},
            "$push": {"status_history": history_entry}
        }
    )

    create_notification(
        user_id=complaint["resident_id"],
        title=f"Complaint Resolved: {complaint_id}",
        message="Your complaint has been resolved and approved by management.",
        link=f"/resident/complaints/{complaint_id}",
        n_type="SUCCESS"
    )

    log_action(
        user_id=manager_user["user_id"],
        user_name=manager_user["name"],
        role=manager_user.get("role", "MANAGER"),
        action="APPROVE_WORK_REPORT",
        entity="COMPLAINT",
        entity_id=complaint_id,
        details=f"Approved completion for complaint {complaint_id}"
    )

    return True, f"Complaint {complaint_id} completion approved."


def reopen_complaint(manager_user: dict, complaint_id: str, reason: str = "") -> tuple[bool, str]:
    """Manager reopens a complaint that requires rework."""
    db = get_db()
    complaint = db.complaints.find_one({"complaint_id": complaint_id})
    if not complaint:
        return False, "Complaint record not found."

    now = datetime.now()
    reopen_notes = reason or "Manager reopened complaint for rework."

    history_entry = {
        "status": "REOPENED",
        "changed_by": manager_user["user_id"],
        "changed_by_name": manager_user["name"],
        "role": manager_user.get("role", "MANAGER"),
        "timestamp": now.isoformat(),
        "notes": reopen_notes
    }

    db.complaints.update_one(
        {"complaint_id": complaint_id},
        {
            "$set": {
                "status": "REOPENED",
                "reopen_reason": reopen_notes,
                "updated_at": now
            },
            "$push": {"status_history": history_entry}
        }
    )

    # If technician was assigned, re-increment active tasks and notify
    if complaint.get("technician_id"):
        db.users.update_one(
            {"user_id": complaint["technician_id"]},
            {"$inc": {"active_tasks": 1}}
        )
        create_notification(
            user_id=complaint["technician_id"],
            title=f"⚠️ Task Reopened: {complaint_id}",
            message=f"Complaint {complaint_id} has been reopened by management: {reopen_notes}",
            link="/technician/assignments",
            n_type="WARNING"
        )

    create_notification(
        user_id=complaint["resident_id"],
        title=f"Complaint Reopened: {complaint_id}",
        message=f"Management has reopened your complaint '{complaint['title']}' for further inspection.",
        link=f"/resident/complaints/{complaint_id}",
        n_type="INFO"
    )

    log_action(
        user_id=manager_user["user_id"],
        user_name=manager_user["name"],
        role=manager_user.get("role", "MANAGER"),
        action="REOPEN_COMPLAINT",
        entity="COMPLAINT",
        entity_id=complaint_id,
        details=f"Reopened complaint {complaint_id}. Notes: {reopen_notes}"
    )

    return True, f"Complaint {complaint_id} reopened."


def update_complaint_status_by_technician(complaint_id: str, new_status: str, tech_user: dict, notes: str = "", completion_file=None) -> tuple[bool, str]:
    db = get_db()
    complaint = db.complaints.find_one({"complaint_id": complaint_id, "technician_id": tech_user["user_id"]})
    if not complaint:
        return False, "Complaint not found or not assigned to you."

    if new_status not in ["IN_PROGRESS", "RESOLVED"]:
        return False, "Invalid status update for technician."

    now = datetime.now()
    history_entry = {
        "status": new_status,
        "changed_by": tech_user["user_id"],
        "changed_by_name": tech_user["name"],
        "role": "TECHNICIAN",
        "timestamp": now.isoformat(),
        "notes": notes or f"Status changed to {new_status}"
    }

    update_doc = {
        "status": new_status,
        "updated_at": now
    }

    if notes:
        update_doc["resolution_notes"] = notes

    if completion_file and completion_file.filename != "":
        saved = save_file_to_gridfs(completion_file)
        if saved:
            update_doc["resolution_media"] = [saved]

    if new_status == "RESOLVED":
        update_doc["resolved_at"] = now
        # Update technician counters
        db.users.update_one(
            {"user_id": tech_user["user_id"]},
            {
                "$inc": {"active_tasks": -1, "completed_tasks": 1}
            }
        )

    db.complaints.update_one(
        {"complaint_id": complaint_id},
        {
            "$set": update_doc,
            "$push": {"status_history": history_entry}
        }
    )

    # Notify resident
    if new_status == "IN_PROGRESS":
        create_notification(
            user_id=complaint["resident_id"],
            title=f"Work In Progress: {complaint_id}",
            message=f"Technician {tech_user['name']} has begun working on your complaint '{complaint['title']}'.",
            link="/resident/complaints",
            n_type="INFO"
        )
    elif new_status == "RESOLVED":
        create_notification(
            user_id=complaint["resident_id"],
            title=f"Complaint Resolved: {complaint_id}",
            message=f"Your complaint '{complaint['title']}' has been marked as RESOLVED by {tech_user['name']}. Please rate the service!",
            link="/resident/complaints",
            n_type="SUCCESS"
        )

    log_action(
        user_id=tech_user["user_id"],
        user_name=tech_user["name"],
        role="TECHNICIAN",
        action=f"UPDATE_STATUS_{new_status}",
        entity="COMPLAINT",
        entity_id=complaint_id,
        details=f"Technician changed status to {new_status}. Notes: {notes}"
    )

    return True, f"Complaint {complaint_id} updated to {new_status}."


def submit_service_rating(complaint_id: str, resident_user: dict, rating: int, feedback: str = "") -> tuple[bool, str]:
    db = get_db()
    complaint = db.complaints.find_one({"complaint_id": complaint_id, "resident_id": resident_user["user_id"]})
    if not complaint:
        return False, "Complaint not found or does not belong to you."

    if complaint["status"] not in ["RESOLVED", "CLOSED"]:
        return False, "You can only rate a resolved complaint."

    if rating < 1 or rating > 5:
        return False, "Rating must be between 1 and 5 stars."

    db.complaints.update_one(
        {"complaint_id": complaint_id},
        {"$set": {
            "rating": rating,
            "feedback": feedback.strip(),
            "status": "CLOSED",
            "updated_at": datetime.now()
        }}
    )

    # Recalculate technician rating using MongoDB aggregation
    tech_id = complaint.get("technician_id")
    if tech_id:
        pipeline = [
            {"$match": {"technician_id": tech_id, "rating": {"$ne": None}}},
            {"$group": {
                "_id": "$technician_id",
                "avg_rating": {"$avg": "$rating"},
                "count": {"$sum": 1}
            }}
        ]
        agg_result = list(db.complaints.aggregate(pipeline))
        if agg_result:
            avg_r = round(agg_result[0]["avg_rating"], 1)
            count = agg_result[0]["count"]
            db.users.update_one(
                {"user_id": tech_id},
                {"$set": {"rating": avg_r, "ratings_count": count}}
            )

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="RATE_COMPLAINT",
        entity="COMPLAINT",
        entity_id=complaint_id,
        details=f"Rated {rating} stars for complaint {complaint_id}"
    )

    return True, f"Thank you! Your {rating}-star rating has been recorded."

def get_technician_workload_list(category: str = None):
    """Returns technicians with workload, specialization, and average rating."""
    db = get_db()
    query = {"role": "TECHNICIAN", "status": "ACTIVE"}
    techs = list(db.users.find(query))
    
    # Sort so recommended matching category comes first
    def sort_key(t):
        is_match = 0 if (category and t.get("specialization", "").lower() == category.lower()) else 1
        return (is_match, t.get("active_tasks", 0))

    techs.sort(key=sort_key)
    return techs
