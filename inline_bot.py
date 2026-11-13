"""Isolated, bounded inline requests; never reads private conversation history."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, BoundedSemaphore
from time import monotonic
import logging
import secrets

from google.genai import types as genai_types
from telebot import types
from telebot.apihelper import ApiTelegramException

from constants import ADMIN_IDS, MAX_MESSAGE_LENGTH
from database import crud, model_catalog
from usage import track_gemini_call
from utils import (
    escape_rich_markdown,
    grounding_sources,
    markdown_to_text,
    source_links_markdown,
    split_long_message,
)

INLINE_MODEL = 'gemini-flash-lite-latest'  # Independent of the admin default.
logger = logging.getLogger(__name__)


def _utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


def _truncate_utf16(text, limit):
    return text.encode('utf-16-le')[:limit * 2].decode('utf-16-le', errors='ignore')


def format_inline_response(prompt, response):
    """Prepare rich Markdown and a bounded plain fallback with grounded links."""
    sources = []
    footer = ''
    all_sources = grounding_sources(response)
    for label, uri in all_sources:
        if _utf16_length(label) > 160:
            label = _truncate_utf16(label, 159) + '…'
        line = f'{len(sources) + 1}. {label}'
        new_footer = footer + '\n' + line if footer else '\n\nИсточники:\n' + line
        if len(sources) >= 10 or _utf16_length(new_footer) > 1024:
            break
        footer = new_footer
        sources.append((line, label, uri))

    rich_sources = []
    for label, uri in all_sources:
        candidate = rich_sources + [(label, uri)]
        if len(source_links_markdown(candidate)) <= MAX_MESSAGE_LENGTH // 2:
            rich_sources = candidate
    rich_footer = source_links_markdown(rich_sources)
    rich_text = escape_rich_markdown(prompt) + '\n\n' + response.text
    note = '\n\n[Ответ сокращён до лимита Telegram.]'
    if len(rich_text) + len(rich_footer) > MAX_MESSAGE_LENGTH:
        limit = MAX_MESSAGE_LENGTH - len(rich_footer) - len(note)
        rich_text = split_long_message(rich_text, max_length=limit)[0] + note
    rich_text += rich_footer

    text = prompt + '\n\n' + markdown_to_text(response.text)
    limit = 4096 - _utf16_length(footer)
    if _utf16_length(text) > limit:
        text = _truncate_utf16(text, limit - _utf16_length(note)).rstrip() + note

    entities = []
    offset = _utf16_length(text + '\n\nИсточники:\n')
    for line, label, uri in sources:
        prefix = len(line) - len(label)
        entities.append(types.MessageEntity(
            'text_link', offset=offset + prefix, length=_utf16_length(label), url=uri,
        ))
        offset += _utf16_length(line + '\n')
    return text + footer, entities, rich_text


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
        markup.add(types.InlineKeyboardButton('Обновить ответ', callback_data='inline:' + token))
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
                                        state='pending', text=None, entities=[], markdown=None)
            results.append(types.InlineQueryResultArticle(
                id='ask_' + token, title='Спросить Gemini',
                description=prompt[:100],
                input_message_content=types.InputTextMessageContent(
                    prompt + '\n\nGemini готовит ответ…',
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

    def edit(self, message_id, text, token=None, entities=None, markdown=None):
        markup = self.keyboard(token) if token else types.InlineKeyboardMarkup()
        if markdown is not None:
            try:
                self.bot.edit_message_text(
                    inline_message_id=message_id,
                    rich_message=types.InputRichMessage(markdown=markdown),
                    reply_markup=markup,
                )
                return
            except Exception as error:
                if (isinstance(error, ApiTelegramException) and error.error_code == 400
                        and 'message is not modified' in error.description.lower()):
                    return
                logger.warning('Could not edit rich inline answer (%s); trying plain text', type(error).__name__)
        try:
            self.bot.edit_message_text(
                text, inline_message_id=message_id, parse_mode=None, entities=entities,
                disable_web_page_preview=True,
                reply_markup=markup,
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
                cached = (job['text'], job['entities'], job['markdown'])
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
            self.edit(message_id, cached[0], entities=cached[1], markdown=cached[2])
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
                    response_modalities=['TEXT'],
                    tools=[genai_types.Tool(url_context=genai_types.UrlContext()),
                           genai_types.Tool(google_search=genai_types.GoogleSearch())],
                    http_options=genai_types.HttpOptions(timeout=45000),
                ),
            )
            if not response.text or not response.text.strip():
                self.edit(message_id, 'Модель не вернула текст. Попробуйте переформулировать запрос.', token)
                return
            text, entities, markdown = format_inline_response(job['prompt'], response)
            with self.lock:
                job['text'], job['entities'], job['markdown'] = text, entities, markdown
            self.edit(message_id, text, entities=entities, markdown=markdown)
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
