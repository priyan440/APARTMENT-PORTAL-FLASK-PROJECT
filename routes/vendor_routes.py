from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, abort
from datetime import datetime
from services.auth_service import login_required, role_required
from services.gridfs_service import stream_gridfs_file
from services.vendor_service import (
    VENDOR_CATEGORIES,
    VENDOR_STATUSES,
    CONTRACT_STATUSES,
    SERVICE_REQUEST_STATUSES,
    PAYMENT_STATUSES,
    create_vendor,
    update_vendor,
    change_vendor_status,
    create_vendor_contract,
    renew_vendor_contract,
    create_vendor_service_request,
    assign_complaint_to_vendor,
    complete_vendor_service_request,
    rate_vendor_performance,
    record_vendor_payment,
    settle_vendor_payment,
    upload_vendor_document,
    get_vendor_analytics,
    get_vendor_expiring_warnings
)
from database.mongodb import get_db

vendor_bp = Blueprint("vendor", __name__)

@vendor_bp.route("/manager/vendors/document/<file_id>", methods=["GET"])
def download_vendor_document(file_id):
    """Stream GridFS document for vendor attachment."""
    response = stream_gridfs_file(file_id)
    if not response:
        abort(404)
    return response

@vendor_bp.route("/manager/vendors/contracts/<contract_id>/pdf", methods=["GET"])
def view_contract_pdf(contract_id):
    """Secure endpoint to view/download contract PDF."""
    db = get_db()
    contract = db.vendor_contracts.find_one({"contract_id": contract_id})
    if not contract:
        abort(404)
    file_id = contract.get("file_id") or contract.get("document", {}).get("file_id")
    if not file_id:
        abort(404)
    response = stream_gridfs_file(file_id)
    if not response:
        abort(404)
    return response

