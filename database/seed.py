import sys
import os
from datetime import datetime, timedelta, date

# Add parent directory to path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from werkzeug.security import generate_password_hash
from database.mongodb import get_db
from database.indexes import create_indexes
from services.receipt_service import generate_qr_code_base64

def seed_database():
    db = get_db()
    print("Clearing existing collections for fresh seed...")
    
    # Drop existing collections to ensure a clean state
    collections = [
        "users", "residents", "service_work_reports", "blocks", "flats", "complaints", "amenities", "bookings",
        "bills", "payments", "visitors", "deliveries", "announcements",
        "notifications", "audit_logs", "emergency_alerts", "counters",
        "community_collections", "community_collection_payments",
        "vendors", "vendor_contracts", "vendor_service_requests", "vendor_payments",
        "daily_help", "daily_help_attendance", "vehicles"
    ]
    for col in collections:
        db[col].drop()

    print("Re-creating indexes...")
    create_indexes()

    # 1. Blocks
    blocks_data = [
        {"block_id": "BLK-A", "name": "Block A - Lavender", "code": "A", "total_floors": 6, "description": "East Wing Residential Tower"},
        {"block_id": "BLK-B", "name": "Block B - Magnolia", "code": "B", "total_floors": 6, "description": "West Wing Residential Tower"},
        {"block_id": "BLK-C", "name": "Block C - Orchid", "code": "C", "total_floors": 8, "description": "North Wing Premium Suites"},
        {"block_id": "BLK-D", "name": "Block D - Jasmine", "code": "D", "total_floors": 8, "description": "South Wing Executive Tower"}
    ]
    db.blocks.insert_many(blocks_data)

    # 2. Flats
    flats_data = []
    for blk in ["A", "B", "C", "D"]:
        for floor in range(1, 5):
            for unit in range(1, 5):
                flat_no = f"{blk}-{floor}0{unit}"
                flats_data.append({
                    "flat_id": f"FLT-{flat_no}",
                    "flat_number": flat_no,
                    "block_id": f"BLK-{blk}",
                    "block": blk,
                    "floor": floor,
                    "bhk": 3 if floor >= 3 else 2,
                    "status": "VACANT",
                    "resident_id": None,
                    "resident_name": None
                })
    db.flats.insert_many(flats_data)

    # 3. Users with embedded documents
    users_data = [
        {
            "user_id": "ADM001",
            "name": "Vikram Malhotra",
            "email": "admin@greenwood.com",
            "phone": "+91 98401 11001",
            "password": generate_password_hash("admin123"),
            "role": "ADMIN",
            "status": "ACTIVE",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        },
        {
            "user_id": "MGR001",
            "name": "Anita Deshmukh",
            "email": "manager@greenwood.com",
            "phone": "+91 98402 22002",
            "password": generate_password_hash("manager123"),
            "role": "MANAGER",
            "status": "ACTIVE",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        },
        {
            "user_id": "RES001",
            "name": "Arun Kumar",
            "email": "resident@greenwood.com",
            "phone": "+91 98403 33003",
            "password": generate_password_hash("resident123"),
            "role": "RESIDENT",
            "block": "A",
            "flat": "A-204",
            "resident_type": "OWNER",
            "status": "ACTIVE",
            "family_members": [
                {"member_id": "FAM001", "name": "Meera Kumar", "relationship": "Spouse", "age": 36},
                {"member_id": "FAM002", "name": "Rahul Kumar", "relationship": "Son", "age": 14}
            ],
            "vehicles": [
                {"vehicle_id": "VEH001", "type": "Car", "registration_number": "TN58AB1234", "parking_slot": "P-A24"},
                {"vehicle_id": "VEH002", "type": "Two-Wheeler", "registration_number": "TN58CD5678", "parking_slot": "B-12"}
            ],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        },
        {
            "user_id": "RES002",
            "name": "Priya Sundaram",
            "email": "priya@greenwood.com",
            "phone": "+91 98404 44004",
            "password": generate_password_hash("resident123"),
            "role": "RESIDENT",
            "block": "B",
            "flat": "B-101",
            "resident_type": "TENANT",
            "status": "ACTIVE",
            "family_members": [
                {"member_id": "FAM003", "name": "Deepak Sundaram", "relationship": "Brother", "age": 28}
            ],
            "vehicles": [
                {"vehicle_id": "VEH003", "type": "Car", "registration_number": "KA01MN4567", "parking_slot": "P-B08"}
            ],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        },
        {
            "user_id": "RES003",
            "name": "Karthik Raja",
            "email": "karthik@greenwood.com",
            "phone": "+91 98405 55005",
            "password": generate_password_hash("resident123"),
            "role": "RESIDENT",
            "block": "A",
            "flat": "A-102",
            "resident_type": "OWNER",
            "status": "ACTIVE",
            "family_members": [],
            "vehicles": [],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        },
        {
            "user_id": "TECH001",
            "name": "Ravi Kumar",
            "email": "ravi@greenwood.com",
            "phone": "+91 98406 66006",
            "password": generate_password_hash("tech123"),
            "role": "TECHNICIAN",
            "specialization": "Plumbing",
            "active_tasks": 1,
            "completed_tasks": 18,
            "rating": 4.8,
            "ratings_count": 16,
            "status": "ACTIVE",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        },
        {
            "user_id": "TECH002",
            "name": "Suresh Sharma",
            "email": "suresh@greenwood.com",
            "phone": "+91 98407 77007",
            "password": generate_password_hash("tech123"),
            "role": "TECHNICIAN",
            "specialization": "Electrical",
            "active_tasks": 2,
            "completed_tasks": 24,
            "rating": 4.6,
            "ratings_count": 22,
            "status": "ACTIVE",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        },
        {
            "user_id": "TECH003",
            "name": "Manoj Verma",
            "email": "manoj@greenwood.com",
            "phone": "+91 98408 88008",
            "password": generate_password_hash("tech123"),
            "role": "TECHNICIAN",
            "specialization": "Lift",
            "active_tasks": 0,
            "completed_tasks": 12,
            "rating": 4.9,
            "ratings_count": 11,
            "status": "ACTIVE",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        },
        {
            "user_id": "SEC001",
            "name": "Bahadur Singh",
            "email": "security@greenwood.com",
            "phone": "+91 98409 99009",
            "password": generate_password_hash("security123"),
            "role": "SECURITY",
            "status": "ACTIVE",
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
    ]
    db.users.insert_many(users_data)

    # Populate residents collection
    resident_profiles = []
    for u in users_data:
        if u.get("role") == "RESIDENT":
            resident_profiles.append({
                "resident_id": u["user_id"],
                "user_id": u["user_id"],
                "name": u["name"],
                "email": u["email"],
                "phone": u.get("phone", ""),
                "block": u.get("block", ""),
                "flat_number": u.get("flat", ""),
                "flat": u.get("flat", ""),
                "resident_type": u.get("resident_type", "OWNER"),
                "status": u.get("status", "ACTIVE"),
                "created_at": u.get("created_at", datetime.now()),
                "updated_at": u.get("updated_at", datetime.now())
            })
    if resident_profiles:
        db.residents.insert_many(resident_profiles)

    # Populate dedicated vehicles collection
    initial_vehicles = []
    for u in users_data:
        for v in u.get("vehicles", []):
            initial_vehicles.append({
                "vehicle_id": v["vehicle_id"],
                "resident_id": u["user_id"],
                "resident_name": u["name"],
                "block": u.get("block", ""),
                "flat": u.get("flat", ""),
                "type": v["type"],
                "registration_number": v["registration_number"],
                "parking_slot": v["parking_slot"],
                "status": "ACTIVE",
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            })
    if initial_vehicles:
        db.vehicles.insert_many(initial_vehicles)

    # Mark assigned flats as OCCUPIED
    db.flats.update_one({"flat_number": "A-204"}, {"$set": {"status": "OCCUPIED", "resident_id": "RES001", "resident_name": "Arun Kumar"}})
    db.flats.update_one({"flat_number": "B-101"}, {"$set": {"status": "OCCUPIED", "resident_id": "RES002", "resident_name": "Priya Sundaram"}})
    db.flats.update_one({"flat_number": "A-102"}, {"$set": {"status": "OCCUPIED", "resident_id": "RES003", "resident_name": "Karthik Raja"}})

    # 4. Amenities (Section 8 & 9)
    amenities_data = [
        {
            "amenity_id": "AMN001",
            "name": "Community Hall",
            "description": "Spacious centralized banquet hall with stage, AV system, and dining area.",
            "capacity": 150,
            "operating_hours": {"type": "24_HOURS"},
            "max_duration_hours": 8,
            "requires_approval": True,
            "is_active": True,
            "icon": "fa-building",
            "rules": "Quiet hours after 10 PM. Clean-up required after event."
        },
        {
            "amenity_id": "AMN002",
            "name": "Function Hall",
            "description": "Modern multi-tier function hall ideal for birthdays, anniversaries, and seminars.",
            "capacity": 100,
            "operating_hours": {"type": "24_HOURS"},
            "max_duration_hours": 6,
            "requires_approval": True,
            "is_active": True,
            "icon": "fa-champagne-glasses",
            "rules": "No pyrotechnics or open flames permitted inside."
        },
        {
            "amenity_id": "AMN003",
            "name": "Swimming Pool",
            "description": "Olympic-sized chlorinated pool with kids wading section and lifeguard on duty.",
            "capacity": 25,
            "operating_hours": {
                "type": "FIXED",
                "open": "10:00",
                "close": "18:00"
            },
            "max_duration_hours": 2,
            "requires_approval": True,
            "is_active": True,
            "icon": "fa-person-swimming",
            "rules": "Shower before entering. Proper synthetic swimwear mandatory."
        },
        {
            "amenity_id": "AMN004",
            "name": "Tennis Court",
            "description": "Synthetic tournament-grade turf court with perimeter floodlights.",
            "capacity": 8,
            "operating_hours": {
                "type": "FIXED",
                "open": "10:00",
                "close": "18:00"
            },
            "max_duration_hours": 2,
            "requires_approval": True,
            "is_active": True,
            "icon": "fa-table-tennis-paddle-ball",
            "rules": "Non-marking tennis shoes mandatory. Bring your own rackets."
        },
        {
            "amenity_id": "AMN005",
            "name": "Badminton Court",
            "description": "Double indoor wooden-floor court with climate control.",
            "capacity": 12,
            "operating_hours": {"type": "24_HOURS"},
            "max_duration_hours": 2,
            "requires_approval": True,
            "is_active": True,
            "icon": "fa-shuttlecock",
            "rules": "Indoor non-marking shoes only."
        },
        {
            "amenity_id": "AMN006",
            "name": "Fitness Gym",
            "description": "State-of-the-art cardio equipment, free weights, and cross-fit racks.",
            "capacity": 30,
            "operating_hours": {"type": "24_HOURS"},
            "max_duration_hours": 2,
            "requires_approval": True,
            "is_active": True,
            "icon": "fa-dumbbell",
            "rules": "Carry gym towel and water bottle. Sanitize equipment after use."
        },
        {
            "amenity_id": "AMN007",
            "name": "Indoor Games Room",
            "description": "Billiards, table tennis, foosball, and board games lounge.",
            "capacity": 20,
            "operating_hours": {"type": "24_HOURS"},
            "max_duration_hours": 3,
            "requires_approval": True,
            "is_active": True,
            "icon": "fa-chess",
            "rules": "Handle cues and equipment with care."
        }
    ]
    db.amenities.insert_many(amenities_data)

    # 5. Complaints
    now = datetime.now()
    complaints_data = [
        {
            "complaint_id": "CMP001",
            "title": "Kitchen pipe leaking under sink",
            "category": "Plumbing",
            "description": "Severe water dripping under the main kitchen sink damaging wood cabinet.",
            "priority": "HIGH",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "resident_phone": "+91 98403 33003",
            "flat": "A-204",
            "block": "A",
            "status": "ASSIGNED",
            "technician_id": "TECH001",
            "technician_name": "Ravi Kumar",
            "media": [],
            "status_history": [
                {
                    "status": "OPEN",
                    "changed_by": "RES001",
                    "changed_by_name": "Arun Kumar",
                    "role": "RESIDENT",
                    "timestamp": (now - timedelta(hours=3)).isoformat(),
                    "notes": "Complaint filed."
                },
                {
                    "status": "ASSIGNED",
                    "changed_by": "MGR001",
                    "changed_by_name": "Anita Deshmukh",
                    "role": "MANAGER",
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                    "notes": "Assigned to Ravi Kumar (Plumbing)."
                }
            ],
            "resolution_notes": None,
            "resolution_media": [],
            "rating": None,
            "feedback": None,
            "created_at": now - timedelta(hours=3),
            "updated_at": now - timedelta(hours=1)
        },
        {
            "complaint_id": "CMP002",
            "title": "Corridor light flickering outside flat",
            "category": "Electrical",
            "description": "Ceiling fixture buzzes and flickers constantly in 1st floor corridor.",
            "priority": "LOW",
            "resident_id": "RES002",
            "resident_name": "Priya Sundaram",
            "resident_phone": "+91 98404 44004",
            "flat": "B-101",
            "block": "B",
            "status": "RESOLVED",
            "technician_id": "TECH002",
            "technician_name": "Suresh Sharma",
            "media": [],
            "status_history": [
                {
                    "status": "OPEN",
                    "changed_by": "RES002",
                    "changed_by_name": "Priya Sundaram",
                    "role": "RESIDENT",
                    "timestamp": (now - timedelta(days=2)).isoformat(),
                    "notes": "Reported flickering fixture."
                },
                {
                    "status": "ASSIGNED",
                    "changed_by": "MGR001",
                    "changed_by_name": "Anita Deshmukh",
                    "role": "MANAGER",
                    "timestamp": (now - timedelta(days=2, hours=-1)).isoformat(),
                    "notes": "Assigned to Suresh Sharma."
                },
                {
                    "status": "IN_PROGRESS",
                    "changed_by": "TECH002",
                    "changed_by_name": "Suresh Sharma",
                    "role": "TECHNICIAN",
                    "timestamp": (now - timedelta(days=1)).isoformat(),
                    "notes": "Replaced faulty LED driver."
                },
                {
                    "status": "RESOLVED",
                    "changed_by": "TECH002",
                    "changed_by_name": "Suresh Sharma",
                    "role": "TECHNICIAN",
                    "timestamp": (now - timedelta(hours=12)).isoformat(),
                    "notes": "Tested successfully. Illumination normal."
                }
            ],
            "resolution_notes": "Replaced damaged capacitor and LED driver fixture.",
            "resolution_media": [],
            "rating": 5,
            "feedback": "Quick and professional service by Suresh! Fixed in 10 minutes.",
            "created_at": now - timedelta(days=2),
            "updated_at": now - timedelta(hours=12)
        }
    ]
    db.complaints.insert_many(complaints_data)

    # 6. Amenity Bookings (Sample to test conflict logic)
    future_date = (date.today() + timedelta(days=3)).strftime("%Y-%m-%d")
    qr_b64 = generate_qr_code_base64({
        "booking_id": "BK001",
        "amenity": "Community Hall",
        "date": future_date,
        "time": "10:00-14:00",
        "status": "APPROVED"
    })
    bookings_data = [
        {
            "booking_id": "BK001",
            "amenity_id": "AMN001",
            "amenity_name": "Community Hall",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "flat": "A-204",
            "block": "A",
            "booking_date": future_date,
            "start_time": "10:00",
            "end_time": "14:00",
            "duration_hours": 4.0,
            "purpose": "Family Birthday Celebration",
            "guests_count": 50,
            "status": "APPROVED",
            "created_at": now - timedelta(days=1),
            "updated_at": now - timedelta(hours=18),
            "expires_at": now + timedelta(days=10),
            "approval": {
                "status": "APPROVED",
                "approved_by": "MGR001",
                "approved_by_name": "Anita Deshmukh",
                "approved_at": (now - timedelta(hours=18)).isoformat(),
                "remarks": "Approved. Please maintain clean facility."
            },
            "receipt_number": "RCP-BK001",
            "qr_code_data": qr_b64
        }
    ]
    db.bookings.insert_many(bookings_data)

    # 7. Bills (Section 25 & Demo Scenario 3: Maintenance ₹2,500, Water ₹400, Parking ₹300, Other ₹100 = ₹3,300)
    month_name = date.today().strftime("%B %Y")
    due_date = (date.today() + timedelta(days=15)).strftime("%Y-%m-%d")
    bills_data = [
        {
            "bill_id": "BILL001",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "flat": "A-204",
            "block": "A",
            "month_year": month_name,
            "due_date": due_date,
            "components": {
                "maintenance_charge": 2500.0,
                "water_charge": 400.0,
                "parking_charge": 300.0,
                "other_charge": 100.0,
                "late_fee": 0.0
            },
            "total_amount": 3300.0,
            "status": "PENDING", # Exactly matches Demo Scenario 3!
            "payment_id": None,
            "paid_at": None,
            "created_at": now - timedelta(days=2),
            "created_by": "MGR001"
        },
        {
            "bill_id": "BILL002",
            "resident_id": "RES002",
            "resident_name": "Priya Sundaram",
            "flat": "B-101",
            "block": "B",
            "month_year": month_name,
            "due_date": due_date,
            "components": {
                "maintenance_charge": 2500.0,
                "water_charge": 400.0,
                "parking_charge": 300.0,
                "other_charge": 100.0,
                "late_fee": 0.0
            },
            "total_amount": 3300.0,
            "status": "PAID",
            "payment_id": "PAY001",
            "paid_at": (now - timedelta(days=1)).isoformat(),
            "created_at": now - timedelta(days=5),
            "created_by": "MGR001"
        }
    ]
    db.bills.insert_many(bills_data)

    # 8. Payments
    payments_data = [
        {
            "payment_id": "PAY001",
            "bill_id": "BILL002",
            "resident_id": "RES002",
            "resident_name": "Priya Sundaram",
            "flat": "B-101",
            "block": "B",
            "amount": 3300.0,
            "payment_date": (now - timedelta(days=1)).isoformat(),
            "payment_method": "UPI",
            "transaction_ref": "TXN-SIM-994827104A",
            "status": "SUCCESS",
            "created_at": now - timedelta(days=1)
        }
    ]
    db.payments.insert_many(payments_data)

    # 9. Visitors & Deliveries
    visitors_data = [
        {
            "visitor_id": "VIS001",
            "visitor_name": "Rajesh Sharma",
            "phone": "+91 97110 55443",
            "purpose": "Friend / Dinner",
            "expected_date": date.today().strftime("%Y-%m-%d"),
            "expected_time": "19:00",
            "check_in_time": None,
            "check_out_time": None,
            "status": "EXPECTED",
            "flat": "A-204",
            "block": "A",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "vehicle_number": "TN58ZZ9988",
            "created_at": now - timedelta(hours=4)
        },
        {
            "visitor_id": "VIS002",
            "visitor_name": "Karan Mehra",
            "phone": "+91 98221 66778",
            "purpose": "Home Interior Consultant",
            "expected_date": date.today().strftime("%Y-%m-%d"),
            "expected_time": "11:00",
            "check_in_time": (now - timedelta(minutes=45)).isoformat(),
            "check_out_time": None,
            "status": "CHECKED_IN",
            "flat": "B-101",
            "block": "B",
            "resident_id": "RES002",
            "resident_name": "Priya Sundaram",
            "vehicle_number": "KA04XY1234",
            "created_at": now - timedelta(hours=2)
        }
    ]
    db.visitors.insert_many(visitors_data)

    deliveries_data = [
        {
            "delivery_id": "DEL001",
            "company": "Amazon Prime",
            "delivery_person": "Sunil Das",
            "flat": "A-204",
            "block": "A",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "parcel_details": "Medium cardboard package #9843",
            "arrival_time": (now - timedelta(minutes=30)).isoformat(),
            "collected_at": None,
            "status": "RECEIVED",
            "logged_by": "Bahadur Singh",
            "created_at": now - timedelta(minutes=30)
        }
    ]
    db.deliveries.insert_many(deliveries_data)

    # 10. Announcements
    announcements_data = [
        {
            "announcement_id": "ANN001",
            "title": "Water Tank Cleaning & Preventive Maintenance",
            "description": "Overhead water tanks in Block A and Block B will undergo scheduled chemical cleaning on Sunday from 9:00 AM to 1:00 PM. Water supply will be paused temporarily.",
            "target": "ALL",
            "priority": "HIGH",
            "published_by": "Vikram Malhotra (Admin)",
            "publish_date": (date.today() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "expiry_date": (date.today() + timedelta(days=7)).strftime("%Y-%m-%d"),
            "created_at": now - timedelta(days=1)
        },
        {
            "announcement_id": "ANN002",
            "title": "Annual Society General Body Meeting (AGM)",
            "description": "All owners and residents are cordially invited to attend the Annual General Meeting at the Community Hall this coming Saturday at 6:00 PM.",
            "target": "ALL",
            "priority": "MEDIUM",
            "published_by": "Anita Deshmukh (Manager)",
            "publish_date": date.today().strftime("%Y-%m-%d"),
            "expiry_date": (date.today() + timedelta(days=10)).strftime("%Y-%m-%d"),
            "created_at": now
        }
    ]
    db.announcements.insert_many(announcements_data)

    # 11. Initial Notifications
    notifications_data = [
        {
            "notification_id": "NOTIF001",
            "user_id": "RES001",
            "title": "Maintenance Bill Generated",
            "message": f"Your maintenance bill BILL001 of ₹3,300 is due on {due_date}.",
            "link": "/resident/bills",
            "type": "WARNING",
            "is_read": False,
            "created_at": now - timedelta(days=2)
        },
        {
            "notification_id": "NOTIF002",
            "user_id": "RES001",
            "title": "Parcel Waiting at Security",
            "message": "A courier package from Amazon Prime has arrived at the security gate.",
            "link": "/resident/visitors",
            "type": "INFO",
            "is_read": False,
            "created_at": now - timedelta(minutes=30)
        }
    ]
    db.notifications.insert_many(notifications_data)

    # 12. Community Collections & Special Contributions (Requirement 33)
    community_collections_data = [
        {
            "collection_id": "COL001",
            "title": "Diwali Celebration 2026",
            "type": "Festival",
            "description": "Grand Diwali celebration with music, community fireworks display, sweets distribution, and catered festive dinner for all families.",
            "amount": 500.0,
            "has_tier_pricing": False,
            "pricing_tiers": {},
            "event_date": "2026-10-20",
            "payment_deadline": "2026-10-15",
            "target": {"type": "ALL"},
            "payment_type": "MANDATORY",
            "max_participants": None,
            "allow_overdue_payments": True,
            "recurrence": "ONE_TIME",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_by_name": "Anita Deshmukh (Manager)",
            "created_at": now - timedelta(days=10),
            "updated_at": now - timedelta(days=10)
        },
        {
            "collection_id": "COL002",
            "title": "Pongal Celebration 2027",
            "type": "Festival",
            "description": "Traditional harvest festival celebrations with Pongal cooking, cultural performances, and traditional games at the courtyard.",
            "amount": 300.0,
            "has_tier_pricing": False,
            "pricing_tiers": {},
            "event_date": "2027-01-14",
            "payment_deadline": "2027-01-10",
            "target": {"type": "ALL"},
            "payment_type": "MANDATORY",
            "max_participants": None,
            "allow_overdue_payments": True,
            "recurrence": "ONE_TIME",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_by_name": "Anita Deshmukh (Manager)",
            "created_at": now - timedelta(days=5),
            "updated_at": now - timedelta(days=5)
        },
        {
            "collection_id": "COL003",
            "title": "Ooty Community Tour",
            "type": "Tour",
            "description": "3-Day luxury bus excursion to Ooty including stay at heritage resort, sightseeing, bonfire night, and all meals included.",
            "amount": 4500.0,
            "has_tier_pricing": True,
            "pricing_tiers": {
                "ADULT": 4500.0,
                "CHILD": 2500.0,
                "SENIOR": 3500.0
            },
            "event_date": "2026-11-25",
            "payment_deadline": "2026-11-10",
            "target": {"type": "ALL"},
            "payment_type": "OPTIONAL",
            "max_participants": 100,
            "allow_overdue_payments": False,
            "recurrence": "ONE_TIME",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_by_name": "Anita Deshmukh (Manager)",
            "created_at": now - timedelta(days=8),
            "updated_at": now - timedelta(days=8)
        },
        {
            "collection_id": "COL004",
            "title": "Apartment Sports Day",
            "type": "Sports Event",
            "description": "Annual badminton, cricket, table tennis tournaments and fun athletic games for children and adults with trophies and certificates.",
            "amount": 200.0,
            "has_tier_pricing": False,
            "pricing_tiers": {},
            "event_date": "2026-11-05",
            "payment_deadline": "2026-11-01",
            "target": {"type": "ALL"},
            "payment_type": "OPTIONAL",
            "max_participants": 150,
            "allow_overdue_payments": True,
            "recurrence": "ONE_TIME",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_by_name": "Anita Deshmukh (Manager)",
            "created_at": now - timedelta(days=4),
            "updated_at": now - timedelta(days=4)
        },
        {
            "collection_id": "COL005",
            "title": "Annual Cultural Event",
            "type": "Cultural Event",
            "description": "Talent night featuring music bands, classical dance, drama, and society awards banquet in the grand hall.",
            "amount": 750.0,
            "has_tier_pricing": False,
            "pricing_tiers": {},
            "event_date": "2026-12-18",
            "payment_deadline": "2026-12-10",
            "target": {"type": "BLOCK", "blocks": ["A", "B"]},
            "payment_type": "MANDATORY",
            "max_participants": None,
            "allow_overdue_payments": True,
            "recurrence": "ONE_TIME",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_by_name": "Anita Deshmukh (Manager)",
            "created_at": now - timedelta(days=3),
            "updated_at": now - timedelta(days=3)
        },
        {
            "collection_id": "COL006",
            "title": "Emergency Maintenance Fund",
            "type": "Emergency Contribution",
            "description": "Emergency corpus contribution for high-capacity backup diesel generator replacement and perimeter lightning arrester system.",
            "amount": 1000.0,
            "has_tier_pricing": False,
            "pricing_tiers": {},
            "event_date": "2026-10-30",
            "payment_deadline": "2026-10-25",
            "target": {"type": "ALL"},
            "payment_type": "MANDATORY",
            "max_participants": None,
            "allow_overdue_payments": True,
            "recurrence": "ONE_TIME",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_by_name": "Anita Deshmukh (Manager)",
            "created_at": now - timedelta(days=6),
            "updated_at": now - timedelta(days=6)
        }
    ]
    db.community_collections.insert_many(community_collections_data)

    # 13. Community Collection Payments & Registrations
    community_payments_data = [
        # COL001 - Diwali
        {
            "payment_id": "CPAY001",
            "collection_id": "COL001",
            "collection_title": "Diwali Celebration 2026",
            "collection_type": "Festival",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "flat": "A-204",
            "block": "A",
            "amount": 500.0,
            "total_amount": 500.0,
            "participant_count": 1,
            "participants": [{"name": "Arun Kumar", "member_id": "RES001", "relationship": "Self", "category": "ADULT", "amount": 500.0}],
            "status": "PENDING",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2026-10-15",
            "payment": {"transaction_id": None, "paid_at": None, "method": None, "receipt_no": None},
            "created_at": now - timedelta(days=10),
            "updated_at": now - timedelta(days=10)
        },
        {
            "payment_id": "CPAY002",
            "collection_id": "COL001",
            "collection_title": "Diwali Celebration 2026",
            "collection_type": "Festival",
            "resident_id": "RES002",
            "resident_name": "Priya Sundaram",
            "flat": "B-101",
            "block": "B",
            "amount": 500.0,
            "total_amount": 500.0,
            "participant_count": 1,
            "participants": [{"name": "Priya Sundaram", "member_id": "RES002", "relationship": "Self", "category": "ADULT", "amount": 500.0}],
            "status": "PAID",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2026-10-15",
            "payment": {
                "transaction_id": "TXN-COMM-DIWALI01",
                "paid_at": (now - timedelta(days=2)).isoformat(),
                "method": "UPI",
                "receipt_no": "CPR-2026-0001",
                "settled_amount": 500.0
            },
            "created_at": now - timedelta(days=10),
            "updated_at": now - timedelta(days=2)
        },
        {
            "payment_id": "CPAY003",
            "collection_id": "COL001",
            "collection_title": "Diwali Celebration 2026",
            "collection_type": "Festival",
            "resident_id": "RES003",
            "resident_name": "Karthik Raja",
            "flat": "A-102",
            "block": "A",
            "amount": 500.0,
            "total_amount": 500.0,
            "participant_count": 1,
            "participants": [{"name": "Karthik Raja", "member_id": "RES003", "relationship": "Self", "category": "ADULT", "amount": 500.0}],
            "status": "PAID",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2026-10-15",
            "payment": {
                "transaction_id": "TXN-COMM-DIWALI02",
                "paid_at": (now - timedelta(days=1)).isoformat(),
                "method": "CARD",
                "receipt_no": "CPR-2026-0002",
                "settled_amount": 500.0
            },
            "created_at": now - timedelta(days=10),
            "updated_at": now - timedelta(days=1)
        },

        # COL002 - Pongal
        {
            "payment_id": "CPAY004",
            "collection_id": "COL002",
            "collection_title": "Pongal Celebration 2027",
            "collection_type": "Festival",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "flat": "A-204",
            "block": "A",
            "amount": 300.0,
            "total_amount": 300.0,
            "participant_count": 1,
            "participants": [{"name": "Arun Kumar", "member_id": "RES001", "relationship": "Self", "category": "ADULT", "amount": 300.0}],
            "status": "PENDING",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2027-01-10",
            "payment": {"transaction_id": None, "paid_at": None, "method": None, "receipt_no": None},
            "created_at": now - timedelta(days=5),
            "updated_at": now - timedelta(days=5)
        },
        {
            "payment_id": "CPAY005",
            "collection_id": "COL002",
            "collection_title": "Pongal Celebration 2027",
            "collection_type": "Festival",
            "resident_id": "RES002",
            "resident_name": "Priya Sundaram",
            "flat": "B-101",
            "block": "B",
            "amount": 300.0,
            "total_amount": 300.0,
            "participant_count": 1,
            "participants": [{"name": "Priya Sundaram", "member_id": "RES002", "relationship": "Self", "category": "ADULT", "amount": 300.0}],
            "status": "PENDING",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2027-01-10",
            "payment": {"transaction_id": None, "paid_at": None, "method": None, "receipt_no": None},
            "created_at": now - timedelta(days=5),
            "updated_at": now - timedelta(days=5)
        },

        # COL003 - Ooty Tour (Optional, with embedded family members and tiered pricing)
        {
            "payment_id": "CPAY006",
            "collection_id": "COL003",
            "collection_title": "Ooty Community Tour",
            "collection_type": "Tour",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "flat": "A-204",
            "block": "A",
            "amount": 11500.0,
            "total_amount": 11500.0,
            "participant_count": 3,
            "participants": [
                {"name": "Arun Kumar", "member_id": "RES001", "relationship": "Self", "category": "ADULT", "amount": 4500.0},
                {"name": "Meera Kumar", "member_id": "FAM001", "relationship": "Spouse", "category": "ADULT", "amount": 4500.0},
                {"name": "Rahul Kumar", "member_id": "FAM002", "relationship": "Son", "category": "CHILD", "amount": 2500.0}
            ],
            "status": "PAID",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2026-11-10",
            "payment": {
                "transaction_id": "TXN-COMM-OOTY01",
                "paid_at": (now - timedelta(days=3)).isoformat(),
                "method": "NETBANKING",
                "receipt_no": "CPR-2026-0003",
                "settled_amount": 11500.0
            },
            "created_at": now - timedelta(days=7),
            "updated_at": now - timedelta(days=3)
        },
        {
            "payment_id": "CPAY007",
            "collection_id": "COL003",
            "collection_title": "Ooty Community Tour",
            "collection_type": "Tour",
            "resident_id": "RES002",
            "resident_name": "Priya Sundaram",
            "flat": "B-101",
            "block": "B",
            "amount": 9000.0,
            "total_amount": 9000.0,
            "participant_count": 2,
            "participants": [
                {"name": "Priya Sundaram", "member_id": "RES002", "relationship": "Self", "category": "ADULT", "amount": 4500.0},
                {"name": "Deepak Sundaram", "member_id": "FAM003", "relationship": "Brother", "category": "ADULT", "amount": 4500.0}
            ],
            "status": "PAID",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2026-11-10",
            "payment": {
                "transaction_id": "TXN-COMM-OOTY02",
                "paid_at": (now - timedelta(days=2)).isoformat(),
                "method": "UPI",
                "receipt_no": "CPR-2026-0004",
                "settled_amount": 9000.0
            },
            "created_at": now - timedelta(days=6),
            "updated_at": now - timedelta(days=2)
        },

        # COL004 - Sports Day (Optional)
        {
            "payment_id": "CPAY008",
            "collection_id": "COL004",
            "collection_title": "Apartment Sports Day",
            "collection_type": "Sports Event",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "flat": "A-204",
            "block": "A",
            "amount": 400.0,
            "total_amount": 400.0,
            "participant_count": 2,
            "participants": [
                {"name": "Arun Kumar", "member_id": "RES001", "relationship": "Self", "category": "ADULT", "amount": 200.0},
                {"name": "Rahul Kumar", "member_id": "FAM002", "relationship": "Son", "category": "CHILD", "amount": 200.0}
            ],
            "status": "PENDING",
            "registration_status": "REGISTERED",
            "payment_deadline": "2026-11-01",
            "payment": {"transaction_id": None, "paid_at": None, "method": None, "receipt_no": None},
            "created_at": now - timedelta(days=2),
            "updated_at": now - timedelta(days=2)
        },

        # COL005 - Cultural Event (Mandatory Block A & B)
        {
            "payment_id": "CPAY009",
            "collection_id": "COL005",
            "collection_title": "Annual Cultural Event",
            "collection_type": "Cultural Event",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "flat": "A-204",
            "block": "A",
            "amount": 750.0,
            "total_amount": 750.0,
            "participant_count": 1,
            "participants": [{"name": "Arun Kumar", "member_id": "RES001", "relationship": "Self", "category": "ADULT", "amount": 750.0}],
            "status": "PENDING",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2026-12-10",
            "payment": {"transaction_id": None, "paid_at": None, "method": None, "receipt_no": None},
            "created_at": now - timedelta(days=3),
            "updated_at": now - timedelta(days=3)
        },
        {
            "payment_id": "CPAY010",
            "collection_id": "COL005",
            "collection_title": "Annual Cultural Event",
            "collection_type": "Cultural Event",
            "resident_id": "RES002",
            "resident_name": "Priya Sundaram",
            "flat": "B-101",
            "block": "B",
            "amount": 750.0,
            "total_amount": 750.0,
            "participant_count": 1,
            "participants": [{"name": "Priya Sundaram", "member_id": "RES002", "relationship": "Self", "category": "ADULT", "amount": 750.0}],
            "status": "PENDING",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2026-12-10",
            "payment": {"transaction_id": None, "paid_at": None, "method": None, "receipt_no": None},
            "created_at": now - timedelta(days=3),
            "updated_at": now - timedelta(days=3)
        },

        # COL006 - Emergency Fund
        {
            "payment_id": "CPAY011",
            "collection_id": "COL006",
            "collection_title": "Emergency Maintenance Fund",
            "collection_type": "Emergency Contribution",
            "resident_id": "RES001",
            "resident_name": "Arun Kumar",
            "flat": "A-204",
            "block": "A",
            "amount": 1000.0,
            "total_amount": 1000.0,
            "participant_count": 1,
            "participants": [{"name": "Arun Kumar", "member_id": "RES001", "relationship": "Self", "category": "ADULT", "amount": 1000.0}],
            "status": "PENDING",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2026-10-25",
            "payment": {"transaction_id": None, "paid_at": None, "method": None, "receipt_no": None},
            "created_at": now - timedelta(days=6),
            "updated_at": now - timedelta(days=6)
        },
        {
            "payment_id": "CPAY012",
            "collection_id": "COL006",
            "collection_title": "Emergency Maintenance Fund",
            "collection_type": "Emergency Contribution",
            "resident_id": "RES002",
            "resident_name": "Priya Sundaram",
            "flat": "B-101",
            "block": "B",
            "amount": 1000.0,
            "total_amount": 1000.0,
            "participant_count": 1,
            "participants": [{"name": "Priya Sundaram", "member_id": "RES002", "relationship": "Self", "category": "ADULT", "amount": 1000.0}],
            "status": "PAID",
            "registration_status": "CONFIRMED",
            "payment_deadline": "2026-10-25",
            "payment": {
                "transaction_id": "TXN-COMM-EMERG01",
                "paid_at": (now - timedelta(days=1)).isoformat(),
                "method": "UPI",
                "receipt_no": "CPR-2026-0005",
                "settled_amount": 1000.0
            },
            "created_at": now - timedelta(days=6),
            "updated_at": now - timedelta(days=1)
        }
    ]
    db.community_collection_payments.insert_many(community_payments_data)

    # 15. External Apartment Service Vendors (covering all 21 categories)
    vendors_data = [
        {
            "vendor_id": "VEN001",
            "company": {"name": "ApexLift Services", "contact_person": "Ramesh Kumar", "phone": "9000000001", "email": "info@apexlift-demo.com", "address": "104 Avinashi Road", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "LIFT_MAINTENANCE", "description": "High-rise elevator preventative AMC, sensor checks, and 24/7 rescue"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-10-31", "payment_frequency": "MONTHLY", "amount": 15000.0},
            "gst_number": "33AABCA1234F1Z1",
            "emergency_contact": "9000000000",
            "service_availability": "24/7 Emergency Support",
            "documents": [],
            "rating": {"average_rating": 4.8, "total_reviews": 6},
            "performance": {"services_completed": 6, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=200)).isoformat()
        },
        {
            "vendor_id": "VEN002",
            "company": {"name": "MetroLift Care", "contact_person": "Suresh Raina", "phone": "9000000002", "email": "contact@metrolift-demo.com", "address": "45 Trichy Road", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "LIFT_MAINTENANCE", "description": "Backup elevator maintenance and modernization services"},
            "contract": None,
            "gst_number": "33AABCM5678F1Z2",
            "emergency_contact": "9000000002",
            "service_availability": "General Working Hours",
            "documents": [],
            "rating": {"average_rating": 4.5, "total_reviews": 2},
            "performance": {"services_completed": 2, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=180)).isoformat()
        },
        {
            "vendor_id": "VEN003",
            "company": {"name": "PowerGrid Electricals", "contact_person": "Venkatesh S", "phone": "9000000003", "email": "sales@powergrid-demo.com", "address": "78 DB Road", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "ELECTRICAL", "description": "HT substation maintenance, transformer diagnostics, and common line wiring"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "QUARTERLY", "amount": 25000.0},
            "gst_number": "33AABCP9911F1Z3",
            "emergency_contact": "9000000003",
            "service_availability": "24/7 Breakdown Assistance",
            "documents": [],
            "rating": {"average_rating": 4.7, "total_reviews": 4},
            "performance": {"services_completed": 4, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=190)).isoformat()
        },
        {
            "vendor_id": "VEN004",
            "company": {"name": "AquaFix Plumbing Solutions", "contact_person": "Manoj Kumar", "phone": "9000000004", "email": "service@aquafix-demo.com", "address": "12 Cross Cut Road", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "PLUMBING", "description": "Hydro-pneumatic booster pump maintenance and master drainage piping"},
            "contract": {"start_date": "2026-03-01", "end_date": "2027-02-28", "payment_frequency": "MONTHLY", "amount": 10000.0},
            "gst_number": "33AABCA4422F1Z4",
            "emergency_contact": "9000000004",
            "service_availability": "8 AM - 8 PM Daily",
            "documents": [],
            "rating": {"average_rating": 4.6, "total_reviews": 5},
            "performance": {"services_completed": 5, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=150)).isoformat()
        },
        {
            "vendor_id": "VEN005",
            "company": {"name": "CleanNest Facility Services", "contact_person": "Deepak Verma", "phone": "9000000005", "email": "ops@cleannest-demo.com", "address": "88 Mettupalayam Road", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "CLEANING", "description": "Society common area scrubbing, glass facade wash, and clubhouse sanitization"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "MONTHLY", "amount": 35000.0},
            "gst_number": "33AABCC1122F1Z5",
            "emergency_contact": "9000000005",
            "service_availability": "Daily 6 AM - 6 PM",
            "documents": [],
            "rating": {"average_rating": 4.9, "total_reviews": 8},
            "performance": {"services_completed": 8, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=220)).isoformat()
        },
        {
            "vendor_id": "VEN006",
            "company": {"name": "SecureGate Patrol Services", "contact_person": "Major R. Balan", "phone": "9000000006", "email": "guard@securegate-demo.com", "address": "200 Race Course", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "SECURITY", "description": "Trained 24/7 security guard deployments, boom barrier control, and perimeter watch"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "MONTHLY", "amount": 45000.0},
            "gst_number": "33AABCS9988F1Z6",
            "emergency_contact": "9000000006",
            "service_availability": "24/7 Gate Patrol",
            "documents": [],
            "rating": {"average_rating": 4.8, "total_reviews": 10},
            "performance": {"services_completed": 10, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=250)).isoformat()
        },
        {
            "vendor_id": "VEN007",
            "company": {"name": "GreenLeaf Gardens & Landscaping", "contact_person": "Karthik Raj", "phone": "9000000007", "email": "green@greenleaf-demo.com", "address": "55 Pollachi Road", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "GARDENING", "description": "Central park pruning, sprinkler maintenance, lawn mowing, and flowering plants"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "MONTHLY", "amount": 12000.0},
            "gst_number": "33AABCG5544F1Z7",
            "emergency_contact": "9000000007",
            "service_availability": "Mon-Sat 7 AM - 4 PM",
            "documents": [],
            "rating": {"average_rating": 4.6, "total_reviews": 4},
            "performance": {"services_completed": 4, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=190)).isoformat()
        },
        {
            "vendor_id": "VEN008",
            "company": {"name": "PestShield Solutions", "contact_person": "Albert S", "phone": "9000000008", "email": "safe@pestshield-demo.com", "address": "33 Saravanampatti", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "PEST_CONTROL", "description": "Quarterly termite control, basement fogging, and rodent management"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "QUARTERLY", "amount": 14000.0},
            "gst_number": "33AABCP1199F1Z8",
            "emergency_contact": "9000000008",
            "service_availability": "On Schedule & Call-out",
            "documents": [],
            "rating": {"average_rating": 4.5, "total_reviews": 3},
            "performance": {"services_completed": 3, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=160)).isoformat()
        },
        {
            "vendor_id": "VEN009",
            "company": {"name": "AquaTank Hygiene Care", "contact_person": "Prakash N", "phone": "9000000009", "email": "tank@aquatank-demo.com", "address": "15 Gandhipuram", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "WATER_TANK_CLEANING", "description": "Overhead sump and underground tank mechanized anti-bacterial cleaning"},
            "contract": {"start_date": "2026-02-01", "end_date": "2027-01-31", "payment_frequency": "QUARTERLY", "amount": 16000.0},
            "gst_number": "33AABCT7766F1Z9",
            "emergency_contact": "9000000009",
            "service_availability": "Weekend Slotted Service",
            "documents": [],
            "rating": {"average_rating": 4.7, "total_reviews": 3},
            "performance": {"services_completed": 3, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=140)).isoformat()
        },
        {
            "vendor_id": "VEN010",
            "company": {"name": "BlueWave Pool Care", "contact_person": "Victor Raj", "phone": "9000000010", "email": "pool@bluewave-demo.com", "address": "77 Peelamedu", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "SWIMMING_POOL_MAINTENANCE", "description": "Daily pool vacuuming, pH balance chlorine dosing, and filter plant backwash"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "MONTHLY", "amount": 8000.0},
            "gst_number": "33AABCB3344F1Z0",
            "emergency_contact": "9000000010",
            "service_availability": "Daily 5 AM - 9 AM",
            "documents": [],
            "rating": {"average_rating": 4.9, "total_reviews": 7},
            "performance": {"services_completed": 7, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=210)).isoformat()
        },
        {
            "vendor_id": "VEN011",
            "company": {"name": "FitTech Equipment Care", "contact_person": "Jagan Mohan", "phone": "9000000011", "email": "gym@fittech-demo.com", "address": "90 RS Puram", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "GYM_EQUIPMENT", "description": "Clubhouse treadmill belt lubrication, cable crossover tuning, and multi-gym AMC"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "QUARTERLY", "amount": 12000.0},
            "gst_number": "33AABCF8877F1Z1",
            "emergency_contact": "9000000011",
            "service_availability": "Bi-weekly Scheduled Maintenance",
            "documents": [],
            "rating": {"average_rating": 4.6, "total_reviews": 4},
            "performance": {"services_completed": 4, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=175)).isoformat()
        },
        {
            "vendor_id": "VEN012",
            "company": {"name": "PowerBackup Generator Solutions", "contact_person": "Harish Shankar", "phone": "9000000012", "email": "dg@powerbackup-demo.com", "address": "14 Industrial Estate", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "GENERATOR_MAINTENANCE", "description": "500kVA Diesel Generator B-check, governor calibration, and battery charging AMC"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "MONTHLY", "amount": 18000.0},
            "gst_number": "33AABCP6655F1Z2",
            "emergency_contact": "9000000012",
            "service_availability": "24/7 Breakdown Hotline",
            "documents": [],
            "rating": {"average_rating": 4.8, "total_reviews": 6},
            "performance": {"services_completed": 6, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=230)).isoformat()
        },
        {
            "vendor_id": "VEN013",
            "company": {"name": "VisionSecure CCTV Systems", "contact_person": "Naveen Babu", "phone": "9000000013", "email": "cctv@visionsecure-demo.com", "address": "62 100 Feet Road", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "CCTV_MAINTENANCE", "description": "IP camera alignment, NVR storage health check, optical fiber transmission"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "QUARTERLY", "amount": 15000.0},
            "gst_number": "33AABCV2211F1Z3",
            "emergency_contact": "9000000013",
            "service_availability": "Mon-Sat 9 AM - 7 PM",
            "documents": [],
            "rating": {"average_rating": 4.7, "total_reviews": 3},
            "performance": {"services_completed": 3, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=160)).isoformat()
        },
        {
            "vendor_id": "VEN014",
            "company": {"name": "FireSafe Protection Solutions", "contact_person": "Raghavan K", "phone": "9000000014", "email": "fire@firesafe-demo.com", "address": "110 Sitra Road", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "FIRE_SAFETY", "description": "Fire hydrant diesel pump pressure testing, smoke detectors, and annual NOC audit"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "ANNUAL", "amount": 35000.0},
            "gst_number": "33AABCF9900F1Z4",
            "emergency_contact": "9000000014",
            "service_availability": "Emergency Hotline",
            "documents": [],
            "rating": {"average_rating": 4.9, "total_reviews": 2},
            "performance": {"services_completed": 2, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=260)).isoformat()
        },
        {
            "vendor_id": "VEN015",
            "company": {"name": "EcoClean Waste Services", "contact_person": "Selvam T", "phone": "9000000015", "email": "eco@ecoclean-demo.com", "address": "5 Vadavalli Road", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "WASTE_MANAGEMENT", "description": "Organic waste composting plant operation and recyclable scrap pickup"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "MONTHLY", "amount": 14000.0},
            "gst_number": "33AABCE4433F1Z5",
            "emergency_contact": "9000000015",
            "service_availability": "Daily Morning 6 AM - 11 AM",
            "documents": [],
            "rating": {"average_rating": 4.6, "total_reviews": 5},
            "performance": {"services_completed": 5, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=190)).isoformat()
        },
        {
            "vendor_id": "VEN016",
            "company": {"name": "NetConnect Fiber Broadband", "contact_person": "Arvind Swamy", "phone": "9000000016", "email": "fiber@netconnect-demo.com", "address": "84 Thudiyalur", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "INTERNET_CABLE", "description": "Society intercom cabling, clubhouse WiFi, and common surveillance broadband"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "MONTHLY", "amount": 6500.0},
            "gst_number": "33AABCN7788F1Z6",
            "emergency_contact": "9000000016",
            "service_availability": "Mon-Sat 8 AM - 8 PM",
            "documents": [],
            "rating": {"average_rating": 4.4, "total_reviews": 3},
            "performance": {"services_completed": 3, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=180)).isoformat()
        },
        {
            "vendor_id": "VEN017",
            "company": {"name": "CoolAir HVAC Maintenance", "contact_person": "Dinesh Kumar", "phone": "9000000017", "email": "service@coolair-demo.com", "address": "22 Sungam", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "HVAC_AC_MAINTENANCE", "description": "Clubhouse central VRV HVAC maintenance, duct cleaning, and coolant top-up"},
            "contract": {"start_date": "2026-03-01", "end_date": "2027-02-28", "payment_frequency": "QUARTERLY", "amount": 20000.0},
            "gst_number": "33AABCC5566F1Z7",
            "emergency_contact": "9000000017",
            "service_availability": "Standard Business Hours",
            "documents": [],
            "rating": {"average_rating": 4.7, "total_reviews": 2},
            "performance": {"services_completed": 2, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=120)).isoformat()
        },
        {
            "vendor_id": "VEN018",
            "company": {"name": "SunPower Solar Care", "contact_person": "Balaji Rao", "phone": "9000000018", "email": "support@sunpower-demo.com", "address": "99 Kalapatti", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "SOLAR_PANEL_MAINTENANCE", "description": "Rooftop 50kW solar panel cleaning, inverter diagnostics, and net-metering checks"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "QUARTERLY", "amount": 10000.0},
            "gst_number": "33AABCS1100F1Z8",
            "emergency_contact": "9000000018",
            "service_availability": "Monthly Scheduled Check",
            "documents": [],
            "rating": {"average_rating": 4.8, "total_reviews": 4},
            "performance": {"services_completed": 4, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=200)).isoformat()
        },
        {
            "vendor_id": "VEN019",
            "company": {"name": "PureFlow RO Purifier Services", "contact_person": "Gopal Krishnan", "phone": "9000000019", "email": "ro@pureflow-demo.com", "address": "34 Kovaipudur", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "RO_WATER_PURIFIER", "description": "Commercial RO drinking water plant membrane replacement and TDS calibration"},
            "contract": {"start_date": "2026-01-01", "end_date": "2026-12-31", "payment_frequency": "QUARTERLY", "amount": 15000.0},
            "gst_number": "33AABCP3322F1Z9",
            "emergency_contact": "9000000019",
            "service_availability": "Mon-Sat 9 AM - 6 PM",
            "documents": [],
            "rating": {"average_rating": 4.7, "total_reviews": 3},
            "performance": {"services_completed": 3, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=170)).isoformat()
        },
        {
            "vendor_id": "VEN020",
            "company": {"name": "ColorCraft Painting Solutions", "contact_person": "Muthu Kumaran", "phone": "9000000020", "email": "paint@colorcraft-demo.com", "address": "12 Ramanathapuram", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "PAINTING", "description": "Exterior weatherproof coating, basement line striping, and touch-ups"},
            "contract": None,
            "gst_number": "33AABCC8899F1Z0",
            "emergency_contact": "9000000020",
            "service_availability": "On Project Basis",
            "documents": [],
            "rating": {"average_rating": 4.5, "total_reviews": 1},
            "performance": {"services_completed": 1, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=100)).isoformat()
        },
        {
            "vendor_id": "VEN021",
            "company": {"name": "WoodCare & CraftFix Carpentry", "contact_person": "Saravanan T", "phone": "9000000021", "email": "wood@woodcare-demo.com", "address": "40 Singanallur", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "CARPENTRY", "description": "Clubhouse wooden flooring, main gate woodwork, and security cabin repairs"},
            "contract": None,
            "gst_number": "33AABCW4455F1Z1",
            "emergency_contact": "9000000021",
            "service_availability": "On Demand",
            "documents": [],
            "rating": {"average_rating": 4.6, "total_reviews": 2},
            "performance": {"services_completed": 2, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=90)).isoformat()
        },
        {
            "vendor_id": "VEN022",
            "company": {"name": "CityFacility Multi-Care Services", "contact_person": "Ashwin Raj", "phone": "9000000022", "email": "multi@cityfacility-demo.com", "address": "101 Anna Nagar", "city": "Coimbatore", "state": "Tamil Nadu"},
            "service": {"category": "OTHER", "description": "Specialized high-pressure washing, event canopy setup, and society logistics"},
            "contract": None,
            "gst_number": "33AABCC7744F1Z2",
            "emergency_contact": "9000000022",
            "service_availability": "On Demand 24/7",
            "documents": [],
            "rating": {"average_rating": 4.4, "total_reviews": 1},
            "performance": {"services_completed": 1, "delayed_services": 0, "sla_breaches": 0},
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=60)).isoformat()
        }
    ]
    for v in vendors_data:
        db.vendors.update_one({"vendor_id": v["vendor_id"]}, {"$setOnInsert": v}, upsert=True)

    # 16. Vendor Contracts
    contracts_data = [
        {
            "contract_id": "CON001",
            "vendor_id": "VEN001",
            "service_category": "LIFT_MAINTENANCE",
            "start_date": "2026-01-01",
            "end_date": "2026-10-31",
            "amount": 15000.0,
            "payment_frequency": "MONTHLY",
            "terms": "Comprehensive maintenance covering 4 passenger elevators in Block A, B, C, D including routine monthly checkups and emergency rescue.",
            "renewal_date": "2026-10-15",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=200)).isoformat()
        },
        {
            "contract_id": "CON002",
            "vendor_id": "VEN012",
            "service_category": "GENERATOR_MAINTENANCE",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "amount": 18000.0,
            "payment_frequency": "MONTHLY",
            "terms": "500kVA DG maintenance, monthly test runs, battery water top-up, and 24/7 power backup support.",
            "renewal_date": "2026-12-15",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=200)).isoformat()
        },
        {
            "contract_id": "CON003",
            "vendor_id": "VEN010",
            "service_category": "SWIMMING_POOL_MAINTENANCE",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "amount": 8000.0,
            "payment_frequency": "MONTHLY",
            "terms": "Daily pool vacuuming, water purification chemicals, filtration plant maintenance.",
            "renewal_date": "2026-12-10",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=200)).isoformat()
        },
        {
            "contract_id": "CON004",
            "vendor_id": "VEN014",
            "service_category": "FIRE_SAFETY",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "amount": 35000.0,
            "payment_frequency": "ANNUAL",
            "terms": "Annual inspection, pressure testing of 40 fire extinguishers, hydrant pump servicing, and government safety certification.",
            "renewal_date": "2026-12-01",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=200)).isoformat()
        },
        {
            "contract_id": "CON005",
            "vendor_id": "VEN006",
            "service_category": "SECURITY",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "amount": 45000.0,
            "payment_frequency": "MONTHLY",
            "terms": "Round-the-clock security guard staffing across Main Gate, Tower Entrances, and Night Patrol.",
            "renewal_date": "2026-12-05",
            "status": "ACTIVE",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=200)).isoformat()
        }
    ]
    for c in contracts_data:
        db.vendor_contracts.update_one({"contract_id": c["contract_id"]}, {"$setOnInsert": c}, upsert=True)

    # 17. Vendor Service Requests
    service_requests_data = [
        {
            "request_id": "VSR001",
            "vendor_id": "VEN001",
            "asset_id": "LIFT-BLK-A",
            "complaint_id": None,
            "service_category": "LIFT_MAINTENANCE",
            "description": "Monthly routine inspection and door leveling sensor recalibration in Block A elevator",
            "priority": "MEDIUM",
            "scheduled_date": (now - timedelta(days=5)).strftime("%Y-%m-%d"),
            "status": "COMPLETED",
            "service_report": "Completed 12-point elevator safety check. Recalibrated optic sensor on 4th floor. Smooth operation confirmed.",
            "rating": {"overall_rating": 5, "service_quality": 5, "response_time": 5, "remarks": "Very punctual and thorough service."},
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=7)).isoformat(),
            "completed_at": (now - timedelta(days=5)).isoformat()
        },
        {
            "request_id": "VSR002",
            "vendor_id": "VEN004",
            "asset_id": "PUMP-MAIN-01",
            "complaint_id": None,
            "service_category": "PLUMBING",
            "description": "Master booster pump pressure switch adjustment and check valve replacement",
            "priority": "HIGH",
            "scheduled_date": now.strftime("%Y-%m-%d"),
            "status": "IN_PROGRESS",
            "service_report": None,
            "rating": None,
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=1)).isoformat(),
            "completed_at": None
        },
        {
            "request_id": "VSR003",
            "vendor_id": "VEN014",
            "asset_id": "FIRE-HYDRANT-SYS",
            "complaint_id": None,
            "service_category": "FIRE_SAFETY",
            "description": "Quarterly dry run testing of main diesel engine fire hydrant backup pump",
            "priority": "HIGH",
            "scheduled_date": (now - timedelta(days=15)).strftime("%Y-%m-%d"),
            "status": "COMPLETED",
            "service_report": "Diesel engine started within 6 seconds. Hydrant line pressure sustained at 7.5 bar. All valves operational.",
            "rating": {"overall_rating": 4, "service_quality": 4, "response_time": 4, "remarks": "Standard quarterly check passed."},
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=18)).isoformat(),
            "completed_at": (now - timedelta(days=15)).isoformat()
        },
        {
            "request_id": "VSR004",
            "vendor_id": "VEN005",
            "asset_id": "COMMON-BASEMENT",
            "complaint_id": None,
            "service_category": "CLEANING",
            "description": "Post-monsoon basement drainage channel deep scrub and deodorizing",
            "priority": "LOW",
            "scheduled_date": (now + timedelta(days=3)).strftime("%Y-%m-%d"),
            "status": "PENDING",
            "service_report": None,
            "rating": None,
            "created_by": "MGR001",
            "created_at": now.isoformat(),
            "completed_at": None
        }
    ]
    for sr in service_requests_data:
        db.vendor_service_requests.update_one({"request_id": sr["request_id"]}, {"$setOnInsert": sr}, upsert=True)

    # 18. Vendor Payments
    vendor_payments_data = [
        {
            "payment_id": "VPAY001",
            "vendor_id": "VEN001",
            "contract_id": "CON001",
            "invoice_number": "INV-AL-2026-09",
            "service_description": "Lift AMC Monthly Maintenance - September 2026",
            "amount": 15000.0,
            "due_date": "2026-10-05",
            "payment_date": "2026-10-02",
            "payment_method": "BANK_TRANSFER",
            "transaction_id": "NEFT-HDFC-994411",
            "status": "PAID",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=5)).isoformat()
        },
        {
            "payment_id": "VPAY002",
            "vendor_id": "VEN012",
            "contract_id": "CON002",
            "invoice_number": "INV-PB-2026-09",
            "service_description": "Diesel Generator AMC Maintenance - September 2026",
            "amount": 18000.0,
            "due_date": "2026-10-05",
            "payment_date": "2026-10-03",
            "payment_method": "BANK_TRANSFER",
            "transaction_id": "NEFT-ICICI-332211",
            "status": "PAID",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=4)).isoformat()
        },
        {
            "payment_id": "VPAY003",
            "vendor_id": "VEN010",
            "contract_id": "CON003",
            "invoice_number": "INV-BW-2026-10",
            "service_description": "Swimming Pool Chemical & Cleaning AMC - October 2026",
            "amount": 8000.0,
            "due_date": "2026-10-15",
            "payment_date": None,
            "payment_method": None,
            "transaction_id": None,
            "status": "PENDING",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=1)).isoformat()
        },
        {
            "payment_id": "VPAY004",
            "vendor_id": "VEN006",
            "contract_id": "CON005",
            "invoice_number": "INV-SG-2026-09",
            "service_description": "Security Guard Deployment - September 2026",
            "amount": 45000.0,
            "due_date": "2026-10-05",
            "payment_date": "2026-10-01",
            "payment_method": "CHEQUE",
            "transaction_id": "CHQ-004455",
            "status": "PAID",
            "created_by": "MGR001",
            "created_at": (now - timedelta(days=6)).isoformat()
        }
    ]
    for vp in vendor_payments_data:
        db.vendor_payments.update_one({"payment_id": vp["payment_id"]}, {"$setOnInsert": vp}, upsert=True)

    # 19. Daily Help Management (Resident Household Staff)
    daily_help_data = [
        {
            "help_id": "HELP001",
            "resident_id": "RES001",
            "flat_id": "A-204",
            "person": {"name": "Priya R", "phone": "9000000101", "service_type": "MAID", "gender": "FEMALE", "address": "Gandhi Nagar, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT"], "entry_time": "08:00", "exit_time": "11:00"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Maintains kitchen cleaning, utensils, and floor mopping.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=90)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=90)).isoformat()
        },
        {
            "help_id": "HELP002",
            "resident_id": "RES001",
            "flat_id": "A-204",
            "person": {"name": "Ramesh M", "phone": "9000000102", "service_type": "COOK", "gender": "MALE", "address": "Ramanathapuram, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "entry_time": "07:30", "exit_time": "10:30"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Morning breakfast & lunch preparation.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=85)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=85)).isoformat()
        },
        {
            "help_id": "HELP003",
            "resident_id": "RES001",
            "flat_id": "A-204",
            "person": {"name": "Murugan K", "phone": "9000000103", "service_type": "DRIVER", "gender": "MALE", "address": "Singanallur, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI"], "entry_time": "08:30", "exit_time": "18:00"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Office commute driver for Honda City.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=80)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=80)).isoformat()
        },
        {
            "help_id": "HELP004",
            "resident_id": "RES001",
            "flat_id": "A-204",
            "person": {"name": "Lakshmi S", "phone": "9000000104", "service_type": "CLEANER", "gender": "FEMALE", "address": "Peelamedu, Coimbatore"},
            "schedule": {"days": ["TUE", "FRI"], "entry_time": "14:00", "exit_time": "16:00"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Balcony washing and deep bathroom sanitization.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=70)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=70)).isoformat()
        },
        {
            "help_id": "HELP005",
            "resident_id": "RES002",
            "flat_id": "B-101",
            "person": {"name": "Anitha V", "phone": "9000000105", "service_type": "BABYSITTER", "gender": "FEMALE", "address": "Saibaba Colony, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI"], "entry_time": "09:00", "exit_time": "17:00"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Childcare and toddler supervision.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=60)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=60)).isoformat()
        },
        {
            "help_id": "HELP006",
            "resident_id": "RES002",
            "flat_id": "B-101",
            "person": {"name": "Senthil P", "phone": "9000000106", "service_type": "DRIVER", "gender": "MALE", "address": "RS Puram, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT"], "entry_time": "08:00", "exit_time": "17:30"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Personal driver.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=55)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=55)).isoformat()
        },
        {
            "help_id": "HELP007",
            "resident_id": "RES002",
            "flat_id": "B-101",
            "person": {"name": "Selvi M", "phone": "9000000107", "service_type": "MAID", "gender": "FEMALE", "address": "Gandhipuram, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT"], "entry_time": "08:30", "exit_time": "11:30"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Daily housekeeping and dusting.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=50)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=50)).isoformat()
        },
        {
            "help_id": "HELP008",
            "resident_id": "RES002",
            "flat_id": "B-101",
            "person": {"name": "Sundar B", "phone": "9000000108", "service_type": "CARETAKER", "gender": "MALE", "address": "Vadavalli, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "entry_time": "10:00", "exit_time": "18:00"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Elderly patient care assistant.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=45)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=45)).isoformat()
        },
        {
            "help_id": "HELP009",
            "resident_id": "RES001",
            "flat_id": "A-204",
            "person": {"name": "Ganesan T", "phone": "9000000109", "service_type": "NEWSPAPER", "gender": "MALE", "address": "Town Hall, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "entry_time": "06:00", "exit_time": "06:30"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Morning English & Tamil newspapers.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=100)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=100)).isoformat()
        },
        {
            "help_id": "HELP010",
            "resident_id": "RES001",
            "flat_id": "A-204",
            "person": {"name": "Palani D", "phone": "9000000110", "service_type": "MILK_DELIVERY", "gender": "MALE", "address": "Perur, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"], "entry_time": "06:15", "exit_time": "06:45"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Aavin fresh milk packet delivery.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=100)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=100)).isoformat()
        },
        {
            "help_id": "HELP011",
            "resident_id": "RES003",
            "flat_id": "A-102",
            "person": {"name": "Kavitha N", "phone": "9000000111", "service_type": "MAID", "gender": "FEMALE", "address": "Singanallur, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT"], "entry_time": "08:00", "exit_time": "10:30"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Kitchen utensils & dusting.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=40)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=40)).isoformat()
        },
        {
            "help_id": "HELP012",
            "resident_id": "RES003",
            "flat_id": "A-102",
            "person": {"name": "Rajeshwari K", "phone": "9000000112", "service_type": "COOK", "gender": "FEMALE", "address": "Ondipudur, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT"], "entry_time": "17:00", "exit_time": "19:30"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Evening dinner preparation.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=35)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=35)).isoformat()
        },
        {
            "help_id": "HELP013",
            "resident_id": "RES003",
            "flat_id": "A-102",
            "person": {"name": "Manickam R", "phone": "9000000113", "service_type": "DRIVER", "gender": "MALE", "address": "Sulur, Coimbatore"},
            "schedule": {"days": ["MON", "TUE", "WED", "THU", "FRI", "SAT"], "entry_time": "08:30", "exit_time": "17:30"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Part-time driver.",
            "verification_status": "PENDING",
            "rejection_reason": None,
            "verified_by": None,
            "verified_at": None,
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=1)).isoformat()
        },
        {
            "help_id": "HELP014",
            "resident_id": "RES003",
            "flat_id": "A-102",
            "person": {"name": "Geetha S", "phone": "9000000114", "service_type": "BABYSITTER", "gender": "FEMALE", "address": "Kuniyamuthur, Coimbatore"},
            "schedule": {"days": ["MON", "WED", "FRI"], "entry_time": "14:00", "exit_time": "18:00"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Weekend babysitting.",
            "verification_status": "REJECTED",
            "rejection_reason": "Uploaded Aadhaar card ID proof was blurred and unreadable. Please re-upload.",
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=2)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=3)).isoformat()
        },
        {
            "help_id": "HELP015",
            "resident_id": "RES002",
            "flat_id": "B-101",
            "person": {"name": "Velu P", "phone": "9000000115", "service_type": "CLEANER", "gender": "MALE", "address": "Ukkadam, Coimbatore"},
            "schedule": {"days": ["SAT"], "entry_time": "10:00", "exit_time": "13:00"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Car washing assistant.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=30)).isoformat(),
            "status": "SUSPENDED",
            "created_at": (now - timedelta(days=30)).isoformat()
        },
        {
            "help_id": "HELP016",
            "resident_id": "RES001",
            "flat_id": "A-204",
            "person": {"name": "Saravanan M", "phone": "9000000116", "service_type": "OTHER", "gender": "MALE", "address": "Ganapathy, Coimbatore"},
            "schedule": {"days": ["MON", "THU"], "entry_time": "11:00", "exit_time": "12:00"},
            "documents": {"photo_file_id": None, "id_proof_file_id": None},
            "notes": "Indoor potted plant caretaker.",
            "verification_status": "APPROVED",
            "rejection_reason": None,
            "verified_by": "MGR001",
            "verified_at": (now - timedelta(days=25)).isoformat(),
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=25)).isoformat()
        }
    ]
    for dh in daily_help_data:
        db.daily_help.update_one({"help_id": dh["help_id"]}, {"$setOnInsert": dh}, upsert=True)

    # 20. Daily Help Attendance Records (Today's check-ins and check-outs)
    today_str = date.today().strftime("%Y-%m-%d")
    daily_attendance_data = [
        {
            "attendance_id": "ATT001",
            "help_id": "HELP001",
            "help_name": "Priya R",
            "service_type": "MAID",
            "resident_id": "RES001",
            "flat_id": "A-204",
            "date": today_str,
            "check_in": "08:05",
            "check_out": None,
            "status": "CHECKED_IN",
            "created_at": datetime.now().isoformat()
        },
        {
            "attendance_id": "ATT002",
            "help_id": "HELP002",
            "help_name": "Ramesh M",
            "service_type": "COOK",
            "resident_id": "RES001",
            "flat_id": "A-204",
            "date": today_str,
            "check_in": "07:45",
            "check_out": "10:15",
            "status": "COMPLETED",
            "created_at": datetime.now().isoformat()
        },
        {
            "attendance_id": "ATT003",
            "help_id": "HELP005",
            "help_name": "Anitha V",
            "service_type": "BABYSITTER",
            "resident_id": "RES002",
            "flat_id": "B-101",
            "date": today_str,
            "check_in": "09:00",
            "check_out": None,
            "status": "CHECKED_IN",
            "created_at": datetime.now().isoformat()
        },
        {
            "attendance_id": "ATT004",
            "help_id": "HELP007",
            "help_name": "Selvi M",
            "service_type": "MAID",
            "resident_id": "RES002",
            "flat_id": "B-101",
            "date": today_str,
            "check_in": "08:30",
            "check_out": "11:30",
            "status": "COMPLETED",
            "created_at": datetime.now().isoformat()
        }
    ]
    for att in daily_attendance_data:
        db.daily_help_attendance.update_one({"attendance_id": att["attendance_id"]}, {"$setOnInsert": att}, upsert=True)

    # 14. Counters for sequential IDs
    counters_data = [
        {"_id": "user_adm", "seq": 1},
        {"_id": "user_mgr", "seq": 1},
        {"_id": "user_res", "seq": 3},
        {"_id": "user_tech", "seq": 3},
        {"_id": "user_sec", "seq": 1},
        {"_id": "complaint", "seq": 2},
        {"_id": "booking", "seq": 1},
        {"_id": "bill", "seq": 2},
        {"_id": "payment", "seq": 5},
        {"_id": "visitor", "seq": 2},
        {"_id": "delivery", "seq": 1},
        {"_id": "announcement", "seq": 2},
        {"_id": "notification", "seq": 6},
        {"_id": "emergency_alert", "seq": 0},
        {"_id": "audit_log", "seq": 10},
        {"_id": "community_collection", "seq": 6},
        {"_id": "community_payment", "seq": 12},
        {"_id": "receipt_cpr", "seq": 5},
        {"_id": "vendor", "seq": 22},
        {"_id": "vendor_contract", "seq": 5},
        {"_id": "vendor_service_request", "seq": 4},
        {"_id": "vendor_payment", "seq": 4},
        {"_id": "daily_help", "seq": 16},
        {"_id": "daily_help_attendance", "seq": 4},
        {"_id": "service_work_report", "seq": 0},
        {"_id": "vehicle", "seq": 3}
    ]
    for c in counters_data:
        db.counters.update_one({"_id": c["_id"]}, {"$set": c}, upsert=True)

    from database.mongodb import sync_counter_max
    sync_counter_max("user_adm", "users", "user_id", "ADM")
    sync_counter_max("user_mgr", "users", "user_id", "MGR")
    sync_counter_max("user_res", "users", "user_id", "RES")
    sync_counter_max("user_tech", "users", "user_id", "TECH")
    sync_counter_max("user_sec", "users", "user_id", "SEC")
    sync_counter_max("complaint", "complaints", "complaint_id", "CMP")
    sync_counter_max("vehicle", "vehicles", "vehicle_id", "VEH")
    sync_counter_max("vendor", "vendors", "vendor_id", "VEN")
    sync_counter_max("vendor_contract", "vendor_contracts", "contract_id", "CON")
    sync_counter_max("vendor_payment", "vendor_payments", "payment_id", "VPAY")
    sync_counter_max("daily_help", "daily_help", "help_id", "HELP")
    sync_counter_max("daily_help_attendance", "daily_help_attendance", "attendance_id", "ATT")
    sync_counter_max("service_work_report", "service_work_reports", "report_id", "WR")

    print("Seed data successfully injected into MongoDB (including 22 external Vendors & 16 Daily Help domestic staff)!")

if __name__ == "__main__":
    seed_database()

