import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from constants import FLASH_MODEL, SEND_MODE_MANUAL
from database import crud, model_catalog
from database.db import Base
from database.models import User


class TestConcurrentRegistration(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(directory.name) / 'bot.db'}",
            connect_args={"check_same_thread": False, "timeout": 5},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        with self.sessions() as session:
            model_catalog.ensure_catalog(session)

    def race_first_contact(self, operations):
        barrier = Barrier(2)
        original_default = crud.get_default_model

        def synchronized_default(session):
            default = original_default(session)
            # Both workers have reached first-contact creation before writing.
            barrier.wait(timeout=5)
            return default

        def contact(operation):
            with self.sessions() as session:
                user = (crud.create_user(session, 123) if operation == "create" else
                        crud.record_user_activity(session, SimpleNamespace(id=123, first_name="User")))
                return user.id

        with patch("database.crud.get_default_model", side_effect=synchronized_default):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(contact, operations))
        self.assertEqual(results, [123, 123])
        with self.sessions() as session:
            self.assertEqual(session.query(User).count(), 1)

    def test_simultaneous_activity_from_start_and_admin_callback_is_safe(self):
        self.race_first_contact(("activity", "activity"))
        with self.sessions() as session:
            self.assertIsNotNone(crud.get_user(session, 123).registered_at)

    def test_user_creation_can_overlap_first_activity_without_duplicate_failure(self):
        self.race_first_contact(("create", "activity"))

    def test_repeated_creation_and_activity_preserve_existing_settings_and_registration(self):
        registered_at = datetime(2026, 1, 2, 3, 4)
        with self.sessions() as session:
            user = crud.create_user(session, 123)
            user.current_model = FLASH_MODEL
            user.pro_access = True
            user.send_mode = SEND_MODE_MANUAL
            user.search_enabled = False
            user.registered_at = registered_at
            session.commit()
            crud.create_user(session, 123)
            crud.record_user_activity(session, SimpleNamespace(id=123, first_name="New name"))
        with self.sessions() as session:
            user = crud.get_user(session, 123)
            self.assertEqual(user.current_model, FLASH_MODEL)
            self.assertTrue(user.pro_access)
            self.assertEqual(user.send_mode, SEND_MODE_MANUAL)
            self.assertFalse(user.search_enabled)
            self.assertEqual(user.registered_at, registered_at)
            self.assertEqual(user.first_name, "New name")
            self.assertIsNotNone(user.last_active_at)


class TestAtomicContextPersistence(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)
        with self.sessions() as session:
            for user_id in (123, 456):
                crud.create_user(session, user_id)
                crud.save_chat_session(session, user_id, 'old history')
                crud.add_file_context(session, user_id, 'pending.txt', 'text/plain', b'pending')
                crud.add_to_buffer(session, user_id, 'text', content='pending message')

    def fail_statement(self, prefix):
        def fail(connection, cursor, statement, parameters, context, executemany):
            if statement.startswith(prefix):
                raise RuntimeError("simulated storage failure")
        event.listen(self.engine, "before_cursor_execute", fail)
        self.addCleanup(event.remove, self.engine, "before_cursor_execute", fail)

    def assert_context(self, session, user_id, history='old history', files=1, buffer=1):
        saved = crud.get_chat_session(session, user_id)
        self.assertEqual(saved.history_json if saved else None, history)
        self.assertEqual(len(crud.get_file_contexts(session, user_id)), files)
        self.assertEqual(len(crud.get_buffer(session, user_id)), buffer)

    def test_saving_response_consumes_only_requested_context_for_that_user(self):
        with self.sessions() as session:
            crud.save_chat_session(session, 123, 'new history', clear_files=True)
            self.assert_context(session, 123, history='new history', files=0)
            self.assert_context(session, 456)
            crud.save_chat_session(session, 123, 'newer history', clear_buffer=True)
            self.assert_context(session, 123, history='newer history', files=0, buffer=0)
            self.assert_context(session, 456)

    def test_failed_history_write_rolls_back_consumption_and_session_can_be_reused(self):
        self.fail_statement('UPDATE chat_sessions')
        with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, 'storage failure'):
                crud.save_chat_session(session, 123, 'new history', clear_files=True, clear_buffer=True)
            self.assert_context(session, 123)
            self.assert_context(session, 456)

    def test_failed_reset_rolls_back_first_delete(self):
        self.fail_statement('DELETE FROM message_buffers')
        with self.sessions() as session:
            with self.assertRaisesRegex(RuntimeError, 'storage failure'):
                crud.clear_user_context(session, 123, clear_history=True)
            self.assert_context(session, 123)
            self.assert_context(session, 456)

    def test_reset_can_clear_pending_context_or_full_dialogue(self):
        with self.sessions() as session:
            crud.clear_user_context(session, 123)
            self.assert_context(session, 123, files=0, buffer=0)
            crud.clear_user_context(session, 456, clear_history=True)
            self.assert_context(session, 456, history=None, files=0, buffer=0)


if __name__ == "__main__":
    unittest.main()
