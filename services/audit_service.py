from datetime import datetime
from database.mongodb import get_db, get_next_sequence

def log_action(user_id: str, user_name: str, role: str, action: str, entity: str, entity_id: str, details: str = ""):
    db = get_db()
    log_id = get_next_sequence("audit_log", prefix="LOG", padding=4)
    log_doc = {
        "log_id": log_id,
        "user_id": user_id,
        "user_name": user_name,
        "role": role,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "details": details,
        "timestamp": datetime.now()
    }
    db.audit_logs.insert_one(log_doc)
    return log_doc

def get_recent_logs(limit: int = 50):
    db = get_db()
    return list(db.audit_logs.find().sort("timestamp", -1).limit(limit))
