import sys
import os

try:
    from app.config import config
    from app.database import models, core, requests
    from app.handlers import base, settings, chat, manual, tools, callbacks
    from app.services import gemini
    from app.utils import text
    from app.middlewares import db_middleware
    print("Imports successful!")
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
