import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import telebot

from inline_bot import register_inline_handlers
from inline_dispatch import InlineQueryDispatcher


def query(owner, text='Question', identifier=None):
    return SimpleNamespace(from_user=SimpleNamespace(id=owner), query=text,
                           id=identifier or text)


class TestInlineDispatcher(unittest.TestCase):
    def dispatcher(self, handler, **kwargs):
        dispatcher = InlineQueryDispatcher(handler, **kwargs)
        self.addCleanup(dispatcher.close, wait=True)
        return dispatcher

    def test_inline_answers_while_both_private_message_workers_are_busy(self):
        bot = telebot.TeleBot('123:TEST', threaded=True)
        self.addCleanup(bot.stop_bot)
        release = threading.Event()
        self.addCleanup(release.set)
        started = [threading.Event(), threading.Event()]
        for event in started:
            def block(event=event):
                event.set()
                release.wait(3)
            bot._exec_task(block)
        for event in started:
            self.assertTrue(event.wait(1))
        panel = register_inline_handlers(bot, None, None)
        self.addCleanup(panel.executor.shutdown, wait=True, cancel_futures=True)
        self.addCleanup(panel.dispatcher.close, wait=True)
        answered = threading.Event()
        update = telebot.types.Update.de_json({
            'update_id': 1,
            'inline_query': {'id': 'QUERY', 'from': {'id': 123, 'is_bot': False, 'first_name': 'Test'},
                             'query': 'DNS', 'offset': '', 'chat_type': 'sender'},
        })
        with patch.object(bot, 'answer_inline_query', side_effect=lambda *args, **kwargs: answered.set()) as answer:
            bot.process_new_updates([update])
            self.assertTrue(answered.wait(1), 'Inline acknowledgement waited for private workers')
            answer.assert_called_once()
            self.assertFalse(release.is_set())
        release.set()

    def test_latest_waiting_query_per_user_replaces_stale_typing(self):
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        seen = []

        def handle(item):
            seen.append(item.query)
            if item.query == 'first':
                started.set()
                release.wait(3)
            else:
                done.set()

        dispatcher = self.dispatcher(handle, max_workers=1)
        dispatcher.dispatch([query(1, 'first')])
        self.assertTrue(started.wait(1))
        dispatcher.dispatch([query(1, 'old'), query(1, 'newest')])
        release.set()
        self.assertTrue(done.wait(1))
        dispatcher.close(wait=True)
        self.assertEqual(seen, ['first', 'newest'])

    def test_pending_queue_is_bounded_and_drops_oldest_waiting_user(self):
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        seen = []

        def handle(item):
            seen.append(item.from_user.id)
            if item.from_user.id == 1:
                started.set()
                release.wait(3)
            if item.from_user.id == 4:
                done.set()

        dispatcher = self.dispatcher(handle, max_workers=1, max_pending=2)
        dispatcher.dispatch([query(1)])
        self.assertTrue(started.wait(1))
        dispatcher.dispatch([query(2), query(3), query(4)])
        release.set()
        self.assertTrue(done.wait(1))
        dispatcher.close(wait=True)
        self.assertEqual(seen, [1, 3, 4])

    def test_expired_waiting_query_is_not_answered_after_deadline(self):
        started, release, done = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        now = [0.0]
        seen = []

        def handle(item):
            seen.append(item.from_user.id)
            if item.from_user.id == 1:
                started.set()
                release.wait(3)
            if item.from_user.id == 3:
                done.set()

        dispatcher = self.dispatcher(handle, max_workers=1, clock=lambda: now[0], max_age=8)
        dispatcher.dispatch([query(1)])
        self.assertTrue(started.wait(1))
        dispatcher.dispatch([query(2)])
        now[0] = 9
        dispatcher.dispatch([query(3)])
        release.set()
        self.assertTrue(done.wait(1))
        dispatcher.close(wait=True)
        self.assertEqual(seen, [1, 3])

    def test_sender_is_serialized_while_other_senders_can_proceed(self):
        started, release, other_done, next_done = (threading.Event() for _ in range(4))
        self.addCleanup(release.set)

        def handle(item):
            if item.query == 'blocked':
                started.set()
                release.wait(3)
            elif item.query == 'next':
                next_done.set()
            else:
                other_done.set()

        dispatcher = self.dispatcher(handle)
        dispatcher.dispatch([query(1, 'blocked')])
        self.assertTrue(started.wait(1))
        dispatcher.dispatch([query(1, 'next'), query(2, 'other')])
        self.assertTrue(other_done.wait(1))
        self.assertFalse(next_done.is_set())
        release.set()
        self.assertTrue(next_done.wait(1))

    def test_submission_failure_does_not_crash_polling_and_can_recover(self):
        handled = threading.Event()
        dispatcher = self.dispatcher(lambda item: handled.set(), max_workers=1)
        with patch.object(dispatcher._executor, 'submit', side_effect=RuntimeError('PRIVATE_TOKEN')):
            with self.assertLogs('inline_dispatch', level='WARNING') as logs:
                dispatcher.dispatch([query(1)])
        self.assertNotIn('PRIVATE_TOKEN', '\n'.join(logs.output))
        dispatcher.dispatch([query(1, 'retry')])
        self.assertTrue(handled.wait(1))

    def test_handler_error_does_not_kill_dispatch_and_error_text_is_private(self):
        done = threading.Event()

        def handle(item):
            if item.from_user.id == 1:
                raise RuntimeError('https://provider.invalid/botPRIVATE_TOKEN')
            done.set()

        dispatcher = self.dispatcher(handle, max_workers=1)
        with self.assertLogs('inline_dispatch', level='WARNING') as logs:
            dispatcher.dispatch([query(1), query(2)])
            self.assertTrue(done.wait(1))
            dispatcher.close(wait=True)
        self.assertIn('RuntimeError', '\n'.join(logs.output))
        self.assertNotIn('PRIVATE_TOKEN', '\n'.join(logs.output))

    def test_close_discards_queued_work_and_rejects_new_work(self):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        seen = []

        def handle(item):
            seen.append(item.from_user.id)
            started.set()
            release.wait(3)

        dispatcher = self.dispatcher(handle, max_workers=1)
        dispatcher.dispatch([query(1)])
        self.assertTrue(started.wait(1))
        dispatcher.dispatch([query(2)])
        dispatcher.close()
        dispatcher.dispatch([query(3)])
        release.set()
        dispatcher.close(wait=True)
        self.assertEqual(seen, [1])

    def test_invalid_limits_are_rejected(self):
        for kwargs in ({'max_workers': 0}, {'max_pending': 0}, {'max_age': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                InlineQueryDispatcher(MagicMock(), **kwargs)
