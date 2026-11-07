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
        telemetry_patch = patch('usage.SessionLocal', self.sessions)
        telemetry_patch.start()
        self.addCleanup(telemetry_patch.stop)
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

    def test_model_switch_preserves_history_files_buffer_and_download(self):
        from google.genai import types
        history = [types.Content(role='user', parts=[types.Part(text='Remember me')]),
                   types.Content(role='model', parts=[types.Part(text='Answer', thought_signature=b'signature')])]
        old_chat = MagicMock()
        old_chat.get_history.return_value = history
        self.app.user_chats[123] = old_chat
        self.app.user_last_responses[123] = 'Last answer'
        self.set_access(True)
        with self.sessions() as session:
            crud.add_file_context(session, 123, 'file.txt', 'text/plain', b'file')
            crud.add_to_buffer(session, 123, 'text', content='pending')
        call = SimpleNamespace(from_user=self.message.from_user, message=self.message,
                               id='callback', data='model_' + FLASH_MODEL)
        with patch.object(self.app.client.chats, 'create') as create:
            self.app.handle_model_selection.__wrapped__(call)
            self.assertIs(self.app.user_chats[123], create.return_value)
            self.assertEqual(create.call_args.kwargs['history'][0].parts[0].text, 'Remember me')
        with self.sessions() as session:
            self.assertEqual(crud.get_user(session, 123).current_model, FLASH_MODEL)
            stored = self.app.deserialize_history(crud.get_chat_session(session, 123).history_json)
            self.assertEqual(stored[0].parts[0].text, 'Remember me')
            self.assertIsNone(stored[1].parts[0].thought_signature)
            self.assertEqual(len(crud.get_file_contexts(session, 123)), 1)
            self.assertEqual(len(crud.get_buffer(session, 123)), 1)
        self.assertEqual(self.app.user_last_responses[123], 'Last answer')

    def test_failed_switch_keeps_original_model_and_cache(self):
        self.set_access(True)
        old_chat = MagicMock()
        old_chat.get_history.return_value = []
        self.app.user_chats[123] = old_chat
        call = SimpleNamespace(from_user=self.message.from_user, message=self.message,
                               id='callback', data='model_' + FLASH_MODEL)
        with patch.object(self.app.client.chats, 'create', side_effect=ValueError('cannot create')):
            self.app.handle_model_selection.__wrapped__(call)
        with self.sessions() as session:
            self.assertEqual(crud.get_user(session, 123).current_model, DEFAULT_MODEL)
        self.assertIs(self.app.user_chats[123], old_chat)

    def test_context_counts_snapshot_without_generating_or_clearing(self):
        from google.genai import types
        chat = MagicMock()
        chat.get_history.return_value = [types.Content(role='user', parts=[types.Part(text='History')])]
        self.app.user_chats[123] = chat
        self.app.client.models.count_tokens.return_value = SimpleNamespace(total_tokens=1234)
        self.app.client.models.get.return_value = SimpleNamespace(input_token_limit=10000)
        with self.sessions() as session:
            crud.add_file_context(session, 123, 'file.txt', 'text/plain', b'file')
            crud.add_to_buffer(session, 123, 'text', content='pending')
        self.app.show_context_size.__wrapped__(self.message)
        text = self.app.bot.reply_to.call_args.args[1]
        self.assertIn('1 234', text)
        self.assertIn('12.3%', text)
        self.assertIn('Ожидающих файлов: 1', text)
        self.app.client.models.generate_content.assert_not_called()
        with self.sessions() as session:
            self.assertEqual(len(crud.get_buffer(session, 123)), 1)
            self.assertEqual(len(crud.get_file_contexts(session, 123)), 1)

    def test_binary_thought_signature_survives_history_serialization(self):
        from google.genai import types
        from chat_context import serialize_history
        history = [types.Content(role='model', parts=[types.Part(text='Answer', thought_signature=b'\x00\xff')])]
        self.assertEqual(self.app.deserialize_history(serialize_history(history))[0].parts[0].thought_signature, b'\x00\xff')

    def test_model_callback_during_inflight_request_does_not_change_chat(self):
        from threading import Event, Thread
        from telebot import types
        entered, release = Event(), Event()
        def ongoing(message):
            entered.set()
            release.wait(3)
        thread = Thread(target=self.app.serialize_user_operation(ongoing), args=(self.message,))
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            callback = MagicMock(spec=types.CallbackQuery)
            callback.from_user = self.message.from_user
            callback.id = 'callback'
            action = MagicMock()
            self.app.serialize_user_operation(action)(callback)
            action.assert_not_called()
            self.app.bot.answer_callback_query.assert_called_with(
                'callback', text='Дождитесь завершения текущего запроса.'
            )
        finally:
            release.set()
            thread.join(3)

    def prepare_voice(self):
        from google.genai import types
        self.message.voice = SimpleNamespace(file_id='voice-id', file_size=8, mime_type='audio/ogg')
        self.app.bot.get_file.return_value = SimpleNamespace(file_size=8, file_path='voice.oga')
        self.app.bot.download_file.return_value = b'OggS-test'
        response = SimpleNamespace(text='Текстовый ответ', candidates=[], usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=40, candidates_token_count=5, total_token_count=45))
        chat = MagicMock()
        chat.send_message.return_value = response
        chat.get_history.return_value = [
            types.Content(role='user', parts=[types.Part.from_bytes(data=b'OggS-test', mime_type='audio/ogg')]),
            types.Content(role='model', parts=[types.Part(text='Текстовый ответ')]),
        ]
        self.app.user_chats[123] = chat
        return chat

    def test_voice_replies_in_text_saves_audio_history_and_records_usage(self):
        from database.models import UsageRecord
        chat = self.prepare_voice()
        with self.sessions() as session:
            crud.add_file_context(session, 123, 'note.txt', 'text/plain', b'note')
        with patch.object(self.app, 'send_rich_response') as send:
            self.app.handle_voice.__wrapped__(self.message)
        kwargs = chat.send_message.call_args.kwargs
        self.assertEqual(kwargs['config'].response_modalities, ['TEXT'])
        self.assertIn('normal user message', kwargs['config'].system_instruction)
        blobs = [part.inline_data for part in kwargs['message'] if part.inline_data]
        self.assertEqual([(blob.mime_type, blob.data) for blob in blobs],
                         [('text/plain', b'note'), ('audio/ogg', b'OggS-test')])
        self.assertEqual(send.call_args.args[2], 'Текстовый ответ')
        self.assertEqual(self.app.user_last_responses[123], 'Текстовый ответ')
        with self.sessions() as session:
            stored = self.app.deserialize_history(crud.get_chat_session(session, 123).history_json)
            self.assertEqual(stored[0].parts[0].inline_data.data, b'OggS-test')
            self.assertEqual(len(crud.get_file_contexts(session, 123)), 0)
            usage = session.query(UsageRecord).one()
            self.assertEqual((usage.operation, usage.total_tokens, usage.success), ('voice', 45, True))

    def test_voice_manual_buffer_survives_reload_and_sends_with_text(self):
        from chat_context import context_contents
        from constants import SEND_MODE_MANUAL
        chat = self.prepare_voice()
        with self.sessions() as session:
            crud.update_user_send_mode(session, 123, SEND_MODE_MANUAL)
        self.app.handle_voice.__wrapped__(self.message)
        chat.send_message.assert_not_called()
        buffer = self.app.get_message_buffer_list(123)
        self.assertEqual((buffer[0]['type'], buffer[0]['mime_type'], buffer[0]['data']),
                         ('voice', 'audio/ogg', b'OggS-test'))
        self.assertEqual(context_contents([], [], buffer)[0].parts[0].inline_data.data, b'OggS-test')
        with self.sessions() as session:
            crud.add_to_buffer(session, 123, 'text', content='Дополнительный вопрос')
        with patch.object(self.app, 'send_rich_response'):
            self.app.handle_send_all.__wrapped__(self.message)
        kwargs = chat.send_message.call_args.kwargs
        self.assertEqual(kwargs['config'].response_modalities, ['TEXT'])
        self.assertEqual(kwargs['message'][0].inline_data.data, b'OggS-test')
        self.assertEqual(kwargs['message'][1], 'Дополнительный вопрос')
        with self.sessions() as session:
            self.assertEqual(len(crud.get_buffer(session, 123)), 0)

    def test_voice_generation_failure_is_counted_and_files_remain(self):
        from database.models import UsageRecord
        chat = self.prepare_voice()
        chat.send_message.side_effect = RuntimeError('API failed')
        with self.sessions() as session:
            crud.add_file_context(session, 123, 'note.txt', 'text/plain', b'note')
        self.app.handle_voice.__wrapped__(self.message)
        with self.sessions() as session:
            self.assertEqual(len(crud.get_file_contexts(session, 123)), 1)
            usage = session.query(UsageRecord).one()
            self.assertFalse(usage.success)
            self.assertIsNone(usage.total_tokens)
        self.assertIn('Не удалось обработать голосовое', self.app.bot.reply_to.call_args.args[1])

    def test_voice_limits_reject_oversized_data_before_gemini(self):
        chat = self.prepare_voice()
        for declared, remote, data in [(1048577, 8, b'a'), (8, 1048577, b'a'), (8, 8, b'a' * 1048577)]:
            with self.subTest(declared=declared, remote=remote):
                self.message.voice.file_size = declared
                self.app.bot.get_file.return_value.file_size = remote
                self.app.bot.download_file.return_value = data
                with patch.object(self.app, 'MAX_FILE_SIZE_MB', 1):
                    self.app.handle_voice.__wrapped__(self.message)
                chat.send_message.assert_not_called()

    def test_image_model_does_not_download_voice_or_clear_pending_audio(self):
        from constants import SEND_MODE_MANUAL
        chat = self.prepare_voice()
        with self.sessions() as session:
            crud.update_user_model(session, 123, IMAGE_MODEL)
            crud.update_user_send_mode(session, 123, SEND_MODE_MANUAL)
            crud.add_to_buffer(session, 123, 'voice', blob_data=b'voice', mime_type='audio/ogg')
        self.app.handle_voice.__wrapped__(self.message)
        self.app.bot.download_file.assert_not_called()
        self.app.handle_send_all.__wrapped__(self.message)
        chat.send_message.assert_not_called()
        with self.sessions() as session:
            self.assertEqual(len(crud.get_buffer(session, 123)), 1)

    def test_unset_access_code_does_not_unlock(self):
        self.message.text = '/unlock_pro None'
        with patch.object(self.app, 'PRO_CODE', None), patch.object(self.app, 'add_to_whitelist') as add:
            self.app.handle_unlock_pro.__wrapped__(self.message)
            add.assert_not_called()


if __name__ == '__main__':
    unittest.main()
