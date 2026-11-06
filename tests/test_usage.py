import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from google.genai.types import GenerateContentResponse, GenerateContentResponseUsageMetadata
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import usage
from admin import AdminPanel, token_value
from constants import DEFAULT_MODEL, FLASH_MODEL
from database import usage as usage_queries
from database.db import Base
from database.models import UsageRecord, User


class TestUsage(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        session_patch = patch('usage.SessionLocal', self.sessions)
        session_patch.start()
        self.addCleanup(session_patch.stop)
        self.response = GenerateContentResponse(usage_metadata=GenerateContentResponseUsageMetadata(
            prompt_token_count=100, candidates_token_count=20,
            thoughts_token_count=10, cached_content_token_count=40,
            tool_use_prompt_token_count=5, total_token_count=135,
        ))

    def test_success_records_exact_google_counts_once_without_content(self):
        request = MagicMock(return_value=self.response)
        with patch('usage.perf_counter', side_effect=[10, 12.5]):
            response = usage.track_gemini_call(123, DEFAULT_MODEL, 'chat', request, message='private prompt')
        self.assertIs(response, self.response)
        request.assert_called_once_with(message='private prompt')
        with self.sessions() as session:
            row = session.query(UsageRecord).one()
            self.assertEqual((row.user_id, row.model, row.operation), (123, DEFAULT_MODEL, 'chat'))
            self.assertTrue(row.success)
            self.assertEqual(row.duration_seconds, 2.5)
            self.assertEqual((row.prompt_tokens, row.output_tokens, row.thinking_tokens,
                              row.cached_tokens, row.tool_tokens, row.total_tokens),
                             (100, 20, 10, 40, 5, 135))
            self.assertIsNone(row.error_type)
            self.assertNotIn('private prompt', str(row.__dict__))

    def test_error_keeps_original_exception_and_unknown_tokens(self):
        error = RuntimeError('secret error message must not be stored')
        error.code = 429
        with self.assertRaises(RuntimeError) as raised:
            usage.track_gemini_call(123, FLASH_MODEL, 'photo', MagicMock(side_effect=error))
        self.assertIs(raised.exception, error)
        with self.sessions() as session:
            row = session.query(UsageRecord).one()
            self.assertFalse(row.success)
            self.assertEqual((row.error_type, row.error_code), ('RuntimeError', 429))
            self.assertIsNone(row.total_tokens)
            self.assertIsNone(row.prompt_tokens)
            self.assertNotIn('secret error', str(row.__dict__))

    def test_missing_or_partial_metadata_does_not_turn_into_zero(self):
        usage.track_gemini_call(123, DEFAULT_MODEL, 'chat', lambda: SimpleNamespace())
        response = SimpleNamespace(usage_metadata={'prompt_token_count': 100, 'thoughts_token_count': 0})
        usage.track_gemini_call(123, DEFAULT_MODEL, 'buffer', lambda: response)
        with self.sessions() as session:
            summary = usage_queries.summary(session)
            self.assertEqual(summary['requests'], 2)
            self.assertEqual(summary['prompt_tokens'], 100)
            self.assertEqual(summary['prompt_tokens_known'], 1)
            self.assertIsNone(summary['total_tokens'])
            self.assertEqual(token_value(summary, 'prompt_tokens'), '100 (частично)')
            self.assertEqual(token_value(summary, 'total_tokens'), 'неизвестно')
            self.assertEqual(token_value(summary, 'thinking_tokens'), '0 (частично)')

    def test_database_failure_does_not_break_response_or_mask_api_error(self):
        with patch('usage.SessionLocal', side_effect=RuntimeError('database unavailable')):
            with self.assertLogs('usage', level='ERROR'):
                self.assertIs(usage.track_gemini_call(123, DEFAULT_MODEL, 'chat', lambda: self.response), self.response)
            error = ValueError('original')
            with self.assertLogs('usage', level='ERROR'), self.assertRaises(ValueError) as raised:
                usage.track_gemini_call(123, DEFAULT_MODEL, 'chat', MagicMock(side_effect=error))
            self.assertIs(raised.exception, error)

    def seed(self):
        with self.sessions() as session:
            session.add(User(id=123, first_name='Alice', username='alice'))
            for user_id, model, started_at, success, total in [
                (123, DEFAULT_MODEL, datetime(2026, 11, 5, 20, 59), True, 900),
                (123, FLASH_MODEL, datetime(2026, 11, 5, 21), True, 100),
                (124, FLASH_MODEL, datetime(2026, 11, 6, 10), False, None),
            ]:
                session.add(UsageRecord(user_id=user_id, model=model, operation='chat',
                                        started_at=started_at, success=success,
                                        duration_seconds=2, total_tokens=total))
            session.commit()

    def test_summary_filters_and_paginated_breakdown_preserve_unknown_usage(self):
        self.seed()
        with self.sessions() as session:
            result = usage_queries.summary(session, since=datetime(2026, 11, 5, 21), until=datetime(2026, 11, 6, 12))
            self.assertEqual((result['requests'], result['successes'], result['total_tokens'], result['total_tokens_known']), (2, 1, 100, 1))
            result = usage_queries.summary(session, user_id=123)
            self.assertEqual((result['requests'], result['total_tokens']), (2, 1000))
            models, page, pages = usage_queries.breakdown(session, 'models', page_size=1)
            self.assertEqual((models[0]['group_id'], page, pages), (FLASH_MODEL, 0, 2))
            models, page, pages = usage_queries.breakdown(session, 'models', page=99, page_size=1)
            self.assertEqual((models[0]['group_id'], page, pages), (DEFAULT_MODEL, 1, 2))
            users, _, _ = usage_queries.breakdown(session, 'users')
            self.assertEqual(users[0]['label'], 'Alice @alice')
            self.assertEqual(users[1]['label'], '124')

    def test_admin_period_uses_moscow_midnight_and_user_filter(self):
        self.seed()
        bot = MagicMock()
        panel = AdminPanel(bot, self.sessions)
        message = SimpleNamespace(chat=SimpleNamespace(id=66765326, type='private'), message_id=1)
        with patch('admin.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
            panel.usage(message)
            text = bot.edit_message_text.call_args.args[0]
            self.assertIn('Запросы: 2 · Успешно: 1 · Ошибки: 1', text)
            self.assertIn('Всего: 100 (частично)', text)
            self.assertIn('Без данных об общем расходе: 1', text)
            panel.usage(message, user_id=123)
            text = bot.edit_message_text.call_args.args[0]
            self.assertIn('Запросы: 1 · Успешно: 1 · Ошибки: 0', text)
            self.assertIn('ID 123', text)
            markup = bot.edit_message_text.call_args.kwargs['reply_markup'].to_dict()
            callbacks = [button['callback_data'] for row in markup['inline_keyboard'] for button in row]
            self.assertIn('admin:usage:week:sum:123:0', callbacks)
            self.assertIn('admin:usage:today:sum:123:0', callbacks)

    def test_user_breakdown_pages_and_fits_telegram_message_limit(self):
        with self.sessions() as session:
            for user_id in range(100, 107):
                session.add(User(id=user_id, first_name='A' * 64, last_name='B' * 64, username='C' * 32))
                session.add(UsageRecord(
                    user_id=user_id, model=DEFAULT_MODEL, operation='chat', started_at=datetime(2026, 11, 6),
                    success=True, duration_seconds=1,
                    **{field: 123456789012 for field in usage_queries.TOKEN_COLUMNS},
                ))
            session.commit()
        bot = MagicMock()
        panel = AdminPanel(bot, self.sessions)
        message = SimpleNamespace(chat=SimpleNamespace(id=66765326, type='private'), message_id=1)
        panel.usage(message, period='all', group='users')
        text = bot.edit_message_text.call_args.args[0]
        self.assertIn('Страница 1 из 2', text)
        self.assertLess(len(text), 4096)
        markup = bot.edit_message_text.call_args.kwargs['reply_markup'].to_dict()
        callbacks = [button['callback_data'] for row in markup['inline_keyboard'] for button in row]
        self.assertIn('admin:usage:all:users:0:1', callbacks)
        self.assertIn('admin:usage:all:sum:100:0', callbacks)
        self.assertTrue(all(len(callback.encode()) <= 64 for callback in callbacks))

    def test_empty_admin_and_breakdown_have_no_invented_usage(self):
        bot = MagicMock()
        panel = AdminPanel(bot, self.sessions)
        message = SimpleNamespace(chat=SimpleNamespace(id=66765326, type='private'), message_id=1)
        for group in ('sum', 'models', 'users'):
            panel.usage(message, period='all', group=group)
            text = bot.edit_message_text.call_args.args[0]
            self.assertIn('Запросы: 0', text)
            self.assertIn('Всего: 0', text)
            self.assertLess(len(text), 4096)


if __name__ == '__main__':
    unittest.main()
