import uuid
from datetime import datetime, date, timedelta
from database.mongodb import get_db, get_next_sequence
from services.notification_service import create_notification
from services.audit_service import log_action
from services.gridfs_service import save_file_to_gridfs

VENDOR_CATEGORIES = [
    "Lift Maintenance",
    "Electrical",
    "Plumbing",
    "Cleaning",
    "Security",
    "Gardening",
    "Pest Control",
    "Water Tank Cleaning",
    "Swimming Pool Maintenance",
    "Gym Equipment",
    "Generator Maintenance",
    "CCTV Maintenance",
    "Fire Safety",
    "Waste Management",
    "Internet / Cable",
    "HVAC / AC Maintenance",
    "Solar Panel Maintenance",
    "RO / Water Purifier",
    "Painting",
    "Carpentry",
    "Other"
]

VENDOR_STATUSES = ["ACTIVE", "INACTIVE", "SUSPENDED", "BLACKLISTED"]
CONTRACT_STATUSES = ["ACTIVE", "EXPIRING_SOON", "EXPIRED", "RENEWED", "CLOSED"]
SERVICE_REQUEST_STATUSES = ["PENDING", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
PAYMENT_STATUSES = ["PENDING", "PAID", "OVERDUE", "CANCELLED"]


def create_vendor(manager_user: dict, data: dict, doc_files: list = None) -> tuple[bool, str, dict]:
    """Creates a new external vendor with company details, contract terms, and documents."""
    db = get_db()
    company_name = data.get("name", "").strip()
    contact_person = data.get("contact_person", "").strip()
    phone = data.get("phone", "").strip()
    email = data.get("email", "").strip()
    category = data.get("category", "Other").strip()
    description = data.get("description", "").strip()

    if not company_name or not contact_person or not phone:
        return False, "Company name, contact person, and phone number are required.", None

    if category not in VENDOR_CATEGORIES:
        category = "Other"

    vendor_id = get_next_sequence("vendor", prefix="VEN", padding=3)

    # Check contract details if supplied
    start_date = data.get("contract_start_date", "").strip()
    end_date = data.get("contract_end_date", "").strip()
    payment_freq = data.get("payment_frequency", "MONTHLY").upper()
    try:
        contract_amount = float(data.get("contract_amount", 0) or 0)
    except (ValueError, TypeError):
        contract_amount = 0.0

    # Process uploaded documents
    documents = []
    if doc_files:
        for f in doc_files:
            if f and f.filename:
                try:
                    saved = save_file_to_gridfs(f)
                    if saved:
                        saved["title"] = f.filename
                        saved["doc_type"] = "Service Agreement / Certificate"
                        saved["uploaded_at"] = datetime.now().isoformat()
                        documents.append(saved)
                except Exception as e:
                    pass

    now = datetime.now()
    vendor_doc = {
        "vendor_id": vendor_id,
        "company": {
            "name": company_name,
            "contact_person": contact_person,
            "phone": phone,
            "email": email,
            "address": data.get("address", "").strip(),
            "city": data.get("city", "Coimbatore").strip(),
            "state": data.get("state", "Tamil Nadu").strip()
        },
        "service": {
            "category": category,
            "description": description,
            "availability": data.get("service_availability", "24x7 Emergency Support").strip()
        },
        "contract": {
            "start_date": start_date or now.strftime("%Y-%m-%d"),
            "end_date": end_date or (now + timedelta(days=365)).strftime("%Y-%m-%d"),
            "payment_frequency": payment_freq,
            "amount": contract_amount
        },
        "gst_number": data.get("gst_number", "").strip(),
        "emergency_contact": data.get("emergency_contact", phone).strip(),
        "documents": documents,
        "performance": {
            "average_rating": 5.0,
            "ratings_count": 0,
            "services_completed": 0,
            "sla_breaches": 0
        },
        "status": "ACTIVE",
        "created_by": manager_user.get("user_id", "MGR001"),
        "created_at": now,
        "updated_at": now
    }

    db.vendors.insert_one(vendor_doc)

    # Automatically create initial contract entry
    if contract_amount > 0 or start_date:
        contract_id = get_next_sequence("vendor_contract", prefix="CON", padding=3)
        contract_doc = {
            "contract_id": contract_id,
            "vendor_id": vendor_id,
            "vendor_name": company_name,
            "service_category": category,
            "start_date": vendor_doc["contract"]["start_date"],
            "end_date": vendor_doc["contract"]["end_date"],
            "amount": contract_amount,
            "payment_frequency": payment_freq,
            "terms": data.get("contract_terms", "Standard AMC Maintenance Terms and SLA agreement."),
            "renewal_date": vendor_doc["contract"]["end_date"],
            "status": "ACTIVE",
            "created_by": manager_user.get("user_id"),
            "created_at": now
        }
        db.vendor_contracts.insert_one(contract_doc)

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="CREATE_VENDOR",
        entity="VENDOR",
        entity_id=vendor_id,
        details=f"Registered vendor '{company_name}' ({category}) - Contract ₹{contract_amount:,.2f}/{payment_freq}"
    )

    return True, f"Vendor {vendor_id} ({company_name}) registered successfully.", vendor_doc


