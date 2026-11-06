import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin import AdminPanel, register_admin_handlers
from constants import DEFAULT_MODEL, FLASH_MODEL
from database import crud
from database.db import Base
from database.models import User

ADMIN_ID = 66765326


class TestAdmin(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.bot = MagicMock()
        self.panel = AdminPanel(self.bot, self.sessions)
        self.actor = SimpleNamespace(id=ADMIN_ID, first_name='Admin', username=None)
        self.message = SimpleNamespace(
            chat=SimpleNamespace(id=ADMIN_ID, type='private'),
            from_user=self.actor, text='/admin', message_id=1,
        )
        with self.sessions() as session:
            session.add(User(id=123, first_name='<Alice>', username='Alice_test', pro_access=True))
            session.add(User(id=124, username='aliceXtest'))
            session.commit()

    def call(self, data, actor=None, chat_type='private'):
        message = SimpleNamespace(chat=SimpleNamespace(id=ADMIN_ID, type=chat_type), message_id=1)
        call = SimpleNamespace(id='callback', data=data, from_user=actor or self.actor, message=message)
        self.panel.callback(call)

    def test_unauthorized_commands_and_callbacks_never_read_or_write_users(self):
        self.message.from_user = SimpleNamespace(id=999)
        with patch.object(self.panel, 'sessions') as sessions:
            self.panel.command(self.message)
            for data in ('admin:users:all:0', 'admin:stats', 'admin:usage:all:sum:0:0', 'admin:set:123:0:all:0'):
                self.call(data, actor=self.message.from_user)
            sessions.assert_not_called()
        self.bot.send_message.assert_not_called()
        self.bot.edit_message_text.assert_not_called()
        self.bot.answer_callback_query.assert_called_with('callback', 'Нет доступа.', show_alert=True)

    def test_admin_cannot_open_panel_or_mutate_from_group(self):
        self.message.chat.type = 'group'
        with patch.object(self.panel, 'sessions') as sessions:
            self.panel.command(self.message)
            self.call('admin:set:123:0:all:0', chat_type='group')
            sessions.assert_not_called()

    def test_command_searches_exact_username_case_insensitively(self):
        self.message.text = '/admin @ALICE_TEST'
        self.panel.command(self.message)
        text = self.bot.send_message.call_args.args[1]
        self.assertIn('ID: 123', text)
        self.assertIn('<Alice>', text)
        self.assertEqual(self.bot.send_message.call_args.kwargs['parse_mode'], None)
        with self.sessions() as session:
            self.assertEqual([u.id for u in crud.find_admin_users(session, '@ALICE_TEST')], [123])
            self.assertEqual([u.id for u in crud.find_admin_users(session, '124')], [124])
            self.assertEqual(crud.find_admin_users(session, '9' * 60), [])

    def test_revoke_requires_confirmation_and_grant_is_idempotent(self):
        self.call('admin:confirm:123:all:0')
        with self.sessions() as session:
            self.assertTrue(crud.get_user(session, 123).pro_access)
        markup = self.bot.edit_message_text.call_args.kwargs['reply_markup'].to_dict()
        self.assertEqual(markup['inline_keyboard'][0][0]['callback_data'], 'admin:set:123:0:all:0')
        self.call('admin:set:123:0:all:0')
        with self.sessions() as session:
            self.assertFalse(crud.get_user(session, 123).pro_access)
        self.call('admin:set:123:1:all:0')
        self.call('admin:set:123:1:all:0')
        with self.sessions() as session:
            self.assertTrue(crud.get_user(session, 123).pro_access)
        self.call('admin:set:999:1:all:0')
        with self.sessions() as session:
            self.assertIsNone(crud.get_user(session, 999))

    def test_pagination_and_whitelist_handle_removed_last_page(self):
        with self.sessions() as session:
            session.add_all(User(id=i, first_name=str(i), pro_access=True) for i in range(200, 209))
            session.commit()
        self.call('admin:users:pro:1')
        text = self.bot.edit_message_text.call_args.args[0]
        self.assertIn('Страница 2 из 2', text)
        with self.sessions() as session:
            session.query(User).filter(User.id >= 200).update({'pro_access': False})
            session.commit()
        self.call('admin:users:pro:1')
        text = self.bot.edit_message_text.call_args.args[0]
        self.assertIn('Страница 1 из 1', text)
        self.assertIn('Белый список: 1', text)

    def test_statistics_use_real_activity_and_selected_models(self):
        now = datetime(2026, 11, 6, 12)
        with self.sessions() as session:
            crud.get_user(session, 123).last_active_at = now - timedelta(hours=2)
            crud.get_user(session, 124).last_active_at = now - timedelta(days=5)
            session.add(User(id=125, last_active_at=now - timedelta(days=20), current_model=FLASH_MODEL))
            session.add(User(id=126))
            session.commit()
            with patch('database.crud.datetime') as clock:
                clock.now.return_value = now.replace(tzinfo=timezone.utc)
                stats = crud.get_admin_statistics(session)
        self.assertEqual([stats[k] for k in ('total', 'pro', 'day', 'week', 'month')], [4, 1, 1, 2, 3])
        self.assertEqual(dict(stats['models']), {DEFAULT_MODEL: 3, FLASH_MODEL: 1})
        self.call('admin:stats')
        self.assertIn('Статистика', self.bot.edit_message_text.call_args.args[0])

    def test_registration_is_independent_and_callback_namespace_is_specific(self):
        panel = register_admin_handlers(self.bot, self.sessions)
        self.assertIsInstance(panel, AdminPanel)
        self.bot.register_message_handler.assert_called_with(panel.command, commands=['admin'])
        predicate = self.bot.register_callback_query_handler.call_args.kwargs['func']
        self.assertTrue(predicate(SimpleNamespace(data='admin:home')))
        self.assertFalse(predicate(SimpleNamespace(data='model_gemini-3.8-flash')))
        self.assertFalse(predicate(SimpleNamespace(data=None)))


if __name__ == '__main__':
    unittest.main()
