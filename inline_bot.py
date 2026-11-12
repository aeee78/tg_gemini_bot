"""Isolated, bounded inline requests; never reads private conversation history."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, BoundedSemaphore
from time import monotonic
import logging
import secrets

from google.genai import types as genai_types
from telebot import types

from constants import ADMIN_IDS, DEFAULT_MODEL
from database import crud, model_catalog
from usage import track_gemini_call
from utils import markdown_to_text, split_plain_text

INLINE_MODEL = DEFAULT_MODEL  # Fixed Flash Lite; independent of the admin default.
logger = logging.getLogger(__name__)


class InlineBot:
    TTL = 900
    MAX_JOBS = 512
    MAX_QUERY = 2000

    def __init__(self, bot, client, sessions, submit=None):
        self.bot, self.client, self.sessions = bot, client, sessions
        self.jobs = OrderedDict()
        self.lock = Lock()
        self.active_users = set()
        self.slots = BoundedSemaphore(2)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='inline') if submit is None else None
        self.submit = submit or self.executor.submit

    def keyboard(self, token):
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('Получить ответ / повторить', callback_data='inline:' + token))
        return markup

    def query(self, query):
        prompt = query.query.strip()
        results = []
        if prompt and len(prompt) <= self.MAX_QUERY:
            with self.lock:
                now = monotonic()
                for token, job in list(self.jobs.items()):
                    if now - job['created'] > self.TTL and job['state'] != 'running':
                        del self.jobs[token]
                while len(self.jobs) >= self.MAX_JOBS:
                    victim = next((key for key, job in self.jobs.items() if job['state'] != 'running'), None)
                    if victim is None:
                        break
                    del self.jobs[victim]
                token = secrets.token_urlsafe(16)
                self.jobs[token] = dict(owner=query.from_user.id, prompt=prompt, created=now,
                                        state='pending', text=None)
            results.append(types.InlineQueryResultArticle(
                id='ask_' + token, title='Спросить Flash Lite',
                description=prompt[:100],
                input_message_content=types.InputTextMessageContent(
                    prompt + '\n\nГотовлю ответ… Если ответ не появляется, нажмите кнопку ниже.',
                ), reply_markup=self.keyboard(token),
            ))
        self.bot.answer_inline_query(query.id, results, cache_time=0, is_personal=True)

    def chosen(self, chosen):
        if chosen.result_id.startswith('ask_') and chosen.inline_message_id:
            self.start(chosen.result_id[4:], chosen.from_user, chosen.inline_message_id)

    def callback(self, call):
        token = call.data.removeprefix('inline:')
        with self.lock:
            job = self.jobs.get(token)
            allowed = bool(job and job['owner'] == call.from_user.id
                           and monotonic() - job['created'] <= self.TTL)
        if not allowed or not call.inline_message_id:
            self.bot.answer_callback_query(call.id, 'Кнопка доступна автору запроса; если она устарела, вызовите бота заново.', show_alert=True)
            return
        self.bot.answer_callback_query(call.id)
        self.start(token, call.from_user, call.inline_message_id)

    def edit(self, message_id, text, token=None):
        try:
            self.bot.edit_message_text(
                text, inline_message_id=message_id, parse_mode=None,
                disable_web_page_preview=True,
                reply_markup=self.keyboard(token) if token else types.InlineKeyboardMarkup(),
            )
        except Exception as error:
            logger.warning('Could not edit inline answer (%s)', type(error).__name__)

    def start(self, token, actor, message_id):
        busy = False
        with self.lock:
            job = self.jobs.get(token)
            if not job or job['owner'] != actor.id or monotonic() - job['created'] > self.TTL:
                return
            if job['text'] is not None:
                cached = job['text']
            else:
                cached = None
                if job['state'] == 'running':
                    return
                if actor.id in self.active_users or not self.slots.acquire(blocking=False):
                    busy = True
                else:
                    job['state'] = 'running'
                    self.active_users.add(actor.id)
        if busy:
            self.edit(message_id, 'Сейчас выполняются другие запросы. Нажмите кнопку чуть позже.', token)
            return
        if cached is not None:
            self.edit(message_id, cached)
            return
        try:
            self.submit(self.generate, token, actor, message_id, job)
        except Exception:
            with self.lock:
                job['state'] = 'pending'
                self.active_users.discard(actor.id)
            self.slots.release()
            self.edit(message_id, 'Не удалось запустить запрос. Попробуйте ещё раз.', token)

    def generate(self, token, actor, message_id, job):
        try:
            with self.sessions() as session:
                user = crud.record_user_activity(session, actor)
                if not model_catalog.can_use_model(session, INLINE_MODEL, user.pro_access,
                                                   is_admin=actor.id in ADMIN_IDS):
                    self.edit(message_id, 'Flash Lite сейчас недоступна для вашего аккаунта.', token)
                    return
            response = track_gemini_call(
                actor.id, INLINE_MODEL, 'inline', self.client.models.generate_content,
                model=INLINE_MODEL, contents=job['prompt'],
                config=genai_types.GenerateContentConfig(
                    system_instruction='Answer the user in their language. Be concise, use plain text, '
                                       'and aim for at most 3000 characters. This is an independent request.',
                    response_modalities=['TEXT'], max_output_tokens=2048,
                    http_options=genai_types.HttpOptions(timeout=45000),
                ),
            )
            if not response.text or not response.text.strip():
                self.edit(message_id, 'Модель не вернула текст. Попробуйте переформулировать запрос.', token)
                return
            text = job['prompt'] + '\n\n' + markdown_to_text(response.text)
            chunks = split_plain_text(text, max_length=3900)
            text = chunks[0] + ('\n\n[Ответ сокращён до лимита Telegram.]' if len(chunks) > 1 else '')
            with self.lock:
                job['text'] = text
            self.edit(message_id, text)
        except Exception as error:
            logger.warning('Inline request failed (%s)', type(error).__name__)
            self.edit(message_id, 'Не удалось получить ответ. Попробуйте ещё раз позже.', token)
        finally:
            with self.lock:
                job['state'] = 'pending' if job['text'] is None else 'done'
                self.active_users.discard(actor.id)
            self.slots.release()


def register_inline_handlers(bot, client, sessions):
    panel = InlineBot(bot, client, sessions)
    bot.register_inline_handler(panel.query, func=lambda query: True)
    bot.register_chosen_inline_handler(panel.chosen, func=lambda chosen: True)
    bot.register_callback_query_handler(panel.callback, func=lambda call: bool(call.data and call.data.startswith('inline:')))
    return panel
