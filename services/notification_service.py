from datetime import datetime
from database.mongodb import get_db, get_next_sequence

def create_notification(user_id: str, title: str, message: str, link: str = "#", n_type: str = "INFO"):
    db = get_db()
    notif_id = get_next_sequence("notification", prefix="NOTIF", padding=4)
    doc = {
        "notification_id": notif_id,
        "user_id": user_id,
        "title": title,
        "message": message,
        "link": link,
        "type": n_type, # INFO, SUCCESS, WARNING, DANGER
        "is_read": False,
        "created_at": datetime.now()
    }
    db.notifications.insert_one(doc)
    return doc

def get_user_notifications(user_id: str, limit: int = 15):
    db = get_db()
    return list(db.notifications.find({"user_id": user_id}).sort("created_at", -1).limit(limit))

def get_unread_count(user_id: str) -> int:
    db = get_db()
    return db.notifications.count_documents({"user_id": user_id, "is_read": False})

def mark_as_read(notif_id: str, user_id: str):
    db = get_db()
    db.notifications.update_one(
        {"notification_id": notif_id, "user_id": user_id},
        {"$set": {"is_read": True}}
    )

def mark_all_read(user_id: str):
    db = get_db()
    db.notifications.update_many(
        {"user_id": user_id, "is_read": False},
        {"$set": {"is_read": True}}
    )
