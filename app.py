import os
from datetime import datetime
from flask import Flask, render_template, session
from config import Config
from database.mongodb import get_db
from database.indexes import create_indexes
from services.notification_service import get_unread_count

# Import route blueprints
from routes.auth_routes import auth_bp
from routes.resident_routes import resident_bp
from routes.manager_routes import manager_bp
from routes.technician_routes import technician_bp
from routes.security_routes import security_bp
from routes.admin_routes import admin_bp
from routes.notification_routes import notification_bp
from routes.community_collection_routes import community_bp
from routes.vendor_routes import vendor_bp
from routes.daily_help_routes import daily_help_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(resident_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(technician_bp)
    app.register_blueprint(security_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(vendor_bp)
    app.register_blueprint(daily_help_bp)

    # Context Processors
    @app.context_processor
    def inject_global_data():
        user_id = session.get("user_id")
        unread_count = 0
        user_data = None
        if user_id:
            try:
                unread_count = get_unread_count(user_id)
                db = get_db()
                user_data = db.users.find_one({"user_id": user_id})
            except Exception:
                pass
        return {
            "current_user": user_data,
            "unread_count": unread_count,
            "session_role": session.get("role"),
            "session_name": session.get("name")
        }

    # Custom Jinja filters
    @app.template_filter("datetime_format")
    def datetime_format(val, fmt="%b %d, %Y - %I:%M %p"):
        if not val:
            return "N/A"
        if isinstance(val, str):
            try:
                val = datetime.fromisoformat(val)
            except Exception:
                return val
        return val.strftime(fmt)

    # Prevent caching of HTML responses to prevent stale back-button access after logout
    @app.after_request
    def add_security_and_cache_headers(response):
        if "text/html" in response.headers.get("Content-Type", ""):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # Friendly Error Handlers
    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/404.html"), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return render_template("errors/403.html"), 401

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(405)
    def method_not_allowed(e):
        return render_template("errors/404.html"), 405

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/500.html"), 500

    @app.route("/api/parking/available-slots", methods=["GET"])
    def global_available_parking_slots():
        from flask import jsonify, request
        from services.parking_service import get_parking_slots_status
        current_veh_id = request.args.get("vehicle_id")
        slots = get_parking_slots_status(current_vehicle_id=current_veh_id)
        return jsonify({
            "success": True,
            "total_slots": len(slots),
            "available_slots": [s for s in slots if not s["is_occupied"]],
            "slots": slots
        })

    return app

app = create_app()

if __name__ == "__main__":
    # Ensure indexes exist on startup
    try:
        create_indexes()
    except Exception as e:
        print(f"Index creation note: {e}")
    app.run(host="0.0.0.0", port=5000, debug=True)
