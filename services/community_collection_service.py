import uuid
from datetime import datetime, date
from database.mongodb import get_db, get_next_sequence
from services.notification_service import create_notification
from services.audit_service import log_action

COLLECTION_TYPES = [
    "Festival",
    "Tour",
    "Community Event",
    "Cultural Event",
    "Sports Event",
    "Emergency Contribution",
    "Special Maintenance",
    "Charity",
    "Other"
]

COLLECTION_STATUSES = [
    "DRAFT",
    "ACTIVE",
    "PAYMENT_OPEN",
    "PAYMENT_CLOSED",
    "COMPLETED",
    "CANCELLED"
]

PAYMENT_STATUSES = [
    "PENDING",
    "PAID",
    "OVERDUE",
    "FAILED",
    "REFUNDED"
]

REGISTRATION_STATUSES = [
    "INTERESTED",
    "REGISTERED",
    "PAYMENT_PENDING",
    "CONFIRMED",
    "CANCELLED"
]


def sync_overdue_payments():
    """Auto-flags pending payments as OVERDUE if the deadline has passed."""
    db = get_db()
    today_str = date.today().strftime("%Y-%m-%d")
    db.community_collection_payments.update_many(
        {
            "status": "PENDING",
            "payment_deadline": {"$lt": today_str}
        },
        {"$set": {"status": "OVERDUE", "updated_at": datetime.now()}}
    )


