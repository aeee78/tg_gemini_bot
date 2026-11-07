"""Keep Telegram's short-lived typing indicator active during a request."""
import logging
from contextlib import contextmanager
from threading import Event, Thread

logger = logging.getLogger(__name__)


@contextmanager
def typing_action(bot, chat_id, interval=4):
    stopped = Event()

    def send_once():
        try:
            bot.send_chat_action(chat_id, 'typing', timeout=3)
        except Exception as error:
            # A presentation failure must not prevent the actual answer.
            logger.debug('Could not refresh typing (%s)', type(error).__name__)

    def refresh():
        while not stopped.wait(interval):
            send_once()

    send_once()
    worker = Thread(target=refresh, name='telegram-typing', daemon=True)
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        worker.join(timeout=4)