def update_vendor(manager_user: dict, vendor_id: str, data: dict) -> tuple[bool, str]:
    """Updates vendor company, service, and contract details."""
    db = get_db()
    vendor = db.vendors.find_one({"vendor_id": vendor_id})
    if not vendor:
        return False, "Vendor not found."

    company_name = data.get("name", vendor["company"]["name"]).strip()
    contact_person = data.get("contact_person", vendor["company"]["contact_person"]).strip()
    phone = data.get("phone", vendor["company"]["phone"]).strip()
    email = data.get("email", vendor["company"].get("email", "")).strip()
    category = data.get("category", vendor["service"]["category"]).strip()
    description = data.get("description", vendor["service"].get("description", "")).strip()

    try:
        contract_amount = float(data.get("contract_amount", vendor["contract"].get("amount", 0)))
    except (ValueError, TypeError):
        contract_amount = vendor["contract"].get("amount", 0)

    update_fields = {
        "company.name": company_name,
        "company.contact_person": contact_person,
        "company.phone": phone,
        "company.email": email,
        "company.address": data.get("address", vendor["company"].get("address", "")).strip(),
        "company.city": data.get("city", vendor["company"].get("city", "Coimbatore")).strip(),
        "company.state": data.get("state", vendor["company"].get("state", "Tamil Nadu")).strip(),
        "service.category": category,
        "service.description": description,
        "service.availability": data.get("service_availability", vendor["service"].get("availability", "24x7")).strip(),
        "contract.start_date": data.get("contract_start_date", vendor["contract"].get("start_date")),
        "contract.end_date": data.get("contract_end_date", vendor["contract"].get("end_date")),
        "contract.payment_frequency": data.get("payment_frequency", vendor["contract"].get("payment_frequency", "MONTHLY")),
        "contract.amount": contract_amount,
        "gst_number": data.get("gst_number", vendor.get("gst_number", "")).strip(),
        "emergency_contact": data.get("emergency_contact", vendor.get("emergency_contact", "")).strip(),
        "updated_at": datetime.now()
    }

    db.vendors.update_one({"vendor_id": vendor_id}, {"$set": update_fields})

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="UPDATE_VENDOR",
        entity="VENDOR",
        entity_id=vendor_id,
        details=f"Updated details for vendor {vendor_id} ({company_name})"
    )

    return True, f"Vendor {vendor_id} updated successfully."