def create_community_collection(manager_user: dict, data: dict) -> tuple[bool, str, dict]:
    """
    Creates a new community collection/event and generates payments for mandatory targets.
    """
    db = get_db()
    title = data.get("title", "").strip()
    c_type = data.get("type", "Festival").strip()
    description = data.get("description", "").strip()
    event_date = data.get("event_date", "").strip()
    payment_deadline = data.get("payment_deadline", "").strip()
    payment_type = data.get("payment_type", "MANDATORY").strip().upper()  # MANDATORY or OPTIONAL
    target_type = data.get("target_type", "ALL").strip().upper()  # ALL, BLOCK, FLATS, SELECTED_RESIDENTS
    
    try:
        base_amount = float(data.get("amount", 0) or 0)
    except (ValueError, TypeError):
        base_amount = 0.0

    if not title or not event_date or not payment_deadline:
        return False, "Title, event date, and payment deadline are required.", None

    if base_amount <= 0 and payment_type == "MANDATORY":
        return False, "A valid contribution amount is required for mandatory collections.", None

    # Pricing Tiers (for tours/events with differentiated pricing)
    has_tier_pricing = data.get("has_tier_pricing") in ["true", "on", True]
    pricing_tiers = {}
    if has_tier_pricing:
        try:
            pricing_tiers = {
                "ADULT": float(data.get("tier_adult", base_amount) or base_amount),
                "CHILD": float(data.get("tier_child", base_amount * 0.6) or 0),
                "SENIOR": float(data.get("tier_senior", base_amount * 0.8) or 0)
            }
        except (ValueError, TypeError):
            pricing_tiers = {"ADULT": base_amount}

    # Target configuration
    target = {"type": target_type}
    if target_type == "BLOCK":
        blocks = data.getlist("target_blocks") if hasattr(data, "getlist") else data.get("target_blocks", [])
        if isinstance(blocks, str):
            blocks = [b.strip().upper() for b in blocks.split(",") if b.strip()]
        target["blocks"] = blocks or ["A"]
    elif target_type == "FLATS":
        flats = data.getlist("target_flats") if hasattr(data, "getlist") else data.get("target_flats", [])
        if isinstance(flats, str):
            flats = [f.strip().upper() for f in flats.split(",") if f.strip()]
        target["flats"] = flats
    elif target_type == "SELECTED_RESIDENTS":
        resident_ids = data.getlist("target_residents") if hasattr(data, "getlist") else data.get("target_residents", [])
        if isinstance(resident_ids, str):
            resident_ids = [r.strip() for r in resident_ids.split(",") if r.strip()]
        target["resident_ids"] = resident_ids

    max_participants = None
    if data.get("max_participants"):
        try:
            max_participants = int(data.get("max_participants"))
        except ValueError:
            max_participants = None

    allow_overdue = data.get("allow_overdue_payments") in ["true", "on", True, "yes"]
    recurrence = data.get("recurrence", "ONE_TIME").upper()

    collection_id = get_next_sequence("community_collection", prefix="COL", padding=3)

    col_doc = {
        "collection_id": collection_id,
        "title": title,
        "type": c_type,
        "description": description,
        "amount": base_amount,
        "has_tier_pricing": has_tier_pricing,
        "pricing_tiers": pricing_tiers,
        "event_date": event_date,
        "payment_deadline": payment_deadline,
        "target": target,
        "payment_type": payment_type,  # MANDATORY / OPTIONAL
        "max_participants": max_participants,
        "allow_overdue_payments": allow_overdue,
        "recurrence": recurrence,
        "status": "ACTIVE",  # ACTIVE, PAYMENT_OPEN, PAYMENT_CLOSED, COMPLETED, CANCELLED
        "created_by": manager_user.get("user_id", "MGR001"),
        "created_by_name": manager_user.get("name", "Apartment Manager"),
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }

    db.community_collections.insert_one(col_doc)

    # Resolve target residents
    target_residents = get_targeted_residents(target)

    # If MANDATORY, automatically create payment records for all target residents
    created_payments_count = 0
    if payment_type == "MANDATORY":
        for res in target_residents:
            pay_id = get_next_sequence("community_payment", prefix="CPAY", padding=3)
            pay_doc = {
                "payment_id": pay_id,
                "collection_id": collection_id,
                "collection_title": title,
                "collection_type": c_type,
                "resident_id": res["user_id"],
                "resident_name": res["name"],
                "flat": res.get("flat", "N/A"),
                "block": res.get("block", "A"),
                "amount": base_amount,
                "total_amount": base_amount,
                "participant_count": 1,
                "participants": [
                    {
                        "name": res["name"],
                        "member_id": res["user_id"],
                        "relationship": "Self",
                        "category": "ADULT",
                        "amount": base_amount
                    }
                ],
                "status": "PENDING",  # PENDING, PAID, OVERDUE, CANCELLED
                "registration_status": "CONFIRMED",
                "payment_deadline": payment_deadline,
                "payment": {
                    "transaction_id": None,
                    "paid_at": None,
                    "method": None,
                    "receipt_no": None
                },
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            db.community_collection_payments.insert_one(pay_doc)
            created_payments_count += 1

            # Send Notification
            create_notification(
                user_id=res["user_id"],
                title="🔔 New Community Payment Obligation",
                message=f"{title} ({c_type}): Contribution ₹{base_amount:,.2f} is due on {payment_deadline}.",
                link="/resident/community-payments",
                n_type="WARNING"
            )
    else:
        # OPTIONAL: Notify residents about invitation / opening to join
        for res in target_residents:
            create_notification(
                user_id=res["user_id"],
                title="🎉 New Community Event Invitation",
                message=f"{title} ({c_type}) is now open for registration! Event date: {event_date}.",
                link="/resident/community-payments",
                n_type="INFO"
            )

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="CREATE_COMMUNITY_COLLECTION",
        entity="COMMUNITY_COLLECTION",
        entity_id=collection_id,
        details=f"Created {payment_type} collection '{title}' (₹{base_amount}) targeting {len(target_residents)} residents."
    )

    return True, f"Community Collection {collection_id} ('{title}') created successfully with {created_payments_count} resident payment requests generated.", col_doc


def get_targeted_residents(target: dict) -> list:
    """Find active residents according to target criteria."""
    db = get_db()
    t_type = target.get("type", "ALL")
    query = {"role": "RESIDENT", "status": "ACTIVE"}

    if t_type == "BLOCK":
        blocks = target.get("blocks", [])
        if blocks:
            query["block"] = {"$in": blocks}
    elif t_type == "FLATS":
        flats = target.get("flats", [])
        if flats:
            query["flat"] = {"$in": flats}
    elif t_type == "SELECTED_RESIDENTS":
        resident_ids = target.get("resident_ids", [])
        if resident_ids:
            query["user_id"] = {"$in": resident_ids}

    return list(db.users.find(query).sort("flat", 1))


