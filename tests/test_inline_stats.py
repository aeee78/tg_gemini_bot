import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin import AdminPanel, USAGE_PAGE_SIZE
from constants import DEFAULT_MODEL
from database import usage
from database.db import Base
from database.models import UsageRecord, User


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
ADMIN_ID = 66765326


class TestInlineStatistics(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.bot = MagicMock()
        self.panel = AdminPanel(self.bot, self.sessions)
        self.actor = SimpleNamespace(id=ADMIN_ID, first_name='Admin')
        self.message = SimpleNamespace(chat=SimpleNamespace(id=ADMIN_ID, type='private'), message_id=1)

    def record(self, session, user_id, started_at, *, operation='inline', success=True,
               tokens=100, duration=2, prompt=None, output=None):
        session.add(UsageRecord(
            user_id=user_id, model=DEFAULT_MODEL, operation=operation,
            started_at=started_at, success=success, duration_seconds=duration,
            total_tokens=tokens, prompt_tokens=prompt, output_tokens=output,
        ))

    def seed(self):
        with self.sessions() as session:
            session.add(User(id=101, first_name='<Alice>', username='alice'))
            session.add(User(id=103, first_name='Chat only'))
            self.record(session, 103, datetime(2026, 10, 1), operation='chat', tokens=99999)
            self.record(session, 101, datetime(2026, 11, 12, 20, 59), tokens=900)
            self.record(session, 101, datetime(2026, 11, 12, 21), tokens=120, prompt=100, output=20)
            self.record(session, 101, datetime(2026, 11, 13, 9), success=False, tokens=None, duration=4)
            self.record(session, 102, datetime(2026, 11, 13, 10), tokens=230,
                        prompt=200, output=30, duration=6)
            self.record(session, 101, datetime(2026, 11, 13, 11), operation='chat', tokens=8888)
            self.record(session, 104, datetime(2026, 11, 13, 12, 1), tokens=7777)
            session.commit()

    def call(self, data, actor=None, message=None):
        call = SimpleNamespace(id='callback', data=data, from_user=actor or self.actor,
                               message=message or self.message)
        with patch('admin.datetime') as clock:
            clock.now.return_value = NOW
            self.panel.callback(call)
        return self.bot.edit_message_text.call_args.args[0] if self.bot.edit_message_text.called else ''

    def buttons(self):
        markup = self.bot.edit_message_text.call_args.kwargs['reply_markup'].to_dict()
        return [button for row in markup['inline_keyboard'] for button in row]

    def routes(self):
        return [button['callback_data'] for button in self.buttons()]

    def test_query_filters_operation_before_aggregating_counts_tokens_and_users(self):
        self.seed()
        since, until = datetime(2026, 11, 12, 21), NOW.replace(tzinfo=None)
        with self.sessions() as session:
            result = usage.summary(session, since, until, operation='inline')
            self.assertEqual((result['requests'], result['successes'], result['unique_users']), (3, 2, 2))
            self.assertEqual((result['total_tokens'], result['total_tokens_known']), (350, 2))
            self.assertEqual((result['prompt_tokens'], result['output_tokens']), (300, 50))
            self.assertEqual(result['duration'], 4)
            self.assertEqual(result['first_recorded_at'], datetime(2026, 11, 12, 20, 59))
            detail = usage.summary(session, since, until, user_id=101, operation='inline')
            self.assertEqual((detail['requests'], detail['total_tokens'], detail['unique_users']), (2, 120, 1))
            all_operations = usage.summary(session, since, until)
            self.assertEqual((all_operations['requests'], all_operations['total_tokens']), (4, 9238))
            self.assertEqual(all_operations['first_recorded_at'], datetime(2026, 10, 1))

    def test_filtered_breakdown_counts_only_inline_users_and_keeps_unknown_profiles(self):
        self.seed()
        with self.sessions() as session:
            results, page, pages = usage.breakdown(
                session, 'users', until=NOW.replace(tzinfo=None), page_size=1, operation='inline',
            )
            self.assertEqual((page, pages, results[0]['group_id'], results[0]['requests']), (0, 2, 101, 3))
            self.assertEqual(results[0]['label'], '<Alice> @alice')
            results, page, pages = usage.breakdown(
                session, 'users', until=NOW.replace(tzinfo=None), page=999, page_size=1, operation='inline',
            )
            self.assertEqual((page, pages, results[0]['group_id'], results[0]['label']), (1, 2, 102, '102'))

    def test_general_statistics_links_inline_and_summary_shows_real_metrics(self):
        self.seed()
        self.call('admin:stats')
        self.assertIn('admin:inline:today:sum:0:0', self.routes())
        text = self.call('admin:inline:today:sum:0:0')
        self.assertIn('Inline-статистика', text)
        self.assertIn('Уникальные пользователи: 2', text)
        self.assertIn('Запросы: 3 · Успешно: 2 · Ошибки: 1', text)
        self.assertIn('Вход: 300 (частично)', text)
        self.assertIn('Ответ: 50 (частично)', text)
        self.assertIn('Всего: 350 (частично)', text)
        self.assertIn('Без данных об общем расходе: 1', text)
        self.assertIn('Среднее время API: 4.00 с', text)
        self.assertIn('Учёт inline с: 12.11.2026 23:59', text)
        self.assertIn('admin:stats', self.routes())
        self.assertIn('admin:inline:today:users:0:0', self.routes())
        for period in ('today', 'week', 'month', 'all'):
            self.assertIn(f'admin:inline:{period}:sum:0:0', self.routes())
        self.assertIsNone(self.bot.edit_message_text.call_args.kwargs['parse_mode'])

    def test_periods_start_at_moscow_midnight_and_exclude_future_records(self):
        rows = [
            (101, datetime(2026, 11, 12, 21)),
            (101, datetime(2026, 11, 12, 20, 59)),
            (102, datetime(2026, 11, 6, 21)),
            (103, datetime(2026, 11, 6, 20, 59)),
            (104, datetime(2026, 10, 14, 21)),
            (105, datetime(2026, 10, 14, 20, 59)),
            (106, NOW.replace(tzinfo=None)),
        ]
        with self.sessions() as session:
            for user, started in rows:
                self.record(session, user, started)
            self.record(session, 999, datetime(2026, 11, 13, 10), operation='photo')
            session.commit()
        for period, requests, users in (('today', 1, 1), ('week', 3, 2), ('month', 5, 4), ('all', 6, 5)):
            with self.subTest(period=period):
                text = self.call(f'admin:inline:{period}:sum:0:0')
                self.assertIn(f'Запросы: {requests} ·', text)
                self.assertIn(f'Уникальные пользователи: {users}', text)

    def test_drilldown_retains_inline_filter_period_and_return_page(self):
        with self.sessions() as session:
            for user_id in range(100, 100 + USAGE_PAGE_SIZE + 2):
                self.record(session, user_id, datetime(2026, 11, 13, 8))
            self.record(session, 105, datetime(2026, 11, 13, 9), operation='chat', tokens=99999)
            self.record(session, 888, datetime(2026, 11, 13, 9), operation='chat')
            session.commit()
        text = self.call('admin:inline:week:users:0:1')
        self.assertIn('Страница 2 из 2', text)
        self.assertIn('admin:inline:week:sum:105:1', self.routes())
        text = self.call('admin:inline:week:sum:105:1')
        self.assertIn('ID 105', text)
        self.assertIn('Запросы: 1 ·', text)
        self.assertIn('Всего: 100', text)
        self.assertIn('admin:inline:week:users:0:1', self.routes())
        self.assertIn('admin:inline:week:sum:105:1', self.routes())
        self.assertIn('admin:inline:month:sum:105:0', self.routes())
        text = self.call('admin:inline:week:users:0:1')
        self.assertIn('Страница 2 из 2', text)
        text = self.call('admin:inline:week:users:0:999')
        self.assertIn('Страница 2 из 2', text)

    def test_empty_inline_data_never_borrows_normal_usage(self):
        with self.sessions() as session:
            self.record(session, 101, datetime(2026, 11, 13, 8), operation='chat')
            session.commit()
        for group in ('sum', 'users'):
            text = self.call(f'admin:inline:all:{group}:0:0')
            self.assertIn('Уникальные пользователи: 0', text)
            self.assertIn('Запросы: 0 ·', text)
            self.assertIn('Всего: 0', text)
            self.assertIn('Среднее время API: —', text)
            self.assertIn('Учёт inline с: первого inline-запроса', text)
        text = self.call('admin:inline:all:sum:101:0')
        self.assertIn('Запросы: 0 ·', text)

    def test_inline_routes_require_admin_identity_and_private_chat(self):
        for route in ('admin:inline:today:sum:0:0', 'admin:inline:all:users:0:0',
                      'admin:inline:week:sum:101:1'):
            for actor, chat in ((SimpleNamespace(id=999), self.message.chat),
                                (self.actor, SimpleNamespace(id=ADMIN_ID, type='group')),
                                (self.actor, SimpleNamespace(id=999, type='private'))):
                with self.subTest(route=route, actor=actor, chat=chat):
                    with patch.object(self.panel, 'sessions') as sessions:
                        self.call(route, actor=actor, message=SimpleNamespace(chat=chat))
                        sessions.assert_not_called()
        self.bot.edit_message_text.assert_not_called()

    def test_invalid_inline_routes_do_not_run_statistics(self):
        routes = (
            'admin:inline:yesterday:sum:0:0', 'admin:inline:today:models:0:0',
            'admin:inline:all:sum:-1:0', 'admin:inline:all:sum:9223372036854775808:0',
            'admin:inline:all:sum:0:1000000000', 'admin:inline:all:sum:0:-1',
            'admin:inline:all:sum:١٠١:0',
        )
        with patch.object(self.panel, 'usage') as render:
            for route in routes:
                text = self.call(route)
                self.assertIn('Кнопка устарела', text)
            render.assert_not_called()

    def test_inline_pages_and_routes_fit_telegram_limits(self):
        with self.sessions() as session:
            for user_id in range(100, 107):
                session.add(User(id=user_id, first_name='A' * 64, last_name='B' * 64, username='C' * 32))
                self.record(session, user_id, datetime(2026, 11, 13, 8), tokens=123456789012)
            session.commit()
        text = self.call('admin:inline:all:users:0:0')
        self.assertLessEqual(len(text.encode('utf-16-le')) // 2, 4096)
        self.assertTrue(all(len(route.encode()) <= 64 for route in self.routes()))
        text = self.call('admin:inline:month:sum:9223372036854775807:999999999')
        self.assertLessEqual(len(text.encode('utf-16-le')) // 2, 4096)
        self.assertTrue(all(len(route.encode()) <= 64 for route in self.routes()))


if __name__ == '__main__':
    unittest.main()
