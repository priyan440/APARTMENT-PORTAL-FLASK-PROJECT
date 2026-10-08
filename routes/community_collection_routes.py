from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from io import BytesIO
from datetime import datetime, date
from services.auth_service import login_required, role_required
from services.community_collection_service import (
    COLLECTION_TYPES,
    COLLECTION_STATUSES,
    PAYMENT_STATUSES,
    create_community_collection,
    update_community_collection,
    cancel_community_collection,
    register_resident_for_event,
    decline_optional_event,
    process_community_payment,
    get_collection_statistics,
    get_all_collections_summary,
    send_collection_reminders,
    sync_overdue_payments
)
from services.receipt_service import generate_community_payment_pdf
from database.mongodb import get_db

community_bp = Blueprint("community", __name__)

# =========================================================================
# MANAGER & ADMIN ROUTES
# =========================================================================

@community_bp.route("/manager/community-collections", methods=["GET"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_collections_list():
    db = get_db()
    sync_overdue_payments()

    status_filter = request.args.get("status")
    type_filter = request.args.get("type")

    query = {}
    if status_filter:
        query["status"] = status_filter
    if type_filter:
        query["type"] = type_filter

    collections = list(db.community_collections.find(query).sort("created_at", -1))
    
    # Attach computed metrics to each collection
    for col in collections:
        stats = get_collection_statistics(col["collection_id"])
        col["stats"] = stats

    summary = get_all_collections_summary()
    blocks = list(db.blocks.find())
    flats = list(db.flats.find().sort("flat_number", 1))
    residents = list(db.users.find({"role": "RESIDENT", "status": "ACTIVE"}).sort("name", 1))

    return render_template(
        "manager/community_collections.html",
        collections=collections,
        summary=summary,
        collection_types=COLLECTION_TYPES,
        collection_statuses=COLLECTION_STATUSES,
        blocks=blocks,
        flats=flats,
        residents=residents,
        active_status=status_filter,
        active_type=type_filter
    )


@community_bp.route("/manager/community-collections/create", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_create_collection():
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    success, msg, col_doc = create_community_collection(mgr, request.form)
    if success:
        flash(msg, "success")
        return redirect(url_for("community.manager_collection_detail", collection_id=col_doc["collection_id"]))
    else:
        flash(msg, "danger")
        return redirect(url_for("community.manager_collections_list"))


@community_bp.route("/manager/community-collections/<collection_id>", methods=["GET"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_collection_detail(collection_id):
    db = get_db()
    sync_overdue_payments()

    col = db.community_collections.find_one({"collection_id": collection_id})
    if not col:
        flash("Community collection not found.", "danger")
        return redirect(url_for("community.manager_collections_list"))

    stats = get_collection_statistics(collection_id)

    # Filter payments
    status_filter = request.args.get("status")
    block_filter = request.args.get("block")
    search_query = request.args.get("q", "").strip()

    pay_query = {"collection_id": collection_id}
    if status_filter:
        pay_query["status"] = status_filter
    if block_filter:
        pay_query["block"] = block_filter
    if search_query:
        pay_query["$or"] = [
            {"resident_name": {"$regex": search_query, "$options": "i"}},
            {"flat": {"$regex": search_query, "$options": "i"}},
            {"payment_id": {"$regex": search_query, "$options": "i"}}
        ]

    payments = list(db.community_collection_payments.find(pay_query).sort("flat", 1))
    blocks = list(db.blocks.find())

    return render_template(
        "manager/community_collection_detail.html",
        collection=col,
        stats=stats,
        payments=payments,
        blocks=blocks,
        collection_types=COLLECTION_TYPES,
        collection_statuses=COLLECTION_STATUSES,
        filters={
            "status": status_filter,
            "block": block_filter,
            "q": search_query
        }
    )


@community_bp.route("/manager/community-collections/<collection_id>/update", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_update_collection(collection_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    success, msg = update_community_collection(mgr, collection_id, request.form)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("community.manager_collection_detail", collection_id=collection_id))


@community_bp.route("/manager/community-collections/<collection_id>/cancel", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_cancel_collection(collection_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    reason = request.form.get("reason", "Cancelled by management")
    success, msg = cancel_community_collection(mgr, collection_id, reason)
    if success:
        flash(msg, "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("community.manager_collection_detail", collection_id=collection_id))


@community_bp.route("/manager/community-collections/<collection_id>/remind", methods=["POST"])
@login_required
@role_required("MANAGER", "ADMIN")
def manager_remind_collection(collection_id):
    db = get_db()
    mgr = db.users.find_one({"user_id": session["user_id"]})
    count, msg = send_collection_reminders(mgr, collection_id)
    if count > 0:
        flash(msg, "success")
    else:
        flash(msg, "warning")
    return redirect(url_for("community.manager_collection_detail", collection_id=collection_id))


# =========================================================================
# RESIDENT ROUTES
# =========================================================================

@community_bp.route("/resident/community-payments", methods=["GET"])
@login_required
@role_required("RESIDENT")
def resident_community_payments():
    db = get_db()
    sync_overdue_payments()
    user_id = session["user_id"]
    user = db.users.find_one({"user_id": user_id})

    # 1. Resident's payments (mandatory generated or registered optional)
    payments = list(db.community_collection_payments.find({"resident_id": user_id}).sort("created_at", -1))
    
    # 2. Registered collection IDs for this resident
    registered_col_ids = {p["collection_id"]: p for p in payments}

    # 3. Available Optional Events open to this resident (not yet registered or registered)
    user_block = user.get("block", "A")
    user_flat = user.get("flat", "")

    optional_collections = list(db.community_collections.find({
        "payment_type": "OPTIONAL",
        "status": {"$in": ["ACTIVE", "PAYMENT_OPEN"]},
        "$or": [
            {"target.type": "ALL"},
            {"target.type": "BLOCK", "target.blocks": user_block},
            {"target.type": "FLATS", "target.flats": user_flat},
            {"target.type": "SELECTED_RESIDENTS", "target.resident_ids": user_id}
        ]
    }).sort("event_date", 1))

    # Decorate optional events with user's status and remaining capacity
    for oc in optional_collections:
        c_id = oc["collection_id"]
        oc["user_payment"] = registered_col_ids.get(c_id)
        if oc.get("max_participants"):
            p_res = list(db.community_collection_payments.aggregate([
                {"$match": {"collection_id": c_id, "status": {"$in": ["PAID", "PENDING"]}}},
                {"$group": {"_id": None, "total": {"$sum": "$participant_count"}}}
            ]))
            registered_slots = p_res[0]["total"] if p_res else 0
            oc["slots_taken"] = registered_slots
            oc["slots_left"] = max(0, oc["max_participants"] - registered_slots)
        else:
            oc["slots_left"] = None

    pending_payments = [p for p in payments if p.get("status") in ["PENDING", "OVERDUE"]]
    paid_payments = [p for p in payments if p.get("status") == "PAID"]

    return render_template(
        "resident/community_payments.html",
        user=user,
        payments=payments,
        pending_payments=pending_payments,
        paid_payments=paid_payments,
        optional_collections=optional_collections,
        registered_col_ids=registered_col_ids
    )


@community_bp.route("/resident/community-collections/<collection_id>/join", methods=["POST"])
@login_required
@role_required("RESIDENT")
def resident_join_event(collection_id):
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    success, msg, pay_doc = register_resident_for_event(user, collection_id, request.form)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "danger")
    return redirect(url_for("community.resident_community_payments"))


@community_bp.route("/resident/community-collections/<collection_id>/decline", methods=["POST"])
@login_required
@role_required("RESIDENT")
def resident_decline_event(collection_id):
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    success, msg = decline_optional_event(user, collection_id)
    if success:
        flash(msg, "info")
    else:
        flash(msg, "danger")
    return redirect(url_for("community.resident_community_payments"))


@community_bp.route("/resident/community-payments/<payment_id>/pay", methods=["POST"])
@login_required
@role_required("RESIDENT")
def resident_pay_collection(payment_id):
    db = get_db()
    user = db.users.find_one({"user_id": session["user_id"]})
    method = request.form.get("payment_method", "UPI")
    success, msg, pay_doc = process_community_payment(user, payment_id, method)
    if success:
        flash(msg, "success")
        return redirect(url_for("community.resident_payment_receipt", payment_id=payment_id))
    else:
        flash(msg, "danger")
        return redirect(url_for("community.resident_community_payments"))


@community_bp.route("/resident/community-payments/<payment_id>/receipt", methods=["GET"])
@login_required
@role_required("RESIDENT", "MANAGER", "ADMIN")
def resident_payment_receipt(payment_id):
    db = get_db()
    user_id = session["user_id"]
    user_role = session.get("role")

    query = {"payment_id": payment_id}
    if user_role == "RESIDENT":
        query["resident_id"] = user_id

    payment = db.community_collection_payments.find_one(query)
    if not payment or payment.get("status") != "PAID":
        flash("Receipt is only accessible for settled contributions.", "warning")
        return redirect(url_for("community.resident_community_payments"))

    collection = db.community_collections.find_one({"collection_id": payment["collection_id"]}) or {}
    return render_template("resident/community_payment_receipt.html", payment=payment, collection=collection)


@community_bp.route("/resident/community-payments/<payment_id>/receipt/pdf", methods=["GET"])
@login_required
@role_required("RESIDENT", "MANAGER", "ADMIN")
def download_community_payment_pdf(payment_id):
    db = get_db()
    user_id = session["user_id"]
    user_role = session.get("role")

    query = {"payment_id": payment_id}
    if user_role == "RESIDENT":
        query["resident_id"] = user_id

    payment = db.community_collection_payments.find_one(query)
    if not payment or payment.get("status") != "PAID":
        flash("Receipt is only accessible for settled contributions.", "warning")
        return redirect(url_for("community.resident_community_payments"))

    collection = db.community_collections.find_one({"collection_id": payment["collection_id"]}) or {}
    pdf_bytes = generate_community_payment_pdf(collection, payment)

    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"Community_Payment_Receipt_{payment_id}.pdf"
    )
