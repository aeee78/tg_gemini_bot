import unittest
from threading import Event
from unittest.mock import MagicMock

from chat_activity import typing_action


class TestChatActivity(unittest.TestCase):
    def test_refreshes_during_work_and_stops_after_success(self):
        bot = MagicMock()
        repeated = Event()
        calls = []
        def send(*args, **kwargs):
            calls.append((args, kwargs))
            if len(calls) >= 2:
                repeated.set()
        bot.send_chat_action.side_effect = send
        with typing_action(bot, 123, interval=0.01):
            self.assertTrue(repeated.wait(1))
        count = len(calls)
        Event().wait(0.03)
        self.assertEqual(len(calls), count)
        self.assertGreaterEqual(count, 2)
        self.assertEqual(calls[0], ((123, 'typing'), {'timeout': 3}))

    def test_stops_after_generation_error_and_keeps_original_exception(self):
        bot = MagicMock()
        error = ValueError('generation failed')
        with self.assertRaises(ValueError) as raised:
            with typing_action(bot, 123, interval=0.01):
                raise error
        self.assertIs(raised.exception, error)
        count = bot.send_chat_action.call_count
        Event().wait(0.03)
        self.assertEqual(bot.send_chat_action.call_count, count)

    def test_telegram_failure_does_not_interrupt_work_or_future_refreshes(self):
        bot = MagicMock()
        repeated = Event()
        def send(*args, **kwargs):
            if bot.send_chat_action.call_count >= 2:
                repeated.set()
            raise RuntimeError('Telegram unavailable')
        bot.send_chat_action.side_effect = send
        completed = False
        with typing_action(bot, 123, interval=0.01):
            self.assertTrue(repeated.wait(1))
            completed = True
        self.assertTrue(completed)


if __name__ == '__main__':
    unittest.main()
