import uuid
from datetime import datetime, date
from database.mongodb import get_db, get_next_sequence
from services.notification_service import create_notification
from services.audit_service import log_action

def generate_bill(manager_user: dict, data: dict) -> tuple[bool, str, dict]:
    db = get_db()
    flat_number = data.get("flat", "").strip().upper()
    block = data.get("block", "").strip().upper()
    month_year = data.get("month_year", "").strip() # e.g. "October 2026"
    due_date = data.get("due_date", "").strip()     # e.g. "2026-10-25"

    if not flat_number or not month_year or not due_date:
        return False, "Flat, month/year, and due date are required.", None

    resident = db.users.find_one({"role": "RESIDENT", "flat": flat_number, "status": "ACTIVE"})
    if not resident:
        return False, f"No active resident found registered for Flat {flat_number}.", None

    # Check if bill already exists for this flat and month
    existing = db.bills.find_one({"flat": flat_number, "month_year": month_year})
    if existing:
        return False, f"A bill for {month_year} has already been issued for Flat {flat_number} ({existing['bill_id']}).", None

    maint = float(data.get("maintenance_charge", 2500))
    water = float(data.get("water_charge", 400))
    parking = float(data.get("parking_charge", 300))
    other = float(data.get("other_charge", 100))
    late_fee = float(data.get("late_fee", 0))
    total_amount = round(maint + water + parking + other + late_fee, 2)

    bill_id = get_next_sequence("bill", prefix="BILL", padding=3)
    bill_doc = {
        "bill_id": bill_id,
        "resident_id": resident["user_id"],
        "resident_name": resident["name"],
        "flat": flat_number,
        "block": block or resident.get("block", "A"),
        "month_year": month_year,
        "due_date": due_date,
        "components": {
            "maintenance_charge": maint,
            "water_charge": water,
            "parking_charge": parking,
            "other_charge": other,
            "late_fee": late_fee
        },
        "total_amount": total_amount,
        "status": "PENDING", # PENDING, PAID, OVERDUE
        "payment_id": None,
        "paid_at": None,
        "created_at": datetime.now(),
        "created_by": manager_user["user_id"]
    }

    db.bills.insert_one(bill_doc)

    create_notification(
        user_id=resident["user_id"],
        title="New Maintenance Bill Generated",
        message=f"Maintenance bill {bill_id} for {month_year} amounting to ₹{total_amount:,.2f} is due on {due_date}.",
        link="/resident/bills",
        n_type="WARNING"
    )

    log_action(
        user_id=manager_user["user_id"],
        user_name=manager_user["name"],
        role=manager_user.get("role", "MANAGER"),
        action="GENERATE_BILL",
        entity="BILL",
        entity_id=bill_id,
        details=f"Generated bill {bill_id} for Flat {flat_number}, amount ₹{total_amount}"
    )

    return True, f"Bill {bill_id} generated successfully for Flat {flat_number}.", bill_doc

def process_test_payment(resident_user: dict, bill_id: str, payment_method: str = "CARD") -> tuple[bool, str, dict]:
    """Safe test simulated payment flow."""
    db = get_db()
    bill = db.bills.find_one({"bill_id": bill_id, "resident_id": resident_user["user_id"]})
    if not bill:
        return False, "Bill not found or does not belong to you.", None

    if bill["status"] == "PAID":
        return False, "This bill has already been settled in full.", None

    now = datetime.now()
    payment_id = get_next_sequence("payment", prefix="PAY", padding=3)
    tx_ref = f"TXN-SIM-{uuid.uuid4().hex[:10].upper()}"

    payment_doc = {
        "payment_id": payment_id,
        "bill_id": bill_id,
        "resident_id": resident_user["user_id"],
        "resident_name": resident_user["name"],
        "flat": bill.get("flat"),
        "block": bill.get("block"),
        "amount": bill["total_amount"],
        "payment_date": now.isoformat(),
        "payment_method": payment_method, # CARD, UPI, NETBANKING
        "transaction_ref": tx_ref,
        "status": "SUCCESS",
        "created_at": now
    }
    db.payments.insert_one(payment_doc)

    # Update bill status to PAID
    db.bills.update_one(
        {"bill_id": bill_id},
        {"$set": {
            "status": "PAID",
            "payment_id": payment_id,
            "paid_at": now.isoformat(),
            "updated_at": now
        }}
    )

    create_notification(
        user_id=resident_user["user_id"],
        title="Payment Successful!",
        message=f"Payment {payment_id} of ₹{bill['total_amount']:,.2f} for bill {bill_id} completed successfully (Txn: {tx_ref}).",
        link=f"/resident/bills/{bill_id}/receipt",
        n_type="SUCCESS"
    )

    # Notify managers
    managers = list(db.users.find({"role": "MANAGER"}))
    for mgr in managers:
        create_notification(
            user_id=mgr["user_id"],
            title="Maintenance Payment Received",
            message=f"{resident_user['name']} (Flat {bill.get('flat')}) paid ₹{bill['total_amount']:,.2f} for {bill.get('month_year')}.",
            link="/manager/bills",
            n_type="SUCCESS"
        )

    log_action(
        user_id=resident_user["user_id"],
        user_name=resident_user["name"],
        role="RESIDENT",
        action="PAY_BILL",
        entity="PAYMENT",
        entity_id=payment_id,
        details=f"Paid ₹{bill['total_amount']} for bill {bill_id}. Ref: {tx_ref}"
    )

    return True, f"Payment of ₹{bill['total_amount']:,.2f} was successful!", payment_doc
