from database.mongodb import get_db
import pymongo

def create_indexes():
    db = get_db()
    print("Creating MongoDB indexes...")

    # Users
    db.users.create_index([("email", pymongo.ASCENDING)], unique=True)
    db.users.create_index([("role", pymongo.ASCENDING)])
    db.users.create_index([("user_id", pymongo.ASCENDING)], unique=True)
    db.users.create_index([("block", pymongo.ASCENDING), ("flat", pymongo.ASCENDING)])

    # Blocks & Flats
    db.blocks.create_index([("block_id", pymongo.ASCENDING)], unique=True)
    db.flats.create_index([("flat_number", pymongo.ASCENDING)], unique=True)
    db.flats.create_index([("block_id", pymongo.ASCENDING)])

    # Complaints
    db.complaints.create_index([("complaint_id", pymongo.ASCENDING)], unique=True)
    db.complaints.create_index([("resident_id", pymongo.ASCENDING)])
    db.complaints.create_index([("status", pymongo.ASCENDING)])
    db.complaints.create_index([("technician_id", pymongo.ASCENDING)])
    db.complaints.create_index([("category", pymongo.ASCENDING)])
    db.complaints.create_index([("block", pymongo.ASCENDING)])

    # Amenities & Bookings
    db.amenities.create_index([("amenity_id", pymongo.ASCENDING)], unique=True)
    db.bookings.create_index([("booking_id", pymongo.ASCENDING)], unique=True)
    db.bookings.create_index([("amenity_id", pymongo.ASCENDING), ("booking_date", pymongo.ASCENDING)])
    db.bookings.create_index([("status", pymongo.ASCENDING)])
    db.bookings.create_index([("resident_id", pymongo.ASCENDING)])

    # Bills & Payments
    db.bills.create_index([("bill_id", pymongo.ASCENDING)], unique=True)
    db.bills.create_index([("resident_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)])
    db.payments.create_index([("payment_id", pymongo.ASCENDING)], unique=True)
    db.payments.create_index([("bill_id", pymongo.ASCENDING)])

    # Visitors & Deliveries
    db.visitors.create_index([("visitor_id", pymongo.ASCENDING)], unique=True)
    db.visitors.create_index([("resident_id", pymongo.ASCENDING)])
    db.visitors.create_index([("status", pymongo.ASCENDING)])
    db.deliveries.create_index([("delivery_id", pymongo.ASCENDING)], unique=True)

    # Announcements, Notifications, Audit Logs, SOS
    db.announcements.create_index([("announcement_id", pymongo.ASCENDING)], unique=True)
    db.announcements.create_index([("target", pymongo.ASCENDING)])
    db.notifications.create_index([("user_id", pymongo.ASCENDING), ("is_read", pymongo.ASCENDING)])
    db.audit_logs.create_index([("timestamp", pymongo.DESCENDING)])
    db.emergency_alerts.create_index([("status", pymongo.ASCENDING)])

    # Community Collections & Special Contributions
    db.community_collections.create_index([("collection_id", pymongo.ASCENDING)], unique=True)
    db.community_collections.create_index([("status", pymongo.ASCENDING)])
    db.community_collections.create_index([("type", pymongo.ASCENDING)])
    db.community_collections.create_index([("payment_deadline", pymongo.ASCENDING)])
    db.community_collection_payments.create_index([("payment_id", pymongo.ASCENDING)], unique=True)
    db.community_collection_payments.create_index([("collection_id", pymongo.ASCENDING)])
    db.community_collection_payments.create_index([("resident_id", pymongo.ASCENDING), ("status", pymongo.ASCENDING)])
    db.community_collection_payments.create_index([("status", pymongo.ASCENDING)])
    db.community_collection_payments.create_index([("block", pymongo.ASCENDING), ("flat", pymongo.ASCENDING)])

    # Vendor Management
    db.vendors.create_index([("vendor_id", pymongo.ASCENDING)], unique=True)
    db.vendors.create_index([("service.category", pymongo.ASCENDING)])
    db.vendors.create_index([("status", pymongo.ASCENDING)])
    db.vendor_contracts.create_index([("contract_id", pymongo.ASCENDING)], unique=True)
    db.vendor_contracts.create_index([("vendor_id", pymongo.ASCENDING)])
    db.vendor_contracts.create_index([("status", pymongo.ASCENDING)])
    db.vendor_contracts.create_index([("end_date", pymongo.ASCENDING)])
    db.vendor_service_requests.create_index([("request_id", pymongo.ASCENDING)], unique=True)
    db.vendor_service_requests.create_index([("vendor_id", pymongo.ASCENDING)])
    db.vendor_service_requests.create_index([("complaint_id", pymongo.ASCENDING)])
    db.vendor_service_requests.create_index([("status", pymongo.ASCENDING)])
    db.vendor_payments.create_index([("payment_id", pymongo.ASCENDING)], unique=True)
    db.vendor_payments.create_index([("vendor_id", pymongo.ASCENDING)])
    db.vendor_payments.create_index([("status", pymongo.ASCENDING)])

    # Daily Help Management
    db.daily_help.create_index([("help_id", pymongo.ASCENDING)], unique=True)
    db.daily_help.create_index([("resident_id", pymongo.ASCENDING)])
    db.daily_help.create_index([("flat_id", pymongo.ASCENDING)])
    db.daily_help.create_index([("verification_status", pymongo.ASCENDING)])
    db.daily_help.create_index([("status", pymongo.ASCENDING)])
    db.daily_help.create_index([("person.service_type", pymongo.ASCENDING)])
    db.daily_help_attendance.create_index([("attendance_id", pymongo.ASCENDING)], unique=True)
    db.daily_help_attendance.create_index([("help_id", pymongo.ASCENDING), ("date", pymongo.ASCENDING)])
    db.daily_help_attendance.create_index([("resident_id", pymongo.ASCENDING)])
    db.daily_help_attendance.create_index([("date", pymongo.ASCENDING), ("status", pymongo.ASCENDING)])

    # Vehicles & Parking Slots (Unique Partial Index on Active Assignments)
    db.vehicles.create_index([("vehicle_id", pymongo.ASCENDING)], unique=True)
    db.vehicles.create_index([("resident_id", pymongo.ASCENDING)])
    db.vehicles.create_index([("status", pymongo.ASCENDING)])
    db.vehicles.create_index([("registration_number", pymongo.ASCENDING)])
    db.vehicles.create_index([("block", pymongo.ASCENDING), ("flat", pymongo.ASCENDING)])
    
    # Check for duplicates before enforcing unique index
    try:
        dup_pipeline = [
            {"$match": {"parking_slot": {"$ne": None}, "status": "ACTIVE"}},
            {"$group": {
                "_id": "$parking_slot",
                "count": {"$sum": 1},
                "vehicles": {"$push": "$vehicle_id"},
                "residents": {"$push": "$resident_id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        duplicates = list(db.vehicles.aggregate(dup_pipeline))
        if duplicates:
            print(f"[PARKING INDEX WARNING] Found {len(duplicates)} duplicate active parking assignments: {duplicates}")
        else:
            db.vehicles.create_index(
                [("parking_slot", pymongo.ASCENDING)],
                unique=True,
                partialFilterExpression={"status": "ACTIVE"}
            )
    except Exception as e:
        print(f"Vehicle parking index note: {e}")

    # Residents collection (for dual users/residents support)
    db.residents.create_index([("resident_id", pymongo.ASCENDING)], unique=True)
    db.residents.create_index([("user_id", pymongo.ASCENDING)], unique=True)
    db.residents.create_index([("email", pymongo.ASCENDING)])
    db.residents.create_index([("block", pymongo.ASCENDING), ("flat_number", pymongo.ASCENDING)])

    # Service Work Reports
    db.service_work_reports.create_index([("report_id", pymongo.ASCENDING)], unique=True)
    db.service_work_reports.create_index([("complaint_id", pymongo.ASCENDING)])
    db.service_work_reports.create_index([("technician_id", pymongo.ASCENDING)])
    db.service_work_reports.create_index([("vendor_id", pymongo.ASCENDING)])
    db.service_work_reports.create_index([("status", pymongo.ASCENDING)])

    print("All indexes created successfully.")

if __name__ == "__main__":
    create_indexes()
