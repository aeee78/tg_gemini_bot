import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
        self.app.whitelisted_users.clear()
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
        self.app.whitelisted_users.clear()
        self.app.user_chats.clear()
        Base.metadata.drop_all(self.engine)

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
                self.app.whitelisted_users.clear()
                if unlocked:
                    self.app.whitelisted_users.add(123)
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
                self.app.whitelisted_users.clear()
                self.app.client.reset_mock()
                self.app.handle_quick_tool_command.__wrapped__(self.message)
                self.app.client.models.generate_content.assert_not_called()
                self.app.whitelisted_users.add(123)
                with patch.object(self.app, 'send_rich_response'), patch.object(self.app, 'send_text_as_file'):
                    self.app.handle_quick_tool_command.__wrapped__(self.message)
                self.assertEqual(self.app.client.models.generate_content.call_args.kwargs['model'], FLASH_MODEL)

    def test_unlocked_user_can_select_premium_models(self):
        self.app.whitelisted_users.add(123)
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

    def test_unset_access_code_does_not_unlock(self):
        self.message.text = '/unlock_pro None'
        with patch.object(self.app, 'PRO_CODE', None), patch.object(self.app, 'add_to_whitelist') as add:
            self.app.handle_unlock_pro.__wrapped__(self.message)
            add.assert_not_called()


if __name__ == '__main__':
    unittest.main()