def change_vendor_status(manager_user: dict, vendor_id: str, new_status: str, reason: str = "") -> tuple[bool, str]:
    """Updates status to ACTIVE, INACTIVE, SUSPENDED, or BLACKLISTED without deleting history."""
    db = get_db()
    if new_status not in VENDOR_STATUSES:
        return False, f"Invalid status: {new_status}"

    vendor = db.vendors.find_one({"vendor_id": vendor_id})
    if not vendor:
        return False, "Vendor not found."

    db.vendors.update_one(
        {"vendor_id": vendor_id},
        {"$set": {
            "status": new_status,
            "status_reason": reason,
            "updated_at": datetime.now()
        }}
    )

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="CHANGE_VENDOR_STATUS",
        entity="VENDOR",
        entity_id=vendor_id,
        details=f"Changed status of {vendor_id} to {new_status}. Reason: {reason}"
    )

    return True, f"Vendor {vendor_id} status updated to {new_status}."


# =========================================================================
# CONTRACT MANAGEMENT
# =========================================================================

def create_vendor_contract(manager_user: dict, vendor_id: str, data: dict, contract_file=None) -> tuple[bool, str, dict]:
    db = get_db()
    vendor = db.vendors.find_one({"vendor_id": vendor_id})
    if not vendor:
        return False, "Vendor not found.", None

    start_date = data.get("start_date", "").strip()
    end_date = data.get("end_date", "").strip()
    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0.0

    if not start_date or not end_date or amount <= 0:
        return False, "Start date, end date, and valid contract amount are required.", None

    # Contract PDF Validation (Required)
    if not contract_file or not contract_file.filename:
        return False, "Contract PDF document is required.", None

    filename = contract_file.filename.lower()
    if not filename.endswith(".pdf"):
        return False, "Only PDF format (.pdf) is allowed for contract documents.", None

    saved_pdf = None
    try:
        saved_pdf = save_file_to_gridfs(contract_file)
        if not saved_pdf or not saved_pdf.get("file_id"):
            return False, "Failed to store contract PDF document in GridFS.", None
    except Exception as e:
        return False, f"Contract PDF upload error: {str(e)}", None

    contract_id = get_next_sequence("vendor_contract", prefix="CON", padding=3)
    now = datetime.now()

    contract_doc = {
        "contract_id": contract_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor["company"]["name"],
        "service_category": vendor["service"]["category"],
        "contract": {
            "start_date": start_date,
            "end_date": end_date,
            "amount": amount,
            "payment_frequency": data.get("payment_frequency", "MONTHLY").upper()
        },
        "start_date": start_date,
        "end_date": end_date,
        "amount": amount,
        "payment_frequency": data.get("payment_frequency", "MONTHLY").upper(),
        "terms": data.get("terms", "Annual Maintenance Contract terms and scope of work."),
        "renewal_date": end_date,
        "document": {
            "file_id": saved_pdf["file_id"],
            "filename": saved_pdf.get("filename", contract_file.filename),
            "content_type": "application/pdf"
        },
        "file_id": saved_pdf["file_id"],
        "status": "ACTIVE",
        "created_by": manager_user.get("user_id"),
        "created_at": now
    }

    db.vendor_contracts.insert_one(contract_doc)

    # Sync vendor master contract summary
    db.vendors.update_one(
        {"vendor_id": vendor_id},
        {"$set": {
            "contract.start_date": start_date,
            "contract.end_date": end_date,
            "contract.amount": amount,
            "contract.payment_frequency": contract_doc["payment_frequency"],
            "updated_at": now
        }}
    )

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="CREATE_VENDOR_CONTRACT",
        entity="VENDOR_CONTRACT",
        entity_id=contract_id,
        details=f"Created contract {contract_id} with PDF for vendor {vendor_id} (₹{amount:,.2f})"
    )

    return True, f"Contract {contract_id} created successfully with attached PDF.", contract_doc


