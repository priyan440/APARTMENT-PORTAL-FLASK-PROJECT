import gridfs
from pymongo import MongoClient, ReturnDocument
from config import Config

_client = None
_db = None
_fs = None

def get_mongo_client():
    global _client
    if _client is None:
        _client = MongoClient(Config.MONGO_URI)
    return _client

def get_db():
    global _db
    if _db is None:
        client = get_mongo_client()
        _db = client[Config.DB_NAME]
    return _db

def get_gridfs():
    global _fs
    if _fs is None:
        db = get_db()
        _fs = gridfs.GridFS(db)
    return _fs

def get_next_sequence(sequence_name: str, prefix: str = "", padding: int = 3) -> str:
    """Generate human-readable sequential IDs such as ADM001, CMP001, BK001, VPAY001, etc."""
    db = get_db()
    counter = db.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    seq = counter["seq"]
    return f"{prefix}{str(seq).zfill(padding)}"

def sync_counter_max(sequence_name: str, collection_name: str, field_name: str, prefix: str):
    """Ensure sequence counter is at least as high as the highest existing numeric suffix in collection."""
    try:
        db = get_db()
        docs = list(db[collection_name].find({field_name: {"$regex": f"^{prefix}\\d+"}}, {field_name: 1}))
        max_num = 0
        for d in docs:
            val = str(d.get(field_name, ""))
            if val.startswith(prefix):
                try:
                    num = int(val[len(prefix):])
                    if num > max_num:
                        max_num = num
                except ValueError:
                    pass
        if max_num > 0:
            db.counters.update_one(
                {"_id": sequence_name},
                {"$max": {"seq": max_num}},
                upsert=True
            )
    except Exception as e:
        print(f"Sync counter note: {e}")

