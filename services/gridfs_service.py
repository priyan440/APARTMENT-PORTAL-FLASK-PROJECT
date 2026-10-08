import os
from bson import ObjectId
from database.mongodb import get_gridfs
from werkzeug.utils import secure_filename
from flask import Response

ALLOWED_EXTENSIONS = {
    "image": {"png", "jpg", "jpeg", "gif", "webp"},
    "video": {"mp4", "mov", "avi", "webm", "mkv"},
    "document": {"pdf", "doc", "docx", "txt"}
}

def allowed_file(filename: str) -> tuple[bool, str]:
    if "." not in filename:
        return False, "unknown"
    ext = filename.rsplit(".", 1)[1].lower()
    if ext in ALLOWED_EXTENSIONS["image"]:
        return True, "image"
    if ext in ALLOWED_EXTENSIONS["video"]:
        return True, "video"
    if ext in ALLOWED_EXTENSIONS["document"]:
        return True, "document"
    return False, "unknown"

def save_file_to_gridfs(file_storage) -> dict:
    if not file_storage or file_storage.filename == "":
        return None
    
    filename = secure_filename(file_storage.filename)
    is_allowed, media_type = allowed_file(filename)
    if not is_allowed:
        raise ValueError(f"File type not supported for '{filename}'. Upload valid images, videos, or documents (PDF/DOC).")

    fs = get_gridfs()
    file_id = fs.put(
        file_storage.stream,
        filename=filename,
        content_type=file_storage.content_type
    )

    return {
        "file_id": str(file_id),
        "filename": filename,
        "content_type": file_storage.content_type,
        "type": media_type
    }

def get_file_from_gridfs(file_id_str: str):
    try:
        fs = get_gridfs()
        grid_out = fs.get(ObjectId(file_id_str))
        return grid_out
    except Exception:
        return None

def stream_gridfs_file(file_id_str: str):
    grid_out = get_file_from_gridfs(file_id_str)
    if not grid_out:
        return None
    
    def generate():
        while True:
            chunk = grid_out.read(1024 * 64)
            if not chunk:
                break
            yield chunk

    response = Response(generate(), mimetype=grid_out.content_type)
    response.headers["Content-Disposition"] = f'inline; filename="{grid_out.filename}"'
    return response