def renew_vendor_contract(manager_user: dict, contract_id: str, data: dict) -> tuple[bool, str]:
    db = get_db()
    old_contract = db.vendor_contracts.find_one({"contract_id": contract_id})
    if not old_contract:
        return False, "Contract not found."

    new_end_date = data.get("new_end_date", "").strip()
    try:
        new_amount = float(data.get("new_amount") or data.get("amount") or old_contract["amount"])
    except (ValueError, TypeError):
        new_amount = old_contract["amount"]

    if not new_end_date:
        return False, "New renewal end date is required."

    # Mark old contract as RENEWED
    db.vendor_contracts.update_one(
        {"contract_id": contract_id},
        {"$set": {"status": "RENEWED", "renewed_at": datetime.now()}}
    )

    # Create new contract
    new_con_id = get_next_sequence("vendor_contract", prefix="CON", padding=3)
    new_contract = {
        "contract_id": new_con_id,
        "vendor_id": old_contract["vendor_id"],
        "vendor_name": old_contract["vendor_name"],
        "service_category": old_contract["service_category"],
        "start_date": old_contract["end_date"],
        "end_date": new_end_date,
        "amount": new_amount,
        "payment_frequency": data.get("payment_frequency", old_contract.get("payment_frequency", "MONTHLY")),
        "terms": data.get("terms", old_contract.get("terms", "")),
        "renewal_date": new_end_date,
        "previous_contract_id": contract_id,
        "status": "ACTIVE",
        "created_by": manager_user.get("user_id"),
        "created_at": datetime.now()
    }
    db.vendor_contracts.insert_one(new_contract)

    # Update vendor master
    db.vendors.update_one(
        {"vendor_id": old_contract["vendor_id"]},
        {"$set": {
            "contract.start_date": old_contract["end_date"],
            "contract.end_date": new_end_date,
            "contract.amount": new_amount,
            "updated_at": datetime.now()
        }}
    )

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="RENEW_VENDOR_CONTRACT",
        entity="VENDOR_CONTRACT",
        entity_id=new_con_id,
        details=f"Renewed contract from {contract_id} -> {new_con_id} till {new_end_date}"
    )

    return True, f"Contract renewed successfully with ID {new_con_id}."


# =========================================================================
# VENDOR SERVICE REQUESTS & COMPLAINTS INTEGRATION
# =========================================================================

def create_vendor_service_request(manager_user: dict, data: dict, complaint_id: str = None) -> tuple[bool, str, dict]:
    db = get_db()
    vendor_id = data.get("vendor_id", "").strip()
    vendor = db.vendors.find_one({"vendor_id": vendor_id})
    if not vendor:
        return False, "Selected vendor not found.", None

    description = data.get("description", "").strip()
    priority = data.get("priority", "MEDIUM").upper()
    scheduled_date = data.get("scheduled_date", date.today().strftime("%Y-%m-%d")).strip()
    asset_id = data.get("asset_id", "").strip() or None
    asset_name = data.get("asset_name", "").strip() or None

    if not description:
        return False, "Service request description is required.", None

    request_id = get_next_sequence("vendor_service_request", prefix="VSR", padding=3)
    now = datetime.now()

    vsr_doc = {
        "request_id": request_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor["company"]["name"],
        "vendor_phone": vendor["company"]["phone"],
        "service_category": vendor["service"]["category"],
        "asset_id": asset_id,
        "asset_name": asset_name,
        "complaint_id": complaint_id,
        "description": description,
        "priority": priority,
        "scheduled_date": scheduled_date,
        "status": "ASSIGNED",  # PENDING, ASSIGNED, IN_PROGRESS, COMPLETED, CANCELLED
        "service_report": None,
        "rating": None,
        "before_images": [],
        "after_images": [],
        "created_by": manager_user.get("user_id"),
        "created_by_name": manager_user.get("name"),
        "created_at": now,
        "updated_at": now,
        "completed_at": None
    }

    db.vendor_service_requests.insert_one(vsr_doc)

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="CREATE_VENDOR_SERVICE_REQUEST",
        entity="VENDOR_SERVICE",
        entity_id=request_id,
        details=f"Dispatched service request {request_id} to {vendor['company']['name']} ({vendor['service']['category']})"
    )

    return True, f"Vendor Service Request {request_id} dispatched to {vendor['company']['name']}.", vsr_doc


