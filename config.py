import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "apartment-secure-secret-key-2026-prod-rnd-98745")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = os.getenv("DB_NAME", "apartment_management_db")
    PENDING_BOOKING_EXPIRY_MINUTES = int(os.getenv("PENDING_BOOKING_EXPIRY_MINUTES", "60"))
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32MB max upload for GridFS media
