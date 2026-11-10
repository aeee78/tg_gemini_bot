"""Regression checks for private exports, pending inputs and media failures."""
import importlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from google.genai import types
from PIL import Image

from constants import DEFAULT_MODEL, SEND_MODE_IMMEDIATE, SEND_MODE_MANUAL
from database import crud

# Reuse only lifecycle methods; inheriting its TestCase would rerun every test.
fixtures = importlib.import_module(
    f'{__package__}.test_model_access' if __package__ else 'test_model_access'
)


class TestBotRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.TestModelAccess.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        fixtures.TestModelAccess.setUp(self)
        self.app.user_last_responses.clear()
        self.message.chat.type = 'private'

    tearDown = fixtures.TestModelAccess.tearDown

    def chat(self):
        chat = MagicMock()
        chat.get_history.return_value = [
            types.Content(role='user', parts=[types.Part(text='Question')]),
            types.Content(role='model', parts=[types.Part(text='Answer')]),
        ]
        chat.send_message.return_value = types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(
                role='model', parts=[types.Part(text='Answer')],
            ))],
        )
        self.app.user_chats[123] = chat
        return chat

    def manual(self):
        with self.sessions() as session:
            crud.update_user_send_mode(session, 123, SEND_MODE_MANUAL)

    def test_download_requires_matching_owner_and_private_destination(self):
        self.app.user_last_responses.update({123: 'Own answer', 999: 'Other private answer'})
        call = SimpleNamespace(
            id='callback', from_user=SimpleNamespace(id=123), message=self.message,
        )
        bad_data = (
            'get_md_999', 'get_file_999', 'get_md_', 'get_file_bad',
            'get_md_-123', 'get_md_123_extra', 'get_md_' + '9' * 40,
            'get_md_9223372036854775808',
        )
        with patch.object(self.app, 'send_text_as_file') as send:
            for data in bad_data:
                with self.subTest(data=data):
                    call.data = data
                    self.app.handle_get_file.__wrapped__(call)
                    send.assert_not_called()
            call.data = 'get_md_123'
            self.message.chat.id = -100123
            self.message.chat.type = 'supergroup'
            self.app.handle_get_file.__wrapped__(call)
            send.assert_not_called()
            self.message.chat.id = 123
            self.message.chat.type = 'private'
            self.app.handle_get_file.__wrapped__(call)
            send.assert_called_once()
            self.assertEqual(send.call_args.args[:2], (123, 'Own answer'))

    def test_photo_download_failure_never_displays_provider_url_or_token(self):
        fake_token = 'FAKE_TOKEN_FOR_REGRESSION_ONLY'
        self.message.photo = [SimpleNamespace(file_id='photo')]
        self.message.caption = ''
        self.app.bot.get_file.return_value = SimpleNamespace(file_size=10, file_path='photos/p.jpg')
        failure = RuntimeError(f'https://api.telegram.org/file/bot{fake_token}/photos/p.jpg failed')
        self.chat()
        for mode in (SEND_MODE_IMMEDIATE, SEND_MODE_MANUAL):
            with self.subTest(mode=mode), self.sessions() as session:
                crud.update_user_send_mode(session, 123, mode)
                with patch.object(self.app.bot, 'download_file', side_effect=failure):
                    with self.assertRaises(ValueError) as raised:
                        self.app.download_telegram_image('photo')
                    self.assertNotIn(fake_token, str(raised.exception))
                    self.app.handle_photo.__wrapped__(self.message)
                self.assertNotIn(fake_token, self.app.bot.reply_to.call_args.args[1])

    def test_photo_download_checks_metadata_and_actual_byte_limits(self):
        with patch.object(self.app, 'MAX_FILE_SIZE_MB', 1), \
                patch.object(self.app.bot, 'get_file') as get_file, \
                patch.object(self.app.bot, 'download_file') as download:
            limit = 1024 * 1024
            get_file.return_value = SimpleNamespace(file_size=limit + 1, file_path='large.jpg')
            with self.assertRaises(ValueError):
                self.app.download_telegram_image('photo')
            download.assert_not_called()
            get_file.return_value = SimpleNamespace(file_size=None, file_path='unknown.jpg')
            download.return_value = b'x' * (limit + 1)
            with self.assertRaises(ValueError):
                self.app.download_telegram_image('photo')
            download.return_value = b''
            with self.assertRaises(ValueError):
                self.app.download_telegram_image('photo')
            download.return_value = b'valid downloaded bytes'
            self.assertEqual(self.app.download_telegram_image('photo').getvalue(), download.return_value)

    def test_invalid_saved_history_is_not_silently_replaced(self):
        for payload in ('{not json', 'null', '{"role":"user"}', '["invalid content"]'):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.app.deserialize_history(payload)
        damaged = '{not json'
        with self.sessions() as session:
            crud.save_chat_session(session, 123, damaged)
            crud.update_user_model(session, 123, 'retired-model')
        with self.assertRaises(ValueError):
            self.app.get_active_chat(123, DEFAULT_MODEL)
        self.app.client.chats.create.assert_not_called()
        self.assertNotIn(123, self.app.user_chats)
        with self.sessions() as session:
            user = crud.get_user(session, 123)
            with self.assertRaises(ValueError):
                self.app.ensure_user_model(session, user)
            self.assertEqual(user.current_model, 'retired-model')
            self.assertEqual(crud.get_chat_session(session, 123).history_json, damaged)

    def test_changing_send_mode_preserves_all_buffered_inputs(self):
        with self.sessions() as session:
            crud.add_to_buffer(session, 123, 'text', content='Unsent question')
            crud.add_to_buffer(session, 123, 'document', blob_data=b'file',
                               mime_type='text/plain', filename='file.txt')
        for expected in (SEND_MODE_MANUAL, SEND_MODE_IMMEDIATE):
            self.app.handle_send_mode.__wrapped__(self.message)
            with self.sessions() as session:
                self.assertEqual(crud.get_user(session, 123).send_mode, expected)
                buffer = crud.get_buffer(session, 123)
                self.assertEqual(len(buffer), 2)
                self.assertEqual(buffer[0].content, 'Unsent question')
                self.assertEqual(buffer[1].blob_data, b'file')

    def test_failed_durable_history_save_preserves_pending_files_and_buffer(self):
        self.chat()
        with self.sessions() as session:
            crud.save_chat_session(session, 123, '[]')
            crud.add_file_context(session, 123, 'file.txt', 'text/plain', b'file')
            crud.add_to_buffer(session, 123, 'text', content='Unsent')
        failed_session = self.sessions()
        with patch.object(failed_session, 'commit', side_effect=RuntimeError('Disk write failed')), \
                patch.object(self.app, 'SessionLocal', return_value=failed_session):
            with self.assertRaises(RuntimeError):
                self.app.save_active_chat(123, clear_files=True, clear_buffer=True)
        with self.sessions() as session:
            self.assertEqual(crud.get_chat_session(session, 123).history_json, '[]')
            self.assertEqual(len(crud.get_file_contexts(session, 123)), 1)
            self.assertEqual(len(crud.get_buffer(session, 123)), 1)

    def test_manual_document_is_stored_once_in_buffer(self):
        self.manual()
        self.message.document = SimpleNamespace(
            mime_type='text/plain', file_id='document', file_name='file.txt', file_size=3,
        )
        self.message.caption = 'Read this'
        self.app.bot.get_file.return_value = SimpleNamespace(file_size=3, file_path='documents/file.txt')
        self.app.bot.download_file.return_value = b'abc'
        self.app.handle_document.__wrapped__(self.message)
        with self.sessions() as session:
            self.assertEqual(crud.get_file_contexts(session, 123), [])
            buffered = crud.get_buffer(session, 123)
            self.assertEqual(len(buffered), 1)
            self.assertEqual(buffered[0].item_type, 'document')
            self.assertEqual(buffered[0].blob_data, b'abc')
            self.assertEqual(buffered[0].content, 'Read this')

    def test_photo_includes_pending_document_and_consumes_it_after_saving(self):
        chat = self.chat()
        with self.sessions() as session:
            crud.add_file_context(session, 123, 'note.txt', 'text/plain', b'Pending document')
        self.message.photo = [SimpleNamespace(file_id='photo')]
        self.message.caption = 'Compare the image with my document'
        stream = io.BytesIO()
        Image.new('RGB', (1, 1)).save(stream, format='PNG')
        stream.seek(0)
        with patch.object(self.app, 'download_telegram_image', return_value=stream), \
                patch.object(self.app, 'send_rich_response'):
            self.app.handle_photo.__wrapped__(self.message)
        chat.send_message.assert_called_once()
        parts = chat.send_message.call_args.kwargs['message']
        self.assertTrue(any(getattr(getattr(part, 'inline_data', None), 'data', None) == b'Pending document'
                            for part in parts))
        with self.sessions() as session:
            self.assertEqual(crud.get_file_contexts(session, 123), [])
            self.assertIsNotNone(crud.get_chat_session(session, 123))

    def test_manual_send_includes_documents_waiting_before_mode_change(self):
        chat = self.chat()
        with self.sessions() as session:
            crud.add_file_context(session, 123, 'note.txt', 'text/plain', b'Pending document')
            crud.update_user_send_mode(session, 123, SEND_MODE_MANUAL)
            crud.add_to_buffer(session, 123, 'text', content='Summarize my document')
        with patch.object(self.app, 'send_rich_response'):
            self.app.handle_send_all.__wrapped__(self.message)
        chat.send_message.assert_called_once()
        parts = chat.send_message.call_args.kwargs['message']
        self.assertTrue(any(getattr(getattr(part, 'inline_data', None), 'data', None) == b'Pending document'
                            for part in parts))
        with self.sessions() as session:
            self.assertEqual(crud.get_file_contexts(session, 123), [])
            self.assertEqual(crud.get_buffer(session, 123), [])
            self.assertIsNotNone(crud.get_chat_session(session, 123))

    def test_empty_manual_send_preserves_buffer_without_request(self):
        chat = self.chat()
        self.manual()
        with self.sessions() as session:
            crud.add_to_buffer(session, 123, 'text', content='')
        self.app.handle_send_all.__wrapped__(self.message)
        chat.send_message.assert_not_called()
        with self.sessions() as session:
            self.assertEqual(len(crud.get_buffer(session, 123)), 1)


if __name__ == '__main__':
    unittest.main()