def update_community_collection(manager_user: dict, collection_id: str, data: dict) -> tuple[bool, str]:
    """Updates collection details with security guards."""
    db = get_db()
    col = db.community_collections.find_one({"collection_id": collection_id})
    if not col:
        return False, "Collection not found."

    paid_count = db.community_collection_payments.count_documents({"collection_id": collection_id, "status": "PAID"})

    title = data.get("title", col["title"]).strip()
    description = data.get("description", col.get("description", "")).strip()
    event_date = data.get("event_date", col["event_date"]).strip()
    payment_deadline = data.get("payment_deadline", col["payment_deadline"]).strip()
    status = data.get("status", col.get("status", "ACTIVE")).strip()
    allow_overdue = data.get("allow_overdue_payments") in ["true", "on", True, "yes"]

    update_fields = {
        "title": title,
        "description": description,
        "event_date": event_date,
        "payment_deadline": payment_deadline,
        "status": status,
        "allow_overdue_payments": allow_overdue,
        "updated_at": datetime.now()
    }

    if data.get("max_participants"):
        try:
            update_fields["max_participants"] = int(data.get("max_participants"))
        except ValueError:
            pass

    # If no payments made yet, allow updating amount
    if paid_count == 0 and data.get("amount"):
        try:
            new_amt = float(data.get("amount"))
            update_fields["amount"] = new_amt
            # Update pending payment records amount
            db.community_collection_payments.update_many(
                {"collection_id": collection_id, "status": "PENDING"},
                {"$set": {"amount": new_amt, "total_amount": new_amt}}
            )
        except ValueError:
            pass

    db.community_collections.update_one({"collection_id": collection_id}, {"$set": update_fields})

    # Update deadline on pending payments if deadline changed
    if payment_deadline != col.get("payment_deadline"):
        db.community_collection_payments.update_many(
            {"collection_id": collection_id, "status": {"$in": ["PENDING", "OVERDUE"]}},
            {"$set": {"payment_deadline": payment_deadline}}
        )

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="UPDATE_COMMUNITY_COLLECTION",
        entity="COMMUNITY_COLLECTION",
        entity_id=collection_id,
        details=f"Updated details for collection {collection_id} (Status: {status})"
    )

    return True, f"Collection {collection_id} updated successfully."


def cancel_community_collection(manager_user: dict, collection_id: str, reason: str = "") -> tuple[bool, str]:
    """Soft cancels a collection, retaining historical financial records."""
    db = get_db()
    col = db.community_collections.find_one({"collection_id": collection_id})
    if not col:
        return False, "Collection not found."

    db.community_collections.update_one(
        {"collection_id": collection_id},
        {"$set": {
            "status": "CANCELLED",
            "cancellation_reason": reason or "Cancelled by manager",
            "cancelled_at": datetime.now(),
            "updated_at": datetime.now()
        }}
    )

    # Cancel unpaid pending payments
    db.community_collection_payments.update_many(
        {"collection_id": collection_id, "status": {"$in": ["PENDING", "OVERDUE"]}},
        {"$set": {"status": "CANCELLED", "registration_status": "CANCELLED", "updated_at": datetime.now()}}
    )

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="CANCEL_COMMUNITY_COLLECTION",
        entity="COMMUNITY_COLLECTION",
        entity_id=collection_id,
        details=f"Cancelled collection {collection_id}. Reason: {reason}"
    )

    return True, f"Collection {collection_id} cancelled. Unsettled payments have been closed."


