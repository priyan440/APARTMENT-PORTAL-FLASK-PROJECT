from datetime import datetime, timedelta
from database.mongodb import get_db

def get_dashboard_summary():
    """High-level counters for Admin and Manager dashboards."""
    db = get_db()
    
    total_residents = db.users.count_documents({"role": "RESIDENT", "status": "ACTIVE"})
    total_managers = db.users.count_documents({"role": "MANAGER", "status": "ACTIVE"})
    total_technicians = db.users.count_documents({"role": "TECHNICIAN", "status": "ACTIVE"})
    total_security = db.users.count_documents({"role": "SECURITY", "status": "ACTIVE"})
    
    total_blocks = db.blocks.count_documents({})
    total_flats = db.flats.count_documents({})
    occupied_flats = db.flats.count_documents({"status": "OCCUPIED"})
    vacant_flats = total_flats - occupied_flats
    
    open_complaints = db.complaints.count_documents({"status": {"$in": ["OPEN", "ASSIGNED", "IN_PROGRESS"]}})
    pending_bookings = db.bookings.count_documents({"status": "PENDING"})
    
    # Billing metrics
    billing_pipeline = [
        {"$group": {
            "_id": "$status",
            "total": {"$sum": "$total_amount"},
            "count": {"$sum": 1}
        }}
    ]
    billing_stats = {item["_id"]: item["total"] for item in db.bills.aggregate(billing_pipeline)}
    total_collected = billing_stats.get("PAID", 0.0)
    total_pending = billing_stats.get("PENDING", 0.0) + billing_stats.get("OVERDUE", 0.0)
    
    # Community Collections metrics
    comm_pipeline = [
        {"$match": {"status": {"$ne": "CANCELLED"}}},
        {"$group": {
            "_id": "$status",
            "total": {"$sum": "$total_amount"},
            "count": {"$sum": 1}
        }}
    ]
    comm_stats = {item["_id"]: item["total"] for item in db.community_collection_payments.aggregate(comm_pipeline)}
    total_comm_collected = comm_stats.get("PAID", 0.0)
    total_comm_pending = comm_stats.get("PENDING", 0.0) + comm_stats.get("OVERDUE", 0.0)
    active_collections_count = db.community_collections.count_documents({"status": {"$in": ["ACTIVE", "PAYMENT_OPEN"]}})

    # Visitors today
    today_str = datetime.now().strftime("%Y-%m-%d")
    visitors_today = db.visitors.count_documents({"expected_date": today_str})

    # Active SOS
    active_sos = db.emergency_alerts.count_documents({"status": "ACTIVE"})

    return {
        "total_residents": total_residents,
        "total_managers": total_managers,
        "total_technicians": total_technicians,
        "total_security": total_security,
        "total_blocks": total_blocks,
        "total_flats": total_flats,
        "occupied_flats": occupied_flats,
        "vacant_flats": vacant_flats,
        "open_complaints": open_complaints,
        "pending_bookings": pending_bookings,
        "total_collected": total_collected,
        "total_pending": total_pending,
        "total_comm_collected": total_comm_collected,
        "total_comm_pending": total_comm_pending,
        "active_collections_count": active_collections_count,
        "visitors_today": visitors_today,
        "active_sos": active_sos
    }