def assign_complaint_to_vendor(manager_user: dict, complaint_id: str, vendor_id: str, description: str = "", priority: str = "MEDIUM") -> tuple[bool, str]:
    """Assigns a resident complaint directly to an external Vendor."""
    db = get_db()
    complaint = db.complaints.find_one({"complaint_id": complaint_id})
    if not complaint:
        return False, "Complaint not found."

    vendor = db.vendors.find_one({"vendor_id": vendor_id})
    if not vendor:
        return False, "Vendor not found."

    now = datetime.now()
    # Create vendor service request
    vsr_data = {
        "vendor_id": vendor_id,
        "description": description or f"Complaint {complaint_id}: {complaint.get('title')} - {complaint.get('description')}",
        "priority": priority or complaint.get("priority", "MEDIUM"),
        "scheduled_date": date.today().strftime("%Y-%m-%d"),
        "asset_name": f"Flat {complaint.get('flat')}"
    }
    success, msg, vsr = create_vendor_service_request(manager_user, vsr_data, complaint_id=complaint_id)
    if not success:
        return False, msg

    history_entry = {
        "status": "ASSIGNED",
        "changed_by": manager_user["user_id"],
        "changed_by_name": manager_user["name"],
        "role": manager_user.get("role", "MANAGER"),
        "timestamp": now.isoformat(),
        "notes": f"Assigned to external vendor {vendor['company']['name']} ({vendor['service']['category']}). Service Ref: {vsr['request_id']}."
    }

    db.complaints.update_one(
        {"complaint_id": complaint_id},
        {
            "$set": {
                "status": "ASSIGNED",
                "assigned_type": "VENDOR",
                "vendor_id": vendor_id,
                "vendor_name": vendor["company"]["name"],
                "vendor_service_id": vsr["request_id"],
                "updated_at": now
            },
            "$push": {"status_history": history_entry}
        }
    )

    # Notify resident
    create_notification(
        user_id=complaint["resident_id"],
        title=f"Complaint {complaint_id} Assigned to Vendor",
        message=f"Your complaint has been assigned to external specialist {vendor['company']['name']} ({vendor['company']['phone']}). Service Request: {vsr['request_id']}.",
        link="/resident/complaints",
        n_type="INFO"
    )

    return True, f"Complaint {complaint_id} assigned to Vendor {vendor['company']['name']} (Service Ref: {vsr['request_id']})."


def complete_vendor_service_request(manager_user: dict, request_id: str, data: dict) -> tuple[bool, str]:
    db = get_db()
    vsr = db.vendor_service_requests.find_one({"request_id": request_id})
    if not vsr:
        return False, "Service request not found."

    report = data.get("service_report", "").strip()
    status = data.get("status", "COMPLETED").upper()
    now = datetime.now()

    db.vendor_service_requests.update_one(
        {"request_id": request_id},
        {"$set": {
            "status": status,
            "service_report": report,
            "completed_at": now.isoformat() if status == "COMPLETED" else None,
            "updated_at": now
        }}
    )

    # If linked to a complaint, update complaint as RESOLVED
    if vsr.get("complaint_id") and status == "COMPLETED":
        complaint_id = vsr["complaint_id"]
        history_entry = {
            "status": "RESOLVED",
            "changed_by": manager_user["user_id"],
            "changed_by_name": manager_user["name"],
            "role": manager_user.get("role", "MANAGER"),
            "timestamp": now.isoformat(),
            "notes": f"Resolved by vendor {vsr['vendor_name']}. Report: {report}"
        }
        db.complaints.update_one(
            {"complaint_id": complaint_id},
            {
                "$set": {
                    "status": "RESOLVED",
                    "resolution_notes": report,
                    "updated_at": now
                },
                "$push": {"status_history": history_entry}
            }
        )
        complaint = db.complaints.find_one({"complaint_id": complaint_id})
        if complaint:
            create_notification(
                user_id=complaint["resident_id"],
                title=f"Complaint {complaint_id} Resolved",
                message=f"Vendor {vsr['vendor_name']} completed maintenance. Please rate the service.",
                link=f"/resident/complaints/{complaint_id}",
                n_type="SUCCESS"
            )

    # Increment completed service count on vendor
    if status == "COMPLETED":
        db.vendors.update_one(
            {"vendor_id": vsr["vendor_id"]},
            {"$inc": {"performance.services_completed": 1}}
        )

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="COMPLETE_VENDOR_SERVICE",
        entity="VENDOR_SERVICE",
        entity_id=request_id,
        details=f"Marked service request {request_id} as {status}"
    )

    return True, f"Service Request {request_id} status updated to {status}."


