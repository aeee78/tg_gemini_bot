import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import crud
from database.db import Base


class TestUserProfile(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.addCleanup(self.engine.dispose)
        self.profile = SimpleNamespace(
            id=123, first_name='Анна', last_name='Иванова',
            username='anna', language_code='ru',
        )

    def record_at(self, session, instant):
        with patch('database.crud.datetime') as clock:
            clock.now.return_value = instant
            return crud.record_user_activity(session, self.profile)

    def test_first_contact_and_profile_changes_persist(self):
        first = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
        last = datetime(2026, 11, 7, 14, tzinfo=timezone.utc)
        with self.sessions() as session:
            user = self.record_at(session, first)
            self.assertEqual(user.registered_at, first.replace(tzinfo=None))
            self.assertEqual(user.last_active_at, first.replace(tzinfo=None))
            self.assertFalse(user.pro_access)
            crud.set_user_pro_access(session, 123, True)
        self.profile.first_name = 'Аня'
        self.profile.username = None
        self.profile.last_name = None
        self.profile.language_code = 'en'
        with self.sessions() as session:
            self.record_at(session, last)
        with self.sessions() as session:
            user = crud.get_user(session, 123)
            self.assertEqual(user.first_name, 'Аня')
            self.assertIsNone(user.last_name)
            self.assertIsNone(user.username)
            self.assertEqual(user.language_code, 'en')
            self.assertEqual(user.registered_at, first.replace(tzinfo=None))
            self.assertEqual(user.last_active_at, last.replace(tzinfo=None))
            self.assertTrue(user.pro_access)

    def test_legacy_registration_date_stays_unknown(self):
        with self.sessions() as session:
            crud.create_user(session, 123)
            user = crud.record_user_activity(session, self.profile)
            self.assertIsNone(user.registered_at)
            self.assertIsNotNone(user.last_active_at)
            self.assertEqual(user.first_name, 'Анна')


if __name__ == '__main__':
    unittest.main()