@vendor_bp.route("/manager/vendors", methods=["GET"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_vendors_list():
    db = get_db()
    category_filter = request.args.get("category")
    status_filter = request.args.get("status")
    search_query = request.args.get("q", "").strip()

    query = {}
    if category_filter:
        query["service.category"] = category_filter
    if status_filter:
        query["status"] = status_filter
    if search_query:
        query["$or"] = [
            {"company.name": {"$regex": search_query, "$options": "i"}},
            {"company.contact_person": {"$regex": search_query, "$options": "i"}},
            {"company.phone": {"$regex": search_query, "$options": "i"}},
            {"vendor_id": {"$regex": search_query, "$options": "i"}}
        ]

    vendors = list(db.vendors.find(query).sort("created_at", -1))
    analytics = get_vendor_analytics()
    expiring_warnings = get_vendor_expiring_warnings()

    # Contracts and services counts
    for v in vendors:
        v["contracts_count"] = db.vendor_contracts.count_documents({"vendor_id": v["vendor_id"]})
        v["pending_services"] = db.vendor_service_requests.count_documents({"vendor_id": v["vendor_id"], "status": {"$in": ["PENDING", "ASSIGNED", "IN_PROGRESS"]}})

    return render_template(
        "manager/vendors.html",
        vendors=vendors,
        analytics=analytics,
        expiring_warnings=expiring_warnings,
        categories=VENDOR_CATEGORIES,
        statuses=VENDOR_STATUSES,
        active_category=category_filter,
        active_status=status_filter,
        search_query=search_query
    )


@vendor_bp.route("/manager/vendors/create", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_create_vendor():
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    doc_files = request.files.getlist("documents")
    success, msg, vendor = create_vendor(mgr, request.form, doc_files)
    if success:
        flash(msg, "success")
        return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vendor["vendor_id"]))
    else:
        flash(msg, "danger")
        return redirect(url_for("vendor.manager_vendors_list"))


@vendor_bp.route("/manager/vendors/<vendor_id>", methods=["GET"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_vendor_detail(vendor_id):
    db = get_db()
    vendor = db.vendors.find_one({"vendor_id": vendor_id})
    if not vendor:
        flash("Vendor not found.", "danger")
        return redirect(url_for("vendor.manager_vendors_list"))

    contracts = list(db.vendor_contracts.find({"vendor_id": vendor_id}).sort("start_date", -1))
    service_requests = list(db.vendor_service_requests.find({"vendor_id": vendor_id}).sort("created_at", -1))
    payments = list(db.vendor_payments.find({"vendor_id": vendor_id}).sort("created_at", -1))
    audit_logs = list(db.audit_logs.find({"entity_id": vendor_id}).sort("timestamp", -1).limit(20))
    expiring_warnings = get_vendor_expiring_warnings(vendor_id=vendor_id)

    active_tab = request.args.get("tab", "overview")

    return render_template(
        "manager/vendor_detail.html",
        vendor=vendor,
        contracts=contracts,
        service_requests=service_requests,
        payments=payments,
        audit_logs=audit_logs,
        expiring_warnings=expiring_warnings,
        categories=VENDOR_CATEGORIES,
        statuses=VENDOR_STATUSES,
        active_tab=active_tab
    )


@vendor_bp.route("/manager/vendors/<vendor_id>/update", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_update_vendor(vendor_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    success, msg = update_vendor(mgr, vendor_id, request.form)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vendor_id))


@vendor_bp.route("/manager/vendors/<vendor_id>/status", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_change_vendor_status(vendor_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    new_status = request.form.get("status", "ACTIVE")
    reason = request.form.get("reason", "")
    success, msg = change_vendor_status(mgr, vendor_id, new_status, reason)
    if success:
        flash(msg, "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vendor_id))


@vendor_bp.route("/manager/vendors/<vendor_id>/contracts/create", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_add_contract(vendor_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    contract_file = request.files.get("contract_pdf") or request.files.get("contract") or request.files.get("document_file")
    success, msg, _ = create_vendor_contract(mgr, vendor_id, request.form, contract_file=contract_file)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vendor_id, tab="contracts"))



@vendor_bp.route("/manager/vendors/contracts/<contract_id>/renew", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_renew_contract(contract_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    contract = db.vendor_contracts.find_one({"contract_id": contract_id})
    vendor_id = contract["vendor_id"] if contract else None
    success, msg = renew_vendor_contract(mgr, contract_id, request.form)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vendor_id, tab="contracts"))


@vendor_bp.route("/manager/vendors/service-requests/create", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_create_service_request():
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    success, msg, vsr = create_vendor_service_request(mgr, request.form)
    if success:
        flash(msg, "success")
        return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vsr["vendor_id"], tab="services"))
    else:
        flash(msg, "danger")
        return redirect(url_for("vendor.manager_vendors_list"))


@vendor_bp.route("/manager/vendors/service-requests/<request_id>/complete", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_complete_service_request(request_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    vsr = db.vendor_service_requests.find_one({"request_id": request_id})
    vendor_id = vsr["vendor_id"] if vsr else None
    success, msg = complete_vendor_service_request(mgr, request_id, request.form)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vendor_id, tab="services"))


@vendor_bp.route("/manager/vendors/service-requests/<request_id>/rate", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_rate_vendor_service(request_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    vsr = db.vendor_service_requests.find_one({"request_id": request_id})
    vendor_id = vsr["vendor_id"] if vsr else None
    success, msg = rate_vendor_performance(mgr, request_id, vendor_id, request.form)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vendor_id, tab="performance"))


@vendor_bp.route("/manager/vendors/payments/create", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_record_payment():
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    success, msg, pay = record_vendor_payment(mgr, request.form)
    if success:
        flash(msg, "success")
        return redirect(url_for("vendor.manager_vendor_detail", vendor_id=pay["vendor_id"], tab="payments"))
    else:
        flash(msg, "danger")
        return redirect(url_for("vendor.manager_vendors_list"))


@vendor_bp.route("/manager/vendors/payments/<payment_id>/settle", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_settle_payment(payment_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    pay = db.vendor_payments.find_one({"payment_id": payment_id})
    vendor_id = pay["vendor_id"] if pay else request.form.get("vendor_id")
    
    success, msg, _ = settle_vendor_payment(mgr, payment_id, request.form)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    
    if vendor_id:
        return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vendor_id, tab="payments"))
    return redirect(url_for("vendor.manager_vendors_list"))



@vendor_bp.route("/manager/vendors/<vendor_id>/documents/upload", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_upload_doc(vendor_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    title = request.form.get("title", "")
    doc_type = request.form.get("doc_type", "Agreement / Compliance")
    file_storage = request.files.get("document_file")
    success, msg = upload_vendor_document(mgr, vendor_id, title, doc_type, file_storage)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("vendor.manager_vendor_detail", vendor_id=vendor_id, tab="documents"))


@vendor_bp.route("/manager/complaints/<complaint_id>/assign-vendor", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_assign_complaint_vendor(complaint_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    vendor_id = request.form.get("vendor_id")
    notes = request.form.get("notes", "")
    priority = request.form.get("priority", "MEDIUM")
    success, msg = assign_complaint_to_vendor(mgr, complaint_id, vendor_id, notes, priority)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("manager.complaints"))
