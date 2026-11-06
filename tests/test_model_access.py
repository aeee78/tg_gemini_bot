import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from constants import DEFAULT_MODEL, FLASH_MODEL, IMAGE_MODEL
from database import crud
from database.db import Base


class TestModelAccess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Import handlers without contacting Telegram or Gemini.
        with patch('telebot.TeleBot') as factory, patch('google.genai.Client'):
            factory.return_value.message_handler.side_effect = lambda **kw: lambda f: f
            factory.return_value.callback_query_handler.side_effect = lambda **kw: lambda f: f
            cls.app = importlib.import_module('gemini_bot')
        cls.engine = create_engine('sqlite:///:memory:')
        cls.sessions = sessionmaker(bind=cls.engine)

    def setUp(self):
        Base.metadata.create_all(self.engine)
        self.session_patch = patch.object(self.app, 'SessionLocal', self.sessions)
        self.session_patch.start()
        self.app.user_chats.clear()
        self.app.bot.reset_mock()
        self.app.client.reset_mock()
        with self.sessions() as session:
            crud.create_user(session, 123)
        self.message = SimpleNamespace(
            from_user=SimpleNamespace(id=123), chat=SimpleNamespace(id=123),
            message_id=1, text='/promptpro hello',
        )

    def tearDown(self):
        self.session_patch.stop()
        self.app.user_chats.clear()
        Base.metadata.drop_all(self.engine)

    def set_access(self, enabled):
        with self.sessions() as session:
            crud.set_user_pro_access(session, 123, enabled)

    def test_new_user_defaults_to_lite(self):
        with self.sessions() as session:
            self.assertEqual(crud.get_user(session, 123).current_model, 'gemini-3.5-flash-lite')

    def test_saved_models_respect_access_and_retirement(self):
        for model, unlocked, expected in [
            ('gemini-3.1-pro-preview', True, DEFAULT_MODEL),
            ('gemini-3.7-flash', False, DEFAULT_MODEL),
            (FLASH_MODEL, False, DEFAULT_MODEL),
            (IMAGE_MODEL, False, DEFAULT_MODEL),
            (FLASH_MODEL, True, FLASH_MODEL),
            (IMAGE_MODEL, True, IMAGE_MODEL),
        ]:
            with self.subTest(model=model, unlocked=unlocked), self.sessions() as session:
                self.set_access(unlocked)
                user = crud.update_user_model(session, 123, model)
                crud.save_chat_session(session, 123, '[]')
                self.app.user_chats[123] = object()
                self.app.ensure_user_model(session, user)
                self.assertEqual(crud.get_user(session, 123).current_model, expected)
                self.assertIsNotNone(crud.get_chat_session(session, 123))
                if model != expected:
                    self.assertNotIn(123, self.app.user_chats)

    def test_model_selection_requires_code(self):
        for model in (FLASH_MODEL, IMAGE_MODEL, 'gemini-3.1-pro-preview'):
            with self.subTest(model=model):
                call = SimpleNamespace(from_user=self.message.from_user,
                                       message=self.message, id='callback',
                                       data='model_' + model)
                self.app.handle_model_selection.__wrapped__(call)
                with self.sessions() as session:
                    self.assertEqual(crud.get_user(session, 123).current_model, DEFAULT_MODEL)
                self.app.client.chats.create.assert_not_called()

    def test_quick_tools_require_code_and_use_flash(self):
        for command in ('promptpro', 'table', 'dayplanner'):
            with self.subTest(command=command):
                self.message.text = '/' + command + ' hello'
                self.set_access(False)
                self.app.client.reset_mock()
                self.app.handle_quick_tool_command.__wrapped__(self.message)
                self.app.client.models.generate_content.assert_not_called()
                self.set_access(True)
                with patch.object(self.app, 'send_rich_response'), patch.object(self.app, 'send_text_as_file'):
                    self.app.handle_quick_tool_command.__wrapped__(self.message)
                self.assertEqual(self.app.client.models.generate_content.call_args.kwargs['model'], FLASH_MODEL)

    def test_unlocked_user_can_select_premium_models(self):
        self.set_access(True)
        for model in (FLASH_MODEL, IMAGE_MODEL):
            with self.subTest(model=model):
                call = SimpleNamespace(from_user=self.message.from_user,
                                       message=self.message, id='callback',
                                       data='model_' + model)
                self.app.handle_model_selection.__wrapped__(call)
                with self.sessions() as session:
                    self.assertEqual(crud.get_user(session, 123).current_model, model)

    def test_regular_quick_tool_uses_lite_without_code(self):
        self.message.text = '/prompt hello'
        with patch.object(self.app, 'send_rich_response'):
            self.app.handle_quick_tool_command.__wrapped__(self.message)
        self.assertEqual(self.app.client.models.generate_content.call_args.kwargs['model'], DEFAULT_MODEL)

    def test_unlock_persists_access_and_revocation_is_immediate(self):
        self.message.text = '/unlock_pro test-code'
        with patch.object(self.app, 'PRO_CODE', 'test-code'):
            self.app.handle_unlock_pro.__wrapped__(self.message)
        with self.sessions() as session:
            self.assertTrue(crud.get_user(session, 123).pro_access)
        self.assertTrue(self.app.is_whitelisted(123))
        self.set_access(False)
        self.assertFalse(self.app.is_whitelisted(123))

    def test_activity_uses_callback_sender_and_tracks_start_and_help(self):
        from telebot import types

        profile = SimpleNamespace(id=123, first_name='Sender', username='sender')
        callback = MagicMock(spec=types.CallbackQuery)
        callback.from_user = profile
        callback.message = SimpleNamespace(
            chat=SimpleNamespace(id=123), from_user=SimpleNamespace(id=999)
        )  # The message author is the bot, not the person clicking.
        handler = self.app.ensure_user_started(lambda event: None)
        handler(callback)
        with self.sessions() as session:
            self.assertEqual(crud.get_user(session, 123).username, 'sender')
            self.assertIsNone(crud.get_user(session, 999))
        self.message.from_user = profile
        self.app.handle_help_command(self.message)
        with patch.object(self.app, 'get_active_chat'):
            self.app.send_welcome(self.message)
        with self.sessions() as session:
            self.assertEqual(crud.get_user(session, 123).first_name, 'Sender')
            self.assertIsNotNone(crud.get_user(session, 123).last_active_at)

    def test_unset_access_code_does_not_unlock(self):
        self.message.text = '/unlock_pro None'
        with patch.object(self.app, 'PRO_CODE', None), patch.object(self.app, 'add_to_whitelist') as add:
            self.app.handle_unlock_pro.__wrapped__(self.message)
            add.assert_not_called()


if __name__ == '__main__':
    unittest.main()
