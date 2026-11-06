import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from constants import DEFAULT_MODEL, FLASH_MODEL
from database import crud, db


class TestWhitelistMigration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.whitelist = self.root / 'whitelist.txt'
        self.engine = create_engine(f"sqlite:///{self.root / 'bot.db'}")
        self.addCleanup(self.engine.dispose)
        self.sessions = sessionmaker(bind=self.engine)
        self.engine_patch = patch.object(db, 'engine', self.engine)
        self.engine_patch.start()
        self.addCleanup(self.engine_patch.stop)
        # Simulate the production schema before pro_access existed.
        with self.engine.begin() as connection:
            connection.exec_driver_sql('''CREATE TABLE users (
                id BIGINT PRIMARY KEY, current_model VARCHAR,
                send_mode VARCHAR, search_enabled BOOLEAN
            )''')
            connection.execute(text('''INSERT INTO users
                VALUES (123, :model, 'manual', 0),
                       (456, :model, 'manual', 1)'''), {'model': FLASH_MODEL})

    def test_import_preserves_settings_and_survives_restart(self):
        original = '123\n789\n\n123\n'
        self.whitelist.write_text(original)
        db.init_db(self.whitelist)
        with self.sessions() as session:
            user = crud.get_user(session, 123)
            self.assertTrue(user.pro_access)
            self.assertIsNone(user.first_name)
            self.assertIsNone(user.username)
            self.assertIsNone(user.registered_at)
            self.assertIsNone(user.last_active_at)
            self.assertEqual(user.current_model, FLASH_MODEL)
            self.assertEqual(user.send_mode, 'manual')
            self.assertFalse(user.search_enabled)
            self.assertFalse(crud.get_user(session, 456).pro_access)
            self.assertTrue(crud.get_user(session, 789).pro_access)
            self.assertEqual(crud.get_user(session, 789).current_model, DEFAULT_MODEL)
            crud.set_user_pro_access(session, 123, False)
            crud.save_chat_session(session, 123, '[{"role":"user"}]')
        db.init_db(self.whitelist)
        with self.sessions() as session:
            self.assertFalse(crud.has_pro_access(session, 123))
            self.assertTrue(crud.has_pro_access(session, 789))
            self.assertEqual(crud.get_chat_session(session, 123).history_json,
                             '[{"role":"user"}]')
        self.assertEqual(self.whitelist.read_text(), original)

    def test_missing_file_can_be_imported_on_later_startup(self):
        db.init_db(self.whitelist)
        with self.sessions() as session:
            self.assertFalse(crud.has_pro_access(session, 123))
        self.whitelist.write_text('123\n')
        db.init_db(self.whitelist)
        with self.sessions() as session:
            self.assertTrue(crud.has_pro_access(session, 123))

    def test_malformed_file_rolls_back_and_can_be_retried(self):
        self.whitelist.write_text('123\nbad-id\n')
        with self.assertRaisesRegex(ValueError, 'line 2'):
            db.init_db(self.whitelist)
        self.assertNotIn('pro_access', {c['name'] for c in inspect(self.engine).get_columns('users')})
        self.whitelist.write_text('123\n789\n')
        db.init_db(self.whitelist)
        with self.sessions() as session:
            self.assertTrue(crud.has_pro_access(session, 123))
            self.assertTrue(crud.has_pro_access(session, 789))

    def test_new_database_defaults_to_no_access(self):
        with self.engine.begin() as connection:
            connection.exec_driver_sql('DROP TABLE users')
        self.whitelist.write_text('')
        db.init_db(self.whitelist)
        with self.sessions() as session:
            user = crud.create_user(session, 999)
            self.assertFalse(user.pro_access)
            self.assertFalse(crud.has_pro_access(session, 888))


if __name__ == '__main__':
    unittest.main()
