import sys
import os
from dotenv import load_dotenv

# Path to the project directory
project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Load environment variables from .env
load_dotenv(os.path.join(project_home, '.env'))

# Ensure database indexes are created
try:
    from database.indexes import create_indexes
    create_indexes()
except Exception as e:
    print(f"Startup index warning: {e}")

# Import the Flask application instance
from app import app as application