def get_analytics_charts_data():
    """MongoDB Aggregations for visual charts."""
    db = get_db()

    # 1. Residents per Block
    residents_by_block = list(db.users.aggregate([
        {"$match": {"role": "RESIDENT", "status": "ACTIVE"}},
        {"$group": {"_id": "$block", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]))

    # 2. Owner vs Tenant
    owner_vs_tenant = list(db.users.aggregate([
        {"$match": {"role": "RESIDENT", "status": "ACTIVE"}},
        {"$group": {"_id": "$resident_type", "count": {"$sum": 1}}}
    ]))

    # 3. Complaints by Category
    complaints_by_category = list(db.complaints.aggregate([
        {"$group": {"_id": "$category", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]))

    # 4. Complaints by Status
    complaints_by_status = list(db.complaints.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]))

    # 5. Complaints by Block
    complaints_by_block = list(db.complaints.aggregate([
        {"$group": {"_id": "$block", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]))

    # 6. Bookings per Amenity
    bookings_by_amenity = list(db.bookings.aggregate([
        {"$group": {"_id": "$amenity_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]))

    # 7. Bookings by Status
    bookings_by_status = list(db.bookings.aggregate([
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]))

    # 8. Billing Collection by Block
    billing_by_block = list(db.bills.aggregate([
        {"$group": {
            "_id": "$block",
            "billed": {"$sum": "$total_amount"},
            "collected": {"$sum": {"$cond": [{"$eq": ["$status", "PAID"]}, "$total_amount", 0]}},
            "pending": {"$sum": {"$cond": [{"$ne": ["$status", "PAID"]}, "$total_amount", 0]}}
        }},
        {"$sort": {"_id": 1}}
    ]))

    # 9. Technician Performance
    tech_performance = list(db.users.aggregate([
        {"$match": {"role": "TECHNICIAN"}},
        {"$project": {
            "_id": 0,
            "user_id": 1,
            "name": 1,
            "specialization": 1,
            "active_tasks": 1,
            "completed_tasks": 1,
            "rating": {"$ifNull": ["$rating", 5.0]}
        }}
    ]))

    # 10. Community Collections by Category
    comm_by_cat = list(db.community_collection_payments.aggregate([
        {"$match": {"status": {"$ne": "CANCELLED"}}},
        {"$group": {
            "_id": "$collection_type",
            "collected": {"$sum": {"$cond": [{"$eq": ["$status", "PAID"]}, "$total_amount", 0]}},
            "pending": {"$sum": {"$cond": [{"$ne": ["$status", "PAID"]}, "$total_amount", 0]}}
        }},
        {"$sort": {"collected": -1}}
    ]))

    # 11. Community Collections by Block
    comm_by_block = list(db.community_collection_payments.aggregate([
        {"$match": {"status": {"$ne": "CANCELLED"}}},
        {"$group": {
            "_id": "$block",
            "collected": {"$sum": {"$cond": [{"$eq": ["$status", "PAID"]}, "$total_amount", 0]}},
            "pending": {"$sum": {"$cond": [{"$ne": ["$status", "PAID"]}, "$total_amount", 0]}}
        }},
        {"$sort": {"_id": 1}}
    ]))

    # Format into easy labels & values for Chart.js
    return {
        "residents_by_block": {
            "labels": [f"Block {r['_id']}" for r in residents_by_block if r["_id"]],
            "data": [r["count"] for r in residents_by_block if r["_id"]]
        },
        "owner_vs_tenant": {
            "labels": [o["_id"] or "Owner" for o in owner_vs_tenant],
            "data": [o["count"] for o in owner_vs_tenant]
        },
        "complaints_by_category": {
            "labels": [c["_id"] for c in complaints_by_category],
            "data": [c["count"] for c in complaints_by_category]
        },
        "complaints_by_status": {
            "labels": [s["_id"] for s in complaints_by_status],
            "data": [s["count"] for s in complaints_by_status]
        },
        "complaints_by_block": {
            "labels": [f"Block {b['_id']}" for b in complaints_by_block if b["_id"]],
            "data": [b["count"] for b in complaints_by_block if b["_id"]]
        },
        "bookings_by_amenity": {
            "labels": [a["_id"] for a in bookings_by_amenity],
            "data": [a["count"] for a in bookings_by_amenity]
        },
        "bookings_by_status": {
            "labels": [b["_id"] for b in bookings_by_status],
            "data": [b["count"] for b in bookings_by_status]
        },
        "billing_by_block": {
            "labels": [f"Block {bl['_id']}" for bl in billing_by_block if bl["_id"]],
            "collected": [bl["collected"] for bl in billing_by_block if bl["_id"]],
            "pending": [bl["pending"] for bl in billing_by_block if bl["_id"]]
        },
        "community_by_category": {
            "labels": [c["_id"] for c in comm_by_cat if c["_id"]],
            "collected": [c["collected"] for c in comm_by_cat if c["_id"]],
            "pending": [c["pending"] for c in comm_by_cat if c["_id"]]
        },
        "community_by_block": {
            "labels": [f"Block {cb['_id']}" for cb in comm_by_block if cb["_id"]],
            "collected": [cb["collected"] for cb in comm_by_block if cb["_id"]],
            "pending": [cb["pending"] for cb in comm_by_block if cb["_id"]]
        },
        "technicians": tech_performance
    }