def rate_vendor_performance(manager_user: dict, request_id: str, vendor_id: str, data: dict) -> tuple[bool, str]:
    db = get_db()
    try:
        quality = int(data.get("rating_quality", 5))
        response_time = int(data.get("rating_response", 5))
        professionalism = int(data.get("rating_professionalism", 5))
        overall = round((quality + response_time + professionalism) / 3.0, 1)
    except (ValueError, TypeError):
        overall = 5.0

    remarks = data.get("remarks", "").strip()

    rating_doc = {
        "quality": quality,
        "response_time": response_time,
        "professionalism": professionalism,
        "overall": overall,
        "remarks": remarks,
        "rated_by": manager_user.get("user_id"),
        "rated_by_name": manager_user.get("name"),
        "rated_at": datetime.now().isoformat()
    }

    # Update request
    db.vendor_service_requests.update_one(
        {"request_id": request_id},
        {"$set": {"rating": rating_doc, "updated_at": datetime.now()}}
    )

    # Recompute vendor average rating
    all_ratings = list(db.vendor_service_requests.find({"vendor_id": vendor_id, "rating.overall": {"$exists": True}}))
    if all_ratings:
        avg_rating = round(sum(r["rating"]["overall"] for r in all_ratings) / len(all_ratings), 1)
        db.vendors.update_one(
            {"vendor_id": vendor_id},
            {"$set": {
                "performance.average_rating": avg_rating,
                "performance.ratings_count": len(all_ratings)
            }}
        )

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="RATE_VENDOR",
        entity="VENDOR",
        entity_id=vendor_id,
        details=f"Rated vendor {vendor_id} ({overall}/5.0) for service {request_id}"
    )

    return True, f"Rating of {overall} / 5.0 recorded for {vendor_id}."


# =========================================================================
# VENDOR PAYMENTS
# =========================================================================

