import unittest
import json
import base64
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import crud
from database.db import Base
from utils import BytesEncoder
from constants import DEFAULT_MODEL

# Use in-memory DB for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class TestPersistenceIntegration(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        self.user_id = 12345

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_user_persistence(self):
        # Create
        user = crud.get_or_create_user(self.db, self.user_id)
        self.assertEqual(user.id, self.user_id)
        self.assertEqual(user.current_model, DEFAULT_MODEL) # Default

        # Update
        updated = crud.update_user_model(self.db, self.user_id, "gemini-pro")
        self.assertEqual(updated.current_model, "gemini-pro")

        # Retrieve fresh
        fresh = crud.get_user(self.db, self.user_id)
        self.assertEqual(fresh.current_model, "gemini-pro")

    def test_chat_history_serialization(self):
        # Simulate history data (list of dicts as if coming from model_dump)
        history_data = [
            {
                "role": "user",
                "parts": [{"text": "hello"}]
            },
            {
                "role": "model",
                "parts": [{"text": "hi", "inline_data": {"mime_type": "image/png", "data": b"fakebytes"}}]
            }
        ]

        # Serialize
        json_str = json.dumps(history_data, cls=BytesEncoder)

        # Save
        crud.save_chat_session(self.db, self.user_id, json_str)

        # Retrieve
        session_obj = crud.get_chat_session(self.db, self.user_id)
        self.assertIsNotNone(session_obj)

        # Deserialize manually to check bytes reconstruction
        loaded_data = json.loads(session_obj.history_json)
        self.assertEqual(loaded_data[0]["role"], "user")
        self.assertEqual(loaded_data[1]["parts"][0]["inline_data"]["data"], base64.b64encode(b"fakebytes").decode('utf-8'))

    def test_file_context_persistence(self):
        filename = "test.txt"
        data = b"some content"
        mime = "text/plain"

        crud.add_file_context(self.db, self.user_id, filename, mime, data)

        files = crud.get_file_contexts(self.db, self.user_id)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].data, data)

        crud.clear_file_contexts(self.db, self.user_id)
        files = crud.get_file_contexts(self.db, self.user_id)
        self.assertEqual(len(files), 0)

    def test_message_buffer_persistence(self):
        crud.add_to_buffer(self.db, self.user_id, "text", content="msg1")
        crud.add_to_buffer(self.db, self.user_id, "photo", content="cap1", blob_data=b"imgdata")

        buffer = crud.get_buffer(self.db, self.user_id)
        self.assertEqual(len(buffer), 2)
        self.assertEqual(buffer[0].content, "msg1")
        self.assertEqual(buffer[1].blob_data, b"imgdata")

        crud.clear_buffer(self.db, self.user_id)
        buffer = crud.get_buffer(self.db, self.user_id)
        self.assertEqual(len(buffer), 0)

if __name__ == "__main__":
    unittest.main()