def register_resident_for_event(resident_user: dict, collection_id: str, form_data: dict) -> tuple[bool, str, dict]:
    """
    Registers a resident and chosen family members for an optional event/tour.
    Calculates amounts server-side from pricing tiers.
    """
    db = get_db()
    col = db.community_collections.find_one({"collection_id": collection_id})
    if not col:
        return False, "Event / Collection not found.", None

    if col.get("status") in ["CANCELLED", "COMPLETED", "PAYMENT_CLOSED"]:
        return False, f"Registration for this event is currently {col.get('status')}.", None

    # Check if already registered and paid
    existing_payment = db.community_collection_payments.find_one({
        "collection_id": collection_id,
        "resident_id": resident_user["user_id"]
    })
    if existing_payment and existing_payment.get("status") == "PAID":
        return False, "You have already completed the payment for this event.", existing_payment

    # Parse participants
    participants = []
    selected_member_ids = form_data.getlist("selected_members") if hasattr(form_data, "getlist") else form_data.get("selected_members", [])
    if isinstance(selected_member_ids, str):
        selected_member_ids = [m.strip() for m in selected_member_ids.split(",") if m.strip()]

    # Pricing logic
    base_amt = float(col.get("amount", 0))
    tiers = col.get("pricing_tiers", {}) or {}
    adult_price = float(tiers.get("ADULT", base_amt))
    child_price = float(tiers.get("CHILD", base_amt * 0.6 if base_amt else 0))
    senior_price = float(tiers.get("SENIOR", base_amt * 0.8 if base_amt else 0))

    # Always include resident if checked (or by default)
    include_self = form_data.get("include_self") in ["true", "on", True, "1", "yes"] or ("self" in selected_member_ids)
    if include_self or not selected_member_ids:
        self_category = form_data.get("category_self", "ADULT").upper()
        amt = adult_price if self_category == "ADULT" else (senior_price if self_category == "SENIOR" else child_price)
        participants.append({
            "name": resident_user["name"],
            "member_id": resident_user["user_id"],
            "relationship": "Self",
            "category": self_category,
            "amount": amt
        })

    # Add selected family members from user's registered list
    user_family = {m["member_id"]: m for m in resident_user.get("family_members", [])}
    for mem_id in selected_member_ids:
        if mem_id in user_family:
            m = user_family[mem_id]
            # determine category from age or form
            cat = form_data.get(f"category_{mem_id}")
            if not cat:
                age = m.get("age", 25)
                if age < 12:
                    cat = "CHILD"
                elif age >= 60:
                    cat = "SENIOR"
                else:
                    cat = "ADULT"
            cat = cat.upper()
            amt = child_price if cat == "CHILD" else (senior_price if cat == "SENIOR" else adult_price)
            participants.append({
                "name": m["name"],
                "member_id": mem_id,
                "relationship": m.get("relationship", "Family"),
                "category": cat,
                "amount": amt
            })

    if not participants:
        return False, "Please select at least one participant.", None

    total_count = len(participants)
    total_amount = sum(p["amount"] for p in participants)

    # Check capacity
    max_part = col.get("max_participants")
    if max_part:
        # Sum current participants across confirmed/paid/registered
        pipeline = [
            {"$match": {"collection_id": collection_id, "status": {"$in": ["PAID", "PENDING"]}, "resident_id": {"$ne": resident_user["user_id"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$participant_count"}}}
        ]
        res = list(db.community_collection_payments.aggregate(pipeline))
        current_registered = res[0]["total"] if res else 0
        if current_registered + total_count > max_part:
            available = max(0, max_part - current_registered)
            return False, f"Cannot register {total_count} members. Only {available} slots remaining for this event.", None

    if existing_payment:
        # Update existing pending record
        db.community_collection_payments.update_one(
            {"payment_id": existing_payment["payment_id"]},
            {"$set": {
                "participants": participants,
                "participant_count": total_count,
                "amount": total_amount,
                "total_amount": total_amount,
                "status": "PENDING",
                "registration_status": "REGISTERED",
                "updated_at": datetime.now()
            }}
        )
        pay_id = existing_payment["payment_id"]
        updated_doc = db.community_collection_payments.find_one({"payment_id": pay_id})
    else:
        pay_id = get_next_sequence("community_payment", prefix="CPAY", padding=3)
        updated_doc = {
            "payment_id": pay_id,
            "collection_id": collection_id,
            "collection_title": col["title"],
            "collection_type": col["type"],
            "resident_id": resident_user["user_id"],
            "resident_name": resident_user["name"],
            "flat": resident_user.get("flat", "N/A"),
            "block": resident_user.get("block", "A"),
            "amount": total_amount,
            "total_amount": total_amount,
            "participant_count": total_count,
            "participants": participants,
            "status": "PENDING",
            "registration_status": "REGISTERED",
            "payment_deadline": col["payment_deadline"],
            "payment": {
                "transaction_id": None,
                "paid_at": None,
                "method": None,
                "receipt_no": None
            },
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        db.community_collection_payments.insert_one(updated_doc)

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="REGISTER_EVENT",
        entity="COMMUNITY_PAYMENT",
        entity_id=pay_id,
        details=f"Registered {total_count} participants for '{col['title']}'. Total payable: ₹{total_amount:,.2f}"
    )

    return True, f"Successfully registered {total_count} participant(s) for '{col['title']}'! Amount payable: ₹{total_amount:,.2f}.", updated_doc


def decline_optional_event(resident_user: dict, collection_id: str) -> tuple[bool, str]:
    """Resident declines an optional event."""
    db = get_db()
    existing = db.community_collection_payments.find_one({
        "collection_id": collection_id,
        "resident_id": resident_user["user_id"]
    })
    if existing:
        if existing.get("status") == "PAID":
            return False, "You have already paid for this event and cannot decline directly. Contact manager for assistance."
        db.community_collection_payments.update_one(
            {"payment_id": existing["payment_id"]},
            {"$set": {"status": "CANCELLED", "registration_status": "CANCELLED", "updated_at": datetime.now()}}
        )
    return True, "You have declined this event invitation."


def process_community_payment(resident_user: dict, payment_id: str, payment_method: str = "UPI") -> tuple[bool, str, dict]:
    """
    Processes simulated payment for a community collection / event contribution.
    Prevents duplicate payment, generates receipt number, creates notifications, and logs audit.
    """
    db = get_db()
    pay_doc = db.community_collection_payments.find_one({
        "payment_id": payment_id,
        "resident_id": resident_user["user_id"]
    })
    if not pay_doc:
        return False, "Payment obligation record not found or does not belong to you.", None

    if pay_doc.get("status") == "PAID":
        return False, "This contribution has already been paid and settled.", pay_doc

    col = db.community_collections.find_one({"collection_id": pay_doc["collection_id"]})
    if col and col.get("status") == "CANCELLED":
        return False, "This collection has been cancelled by the management.", None

    # Check deadline if overdue acceptance is false
    today_str = date.today().strftime("%Y-%m-%d")
    if col and not col.get("allow_overdue_payments", True):
        if pay_doc.get("payment_deadline", "") < today_str:
            return False, "The payment deadline for this collection has passed and overdue payments are not accepted.", None

    now = datetime.now()
    tx_id = f"TXN-COMM-{uuid.uuid4().hex[:10].upper()}"
    receipt_no = f"CPR-{now.year}-{get_next_sequence('receipt_cpr', prefix='', padding=4)}"
    amount = float(pay_doc.get("total_amount", pay_doc.get("amount", 0)))

    payment_details = {
        "transaction_id": tx_id,
        "paid_at": now.isoformat(),
        "method": payment_method.upper(),
        "receipt_no": receipt_no,
        "settled_amount": amount
    }

    # Update payment document
    db.community_collection_payments.update_one(
        {"payment_id": payment_id},
        {"$set": {
            "status": "PAID",
            "registration_status": "CONFIRMED",
            "payment": payment_details,
            "paid_at": now.isoformat(),
            "updated_at": now
        }}
    )

    # Insert into universal payments collection for unified audit & accounting
    universal_pay_id = get_next_sequence("payment", prefix="PAY", padding=3)
    universal_pay_doc = {
        "payment_id": universal_pay_id,
        "reference_id": payment_id,
        "collection_id": pay_doc["collection_id"],
        "category": "COMMUNITY_COLLECTION",
        "title": pay_doc.get("collection_title", "Community Contribution"),
        "resident_id": resident_user["user_id"],
        "resident_name": resident_user["name"],
        "flat": pay_doc.get("flat"),
        "block": pay_doc.get("block"),
        "amount": amount,
        "payment_date": now.isoformat(),
        "payment_method": payment_method.upper(),
        "transaction_ref": tx_id,
        "receipt_no": receipt_no,
        "status": "SUCCESS",
        "created_at": now
    }
    db.payments.insert_one(universal_pay_doc)

    # Send Notification to Resident
    create_notification(
        user_id=resident_user["user_id"],
        title="✓ Payment Successful: Community Contribution",
        message=f"Your ₹{amount:,.2f} payment for {pay_doc.get('collection_title')} has been received (Receipt: {receipt_no}).",
        link=f"/resident/community-payments/{payment_id}/receipt",
        n_type="SUCCESS"
    )

    # Notify Managers
    managers = list(db.users.find({"role": "MANAGER"}))
    for mgr in managers:
        create_notification(
            user_id=mgr["user_id"],
            title="Community Contribution Received",
            message=f"{resident_user['name']} (Flat {pay_doc.get('flat')}) paid ₹{amount:,.2f} for '{pay_doc.get('collection_title')}'.",
            link=f"/manager/community-collections/{pay_doc['collection_id']}",
            n_type="SUCCESS"
        )

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="PAY_COMMUNITY_COLLECTION",
        entity="COMMUNITY_PAYMENT",
        entity_id=payment_id,
        details=f"Paid ₹{amount:,.2f} for {pay_doc.get('collection_title')} ({pay_doc['collection_id']}). Txn: {tx_id}, Receipt: {receipt_no}"
    )

    updated_doc = db.community_collection_payments.find_one({"payment_id": payment_id})
    return True, f"Payment of ₹{amount:,.2f} completed successfully! Receipt No: {receipt_no}", updated_doc


def get_collection_statistics(collection_id: str) -> dict:
    """Computes detailed MongoDB aggregation metrics for a specific collection."""
    db = get_db()
    col = db.community_collections.find_one({"collection_id": collection_id})
    if not col:
        return {}

    today_str = date.today().strftime("%Y-%m-%d")

    payments = list(db.community_collection_payments.find({"collection_id": collection_id}))
    
    total_records = len(payments)
    paid_records = [p for p in payments if p.get("status") == "PAID"]
    pending_records = [p for p in payments if p.get("status") == "PENDING" and p.get("payment_deadline", "") >= today_str]
    overdue_records = [p for p in payments if p.get("status") == "OVERDUE" or (p.get("status") == "PENDING" and p.get("payment_deadline", "") < today_str)]

    paid_count = len(paid_records)
    pending_count = len(pending_records)
    overdue_count = len(overdue_records)

    total_expected = sum(float(p.get("total_amount", p.get("amount", 0))) for p in payments if p.get("status") != "CANCELLED")
    total_collected = sum(float(p.get("total_amount", p.get("amount", 0))) for p in paid_records)
    total_pending = sum(float(p.get("total_amount", p.get("amount", 0))) for p in pending_records)
    total_overdue = sum(float(p.get("total_amount", p.get("amount", 0))) for p in overdue_records)

    collection_rate = round((total_collected / total_expected * 100) if total_expected > 0 else 0, 1)

    # Participant metrics (especially for tours)
    total_participants = sum(p.get("participant_count", 1) for p in payments if p.get("status") != "CANCELLED")
    paid_participants = sum(p.get("participant_count", 1) for p in paid_records)

    # Block-wise collection breakdown
    block_pipeline = [
        {"$match": {"collection_id": collection_id, "status": {"$ne": "CANCELLED"}}},
        {"$group": {
            "_id": "$block",
            "expected": {"$sum": "$total_amount"},
            "collected": {"$sum": {"$cond": [{"$eq": ["$status", "PAID"]}, "$total_amount", 0]}},
            "pending": {"$sum": {"$cond": [{"$ne": ["$status", "PAID"]}, "$total_amount", 0]}},
            "paid_count": {"$sum": {"$cond": [{"$eq": ["$status", "PAID"]}, 1, 0]}},
            "total_count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    block_stats = list(db.community_collection_payments.aggregate(block_pipeline))

    return {
        "collection": col,
        "total_records": total_records,
        "paid_count": paid_count,
        "pending_count": pending_count,
        "overdue_count": overdue_count,
        "total_expected": total_expected,
        "total_collected": total_collected,
        "total_pending": total_pending,
        "total_overdue": total_overdue,
        "collection_rate": collection_rate,
        "total_participants": total_participants,
        "paid_participants": paid_participants,
        "block_stats": block_stats
    }


def get_all_collections_summary() -> dict:
    """Overall dashboard statistics across all community collections."""
    db = get_db()
    sync_overdue_payments()

    total_collections = db.community_collections.count_documents({})
    active_collections = db.community_collections.count_documents({"status": {"$in": ["ACTIVE", "PAYMENT_OPEN"]}})
    completed_collections = db.community_collections.count_documents({"status": "COMPLETED"})
    cancelled_collections = db.community_collections.count_documents({"status": "CANCELLED"})

    # Aggregate financial sums
    pipeline = [
        {"$match": {"status": {"$ne": "CANCELLED"}}},
        {"$group": {
            "_id": None,
            "total_expected": {"$sum": "$total_amount"},
            "total_collected": {"$sum": {"$cond": [{"$eq": ["$status", "PAID"]}, "$total_amount", 0]}},
            "total_pending": {"$sum": {"$cond": [{"$eq": ["$status", "PENDING"]}, "$total_amount", 0]}},
            "total_overdue": {"$sum": {"$cond": [{"$eq": ["$status", "OVERDUE"]}, "$total_amount", 0]}},
            "total_paid_count": {"$sum": {"$cond": [{"$eq": ["$status", "PAID"]}, 1, 0]}},
            "total_pending_count": {"$sum": {"$cond": [{"$eq": ["$status", "PENDING"]}, 1, 0]}},
            "total_overdue_count": {"$sum": {"$cond": [{"$eq": ["$status", "OVERDUE"]}, 1, 0]}}
        }}
    ]
    fin_res = list(db.community_collection_payments.aggregate(pipeline))
    fin = fin_res[0] if fin_res else {
        "total_expected": 0, "total_collected": 0, "total_pending": 0, "total_overdue": 0,
        "total_paid_count": 0, "total_pending_count": 0, "total_overdue_count": 0
    }

    collection_rate = round((fin["total_collected"] / fin["total_expected"] * 100) if fin.get("total_expected", 0) > 0 else 0, 1)

    # Category-wise breakdown
    cat_pipeline = [
        {"$match": {"status": {"$ne": "CANCELLED"}}},
        {"$group": {
            "_id": "$collection_type",
            "collected": {"$sum": {"$cond": [{"$eq": ["$status", "PAID"]}, "$total_amount", 0]}},
            "expected": {"$sum": "$total_amount"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"collected": -1}}
    ]
    by_category = list(db.community_collection_payments.aggregate(cat_pipeline))

    return {
        "total_collections": total_collections,
        "active_collections": active_collections,
        "completed_collections": completed_collections,
        "cancelled_collections": cancelled_collections,
        "total_expected": fin.get("total_expected", 0),
        "total_collected": fin.get("total_collected", 0),
        "total_pending": fin.get("total_pending", 0),
        "total_overdue": fin.get("total_overdue", 0),
        "total_paid_count": fin.get("total_paid_count", 0),
        "total_pending_count": fin.get("total_pending_count", 0),
        "total_overdue_count": fin.get("total_overdue_count", 0),
        "collection_rate": collection_rate,
        "by_category": by_category
    }


def send_collection_reminders(manager_user: dict, collection_id: str) -> tuple[int, str]:
    """Sends reminder notifications to all residents with pending or overdue status for a collection."""
    db = get_db()
    col = db.community_collections.find_one({"collection_id": collection_id})
    if not col:
        return 0, "Collection not found."

    pending_payments = list(db.community_collection_payments.find({
        "collection_id": collection_id,
        "status": {"$in": ["PENDING", "OVERDUE"]}
    }))

    sent_count = 0
    for p in pending_payments:
        amount = float(p.get("total_amount", p.get("amount", 0)))
        create_notification(
            user_id=p["resident_id"],
            title=f"⚠️ Payment Reminder: {col['title']}",
            message=f"Gentle reminder: Contribution of ₹{amount:,.2f} for '{col['title']}' is pending (Deadline: {col['payment_deadline']}).",
            link="/resident/community-payments",
            n_type="WARNING"
        )
        sent_count += 1

    log_action(
        user_id=manager_user.get("user_id"),
        user_name=manager_user.get("name"),
        role=manager_user.get("role", "MANAGER"),
        action="SEND_COLLECTION_REMINDER",
        entity="COMMUNITY_COLLECTION",
        entity_id=collection_id,
        details=f"Sent {sent_count} payment reminders for collection '{col['title']}'"
    )

    return sent_count, f"Successfully dispatched {sent_count} payment reminders to residents."