def record_vendor_payment(manager_user: dict, data: dict) -> tuple[bool, str, dict]:
    db = get_db()
    vendor_id = data.get("vendor_id", "").strip()
    vendor = db.vendors.find_one({"vendor_id": vendor_id})
    if not vendor:
        return False, "Vendor not found.", None

    invoice_number = data.get("invoice_number", "").strip() or f"INV-{uuid.uuid4().hex[:6].upper()}"
    service_description = data.get("service_description", "").strip() or f"{vendor['service']['category']} AMC payment"
    try:
        amount = float(data.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0.0

    if amount <= 0:
        return False, "A valid payment amount is required.", None

    payment_id = get_next_sequence("vendor_payment", prefix="VPAY", padding=3)
    due_date = data.get("due_date", date.today().strftime("%Y-%m-%d"))
    payment_status = data.get("status", "PAID").upper()
    payment_method = data.get("payment_method", "BANK_TRANSFER").upper()
    transaction_id = data.get("transaction_id", "").strip() or (f"TXN-VND-{uuid.uuid4().hex[:8].upper()}" if payment_status == "PAID" else None)
    payment_date = datetime.now().isoformat() if payment_status == "PAID" else None

    payment_doc = {
        "payment_id": payment_id,
        "vendor_id": vendor_id,
        "vendor_name": vendor["company"]["name"],
        "contract_id": data.get("contract_id"),
        "invoice_number": invoice_number,
        "service_description": service_description,
        "amount": amount,
        "due_date": due_date,
        "payment_date": payment_date,
        "payment_method": payment_method,
        "transaction_id": transaction_id,
        "remarks": data.get("remarks", "").strip(),
        "status": payment_status,
        "settled_by": manager_user.get("user_id") if payment_status == "PAID" else None,
        "settled_at": datetime.now().isoformat() if payment_status == "PAID" else None,
        "created_by": manager_user.get("user_id"),
        "created_at": datetime.now()
    }

    db.vendor_payments.insert_one(payment_doc)

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="RECORD_VENDOR_PAYMENT",
        entity="VENDOR_PAYMENT",
        entity_id=payment_id,
        details=f"Recorded vendor payment of ₹{amount:,.2f} to {vendor['company']['name']} ({payment_status})"
    )

    return True, f"Vendor Payment {payment_id} recorded successfully.", payment_doc


def settle_vendor_payment(manager_user: dict, payment_id: str, data: dict) -> tuple[bool, str, dict]:
    """Settles a pending vendor invoice/payment record. Prevents duplicate settlements."""
    db = get_db()
    pay = db.vendor_payments.find_one({"payment_id": payment_id})
    if not pay:
        return False, "Vendor payment record not found.", None

    if pay.get("status") == "PAID":
        return False, "Vendor payment has already been settled.", pay

    payment_method = data.get("payment_method", "BANK_TRANSFER").upper()
    transaction_id = data.get("transaction_id", "").strip() or f"TXN-SETTLE-{uuid.uuid4().hex[:8].upper()}"
    remarks = data.get("remarks", "").strip()
    payment_date_str = data.get("payment_date", "").strip() or datetime.now().strftime("%Y-%m-%d")

    now = datetime.now()

    update_fields = {
        "status": "PAID",
        "payment_method": payment_method,
        "transaction_id": transaction_id,
        "remarks": remarks,
        "payment_date": payment_date_str,
        "settled_by": manager_user.get("user_id"),
        "settled_at": now.isoformat(),
        "updated_at": now
    }

    db.vendor_payments.update_one(
        {"payment_id": payment_id},
        {"$set": update_fields}
    )

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="SETTLE_VENDOR_PAYMENT",
        entity="VENDOR_PAYMENT",
        entity_id=payment_id,
        details=f"Settled payment {payment_id} (₹{pay.get('amount', 0):,.2f}) for {pay.get('vendor_name')} via {payment_method} Ref: {transaction_id}"
    )

    updated_doc = db.vendor_payments.find_one({"payment_id": payment_id})
    return True, f"Vendor payment {payment_id} settled successfully.", updated_doc


def get_vendor_expiring_warnings(vendor_id: str = None) -> list:
    """Returns list of contracts expiring in 30 days or less with warning badges."""
    db = get_db()
    today = date.today()
    query = {"status": "ACTIVE"}
    if vendor_id:
        query["vendor_id"] = vendor_id

    contracts = list(db.vendor_contracts.find(query))
    warnings = []

    for c in contracts:
        end_date_str = c.get("end_date") or c.get("contract", {}).get("end_date")
        if not end_date_str:
            continue
        try:
            end_d = datetime.strptime(end_date_str, "%Y-%m-%d").date()
            days_left = (end_d - today).days
            if 0 <= days_left <= 30:
                warnings.append({
                    "contract_id": c.get("contract_id"),
                    "vendor_id": c.get("vendor_id"),
                    "vendor_name": c.get("vendor_name"),
                    "service_category": c.get("service_category"),
                    "days_left": days_left,
                    "end_date": end_date_str,
                    "file_id": c.get("file_id") or c.get("document", {}).get("file_id"),
                    "warning_level": "CRITICAL" if days_left <= 7 else ("HIGH" if days_left <= 15 else "MEDIUM"),
                    "message": f"{c.get('vendor_name')} ({c.get('service_category')}) contract expires in {days_left} day{'s' if days_left != 1 else ''}."
                })
        except Exception:
            pass

    warnings.sort(key=lambda x: x["days_left"])
    return warnings



