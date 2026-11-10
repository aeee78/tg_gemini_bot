"""Check explicit recovery and inputs retained after failed model responses."""
import importlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from google.genai import chats, types

from constants import DEFAULT_MODEL, FLASH_MODEL
from database import crud

fixtures = importlib.import_module(
    f'{__package__}.test_bot_regressions' if __package__ else 'test_bot_regressions'
)


class TestRecoveryRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.TestBotRegressions.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    setUp = fixtures.TestBotRegressions.setUp
    tearDown = fixtures.TestBotRegressions.tearDown
    chat = fixtures.TestBotRegressions.chat
    manual = fixtures.TestBotRegressions.manual

    def pending(self):
        with self.sessions() as session:
            crud.add_file_context(session, 123, 'note.txt', 'text/plain', b'Pending file')
            crud.add_to_buffer(session, 123, 'text', content='Pending question')

    def assert_pending(self):
        with self.sessions() as session:
            self.assertEqual(len(crud.get_file_contexts(session, 123)), 1)
            self.assertEqual(len(crud.get_buffer(session, 123)), 1)

    def test_start_preserves_pending_inputs_and_last_downloadable_response(self):
        self.chat()
        self.pending()
        self.app.user_last_responses[123] = 'Previous answer'
        self.app.send_welcome(self.message)
        self.assert_pending()
        self.assertEqual(self.app.user_last_responses[123], 'Previous answer')

    def test_start_offers_explicit_recovery_for_invalid_history_roles(self):
        self.app.client.chats.create.reset_mock()
        for history in ('[{}]', '[{"role":"assistant","parts":[{"text":"Saved text"}]}]'):
            with self.subTest(history=history):
                with self.sessions() as session:
                    crud.save_chat_session(session, 123, history)
                self.app.send_welcome(self.message)
                self.app.client.chats.create.assert_not_called()
                self.assertIn('Для явного сброса', self.app.bot.send_message.call_args.args[1])
                with self.sessions() as session:
                    self.assertEqual(crud.get_chat_session(session, 123).history_json, history)

    def test_new_chat_can_recover_corrupt_history_and_inaccessible_model(self):
        self.pending()
        with self.sessions() as session:
            crud.update_user_model(session, 123, FLASH_MODEL)
            crud.save_chat_session(session, 123, '{invalid history')
        self.message.text = 'Новый чат'
        # Exercise the real decorator, including its model normalization guard.
        from telebot import types as telegram_types
        message = MagicMock(spec=telegram_types.Message)
        message.from_user = SimpleNamespace(id=123)
        message.chat = SimpleNamespace(id=123)
        message.text = 'Новый чат'
        self.app.new_chat(message)
        with self.sessions() as session:
            self.assertEqual(crud.get_user(session, 123).current_model, DEFAULT_MODEL)
            self.assertIsNone(crud.get_chat_session(session, 123))
            self.assertEqual(crud.get_file_contexts(session, 123), [])
            self.assertEqual(crud.get_buffer(session, 123), [])

    def test_new_chat_initialization_failure_keeps_original_context(self):
        previous = self.chat()
        self.pending()
        with self.sessions() as session:
            crud.save_chat_session(session, 123, '[]')
        with patch.object(self.app.client.chats, 'create', side_effect=RuntimeError('SDK failed')):
            self.app.new_chat.__wrapped__(self.message)
        self.assert_pending()
        self.assertIs(self.app.user_chats[123], previous)
        with self.sessions() as session:
            self.assertIsNotNone(crud.get_chat_session(session, 123))

    def test_failed_history_serialization_keeps_inputs_and_evicts_uncommitted_cache(self):
        chat = self.chat()
        self.pending()
        chat.get_history.side_effect = RuntimeError('History unavailable')
        with self.assertRaises(RuntimeError):
            self.app.save_active_chat(123, clear_files=True, clear_buffer=True)
        self.assert_pending()
        self.assertNotIn(123, self.app.user_chats)

    def test_provider_exceptions_are_not_echoed_to_user(self):
        chat = self.chat()
        self.pending()
        chat.send_message.side_effect = RuntimeError('https://provider.invalid/?key=PRIVATE_TEST_KEY')
        self.app.handle_message.__wrapped__(self.message)
        text = self.app.bot.reply_to.call_args.args[1]
        self.assertNotIn('PRIVATE_TEST_KEY', text)
        self.assertNotIn('provider.invalid', text)
        self.assert_pending()

    def test_empty_or_blocked_sdk_turn_keeps_buffer_and_documents(self):
        self.pending()
        self.manual()
        responses = [
            types.GenerateContentResponse(candidates=[]),
            types.GenerateContentResponse(candidates=[types.Candidate(
                finish_reason='SAFETY', content=types.Content(role='model', parts=[]),
            )]),
            types.GenerateContentResponse(candidates=[types.Candidate(
                content=types.Content(role='model', parts=[types.Part(text='Partial'), types.Part()]),
            )]),
        ]
        for response in responses:
            with self.subTest(response=response):
                modules = MagicMock()
                modules.generate_content.return_value = response
                chat = chats.Chat(modules=modules, model=DEFAULT_MODEL, history=[])
                self.app.user_chats[123] = chat
                self.app.handle_send_all.__wrapped__(self.message)
                modules.generate_content.assert_called_once()
                self.assertEqual(chat.get_history(curated=True), [])
                self.assert_pending()
                with self.sessions() as session:
                    self.assertIsNone(crud.get_chat_session(session, 123))
                self.assertIn('Модель не вернула ответ', self.app.bot.reply_to.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