# =========================================================================
# VENDOR DOCUMENTS
# =========================================================================

def upload_vendor_document(manager_user: dict, vendor_id: str, title: str, doc_type: str, file_storage) -> tuple[bool, str]:
    db = get_db()
    vendor = db.vendors.find_one({"vendor_id": vendor_id})
    if not vendor:
        return False, "Vendor not found."

    if not file_storage or file_storage.filename == "":
        return False, "Please choose a document to upload."

    try:
        saved = save_file_to_gridfs(file_storage)
        if not saved:
            return False, "Failed to upload document."
        
        saved["title"] = title or file_storage.filename
        saved["doc_type"] = doc_type or "Contract / Compliance"
        saved["uploaded_by"] = manager_user.get("user_id")
        saved["uploaded_at"] = datetime.now().isoformat()

        db.vendors.update_one(
            {"vendor_id": vendor_id},
            {"$push": {"documents": saved}, "$set": {"updated_at": datetime.now()}}
        )

        log_action(
            user_id=manager_user.get("user_id"),
            user_name=manager_user.get("name"),
            role=manager_user.get("role", "MANAGER"),
            action="UPLOAD_VENDOR_DOC",
            entity="VENDOR",
            entity_id=vendor_id,
            details=f"Uploaded '{saved['title']}' for vendor {vendor_id}"
        )
        return True, f"Document '{saved['title']}' uploaded successfully."
    except Exception as e:
        return False, f"Upload error: {str(e)}"


# =========================================================================
# VENDOR ANALYTICS & STATS
# =========================================================================

def get_vendor_analytics() -> dict:
    """Computes MongoDB aggregations for vendor management."""
    db = get_db()

    total_vendors = db.vendors.count_documents({})
    active_vendors = db.vendors.count_documents({"status": "ACTIVE"})
    inactive_vendors = db.vendors.count_documents({"status": {"$in": ["INACTIVE", "SUSPENDED", "BLACKLISTED"]}})

    # Contracts expiring within 30 days
    today_str = date.today().strftime("%Y-%m-%d")
    expiry_threshold = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    expiring_contracts_count = db.vendor_contracts.count_documents({
        "status": "ACTIVE",
        "end_date": {"$gte": today_str, "$lte": expiry_threshold}
    })

    # Pending services
    pending_services_count = db.vendor_service_requests.count_documents({
        "status": {"$in": ["PENDING", "ASSIGNED", "IN_PROGRESS"]}
    })

    # Pending payments
    pending_payments_count = db.vendor_payments.count_documents({"status": {"$in": ["PENDING", "OVERDUE"]}})

    # Total expenses paid
    pay_pipeline = [
        {"$match": {"status": "PAID"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]
    pay_res = list(db.vendor_payments.aggregate(pay_pipeline))
    total_paid_expenses = pay_res[0]["total"] if pay_res else 0.0

    # Vendors by category
    by_category_pipeline = [
        {"$group": {"_id": "$service.category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    by_category = list(db.vendors.aggregate(by_category_pipeline))

    return {
        "total_vendors": total_vendors,
        "active_vendors": active_vendors,
        "inactive_vendors": inactive_vendors,
        "expiring_contracts_count": expiring_contracts_count,
        "pending_services_count": pending_services_count,
        "pending_payments_count": pending_payments_count,
        "total_paid_expenses": total_paid_expenses,
        "by_category": by_category
    }
