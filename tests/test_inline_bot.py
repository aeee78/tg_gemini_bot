import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from google.genai import types as genai_types
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from telebot.apihelper import ApiTelegramException

from database.db import Base
from database import crud, model_catalog
from database.models import UsageRecord, ChatSession
from inline_bot import InlineBot, INLINE_MODEL, register_inline_handlers
from utils import source_links_markdown


class TestInlineBot(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as session:
            model_catalog.sync_catalog(session, [{
                'name': 'models/gemini-flash-lite-latest',
                'supportedGenerationMethods': ['generateContent'],
            }])
            model_catalog.set_model_access(session, model_catalog.get_model(session, INLINE_MODEL).id, 'public')
        self.patch = patch('usage.SessionLocal', self.sessions)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.bot, self.client = MagicMock(), MagicMock()
        self.client.models.generate_content.return_value = SimpleNamespace(text='Answer', usage_metadata=None)
        self.panel = InlineBot(self.bot, self.client, self.sessions, submit=lambda fn, *args: fn(*args))
        self.actor = SimpleNamespace(id=123, first_name='User')

    def query(self, prompt='Question', actor=None):
        self.panel.query(SimpleNamespace(id='query', query=prompt, from_user=actor or self.actor))
        results = self.bot.answer_inline_query.call_args.args[1]
        return results[0].id[4:] if results else None

    def chosen(self, token, actor=None, message_id='inline-message'):
        self.panel.chosen(SimpleNamespace(result_id='ask_' + token, from_user=actor or self.actor,
                                         inline_message_id=message_id))

    def use_plain_fallback(self):
        def edit(*args, **kwargs):
            if 'rich_message' in kwargs:
                raise RuntimeError('Rich messages unavailable')
        self.bot.edit_message_text.side_effect = edit

    def last_answer(self):
        args, kwargs = self.bot.edit_message_text.call_args
        return kwargs['rich_message'].markdown if 'rich_message' in kwargs else args[0]

    def test_query_never_generates_and_results_are_personal_uncached(self):
        token = self.query()
        self.client.models.generate_content.assert_not_called()
        kwargs = self.bot.answer_inline_query.call_args.kwargs
        self.assertEqual((kwargs['cache_time'], kwargs['is_personal']), (0, True))
        result = self.bot.answer_inline_query.call_args.args[1][0]
        self.assertEqual(result.reply_markup.keyboard[0][0].callback_data, 'inline:' + token)
        for prompt in (' ', 'x' * 2001):
            self.assertIsNone(self.query(prompt))

    def test_selection_uses_fixed_lite_and_isolated_prompt_with_usage(self):
        with self.sessions() as session:
            crud.create_user(session, 123)
            crud.save_chat_session(session, 123, 'PRIVATE HISTORY')
        token = self.query()
        self.chosen(token)
        request = self.client.models.generate_content.call_args.kwargs
        self.assertEqual(request['model'], 'gemini-flash-lite-latest')
        self.assertEqual((request['model'], request['contents']), (INLINE_MODEL, 'Question'))
        self.assertEqual(request['config'].response_modalities, ['TEXT'])
        self.assertEqual(len(request['config'].tools), 2)
        self.assertIsNotNone(request['config'].tools[0].url_context)
        self.assertIsNotNone(request['config'].tools[1].google_search)
        config = request['config'].model_dump(exclude_none=True)
        self.assertNotIn('system_instruction', config)
        self.assertNotIn('max_output_tokens', config)
        self.assertNotIn('PRIVATE', str(request))
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['inline_message_id'], 'inline-message')
        self.assertIn('Answer', self.last_answer())
        with self.sessions() as session:
            self.assertEqual(session.query(UsageRecord).one().operation, 'inline')
            self.assertEqual(crud.get_chat_session(session, 123).history_json, 'PRIVATE HISTORY')
        self.chosen(token, message_id='another-inline-message')
        self.client.models.generate_content.assert_called_once()

    def test_callback_fallback_does_not_require_start_or_feedback(self):
        token = self.query()
        call = SimpleNamespace(id='callback', data='inline:' + token,
                               from_user=self.actor, inline_message_id='inline-message')
        self.panel.callback(call)
        self.client.models.generate_content.assert_called_once()
        self.bot.answer_callback_query.assert_called_once_with('callback')
        with self.sessions() as session:
            self.assertIsNotNone(crud.get_user(session, 123))
            self.assertEqual(session.query(ChatSession).count(), 0)

    def test_forwarded_callback_and_forged_selection_cannot_generate_or_edit(self):
        token = self.query()
        other = SimpleNamespace(id=999)
        self.chosen(token, actor=other)
        self.panel.callback(SimpleNamespace(id='callback', data='inline:' + token,
                                           from_user=other, inline_message_id='inline-message'))
        self.client.models.generate_content.assert_not_called()
        self.bot.edit_message_text.assert_not_called()
        self.assertTrue(self.bot.answer_callback_query.call_args.kwargs['show_alert'])

    def test_disabled_model_prevents_generation(self):
        with self.sessions() as session:
            replacement = model_catalog.get_model(session, 'gemini-3.8-flash')
            model_catalog.set_model_access(session, replacement.id, 'public')
            model_catalog.set_default_model(session, replacement.id)
            model_catalog.set_model_access(session, model_catalog.get_model(session, INLINE_MODEL).id, 'disabled')
        self.chosen(self.query())
        self.client.models.generate_content.assert_not_called()
        self.assertIn('недоступна', self.bot.edit_message_text.call_args.args[0])

    def test_error_is_safe_and_retry_works(self):
        self.client.models.generate_content.side_effect = RuntimeError('SECRET_TOKEN')
        token = self.query()
        self.chosen(token)
        self.assertNotIn('SECRET_TOKEN', self.bot.edit_message_text.call_args.args[0])
        self.assertEqual(self.panel.jobs[token]['state'], 'pending')
        self.client.models.generate_content.side_effect = None
        self.chosen(token)
        self.assertIn('Answer', self.last_answer())

    def test_long_unicode_output_fits_inline_message_limit(self):
        self.use_plain_fallback()
        self.client.models.generate_content.return_value.text = '😀' * 5000
        self.chosen(self.query('Вопрос ' * 200))
        text = self.bot.edit_message_text.call_args.args[0]
        self.assertLessEqual(len(text.encode('utf-16-le')) // 2, 4096)
        self.assertIn('😀', text)
        self.assertIn('сокращён', text)

    def test_grounded_sources_are_linked_at_end_and_reused_without_regeneration(self):
        self.use_plain_fallback()
        self.client.models.generate_content.return_value = genai_types.GenerateContentResponse(
            candidates=[genai_types.Candidate(
                content=genai_types.Content(parts=[genai_types.Part(text='Ответ 😀')]),
                grounding_metadata=genai_types.GroundingMetadata(grounding_chunks=[
                    genai_types.GroundingChunk(web=genai_types.GroundingChunkWeb(
                        title='Погода 🌤', uri='https://example.org/weather',
                    )),
                    genai_types.GroundingChunk(web=genai_types.GroundingChunkWeb(
                        title='Дубликат', uri='https://example.org/weather',
                    )),
                    genai_types.GroundingChunk(),
                    genai_types.GroundingChunk(web=genai_types.GroundingChunkWeb(title='Нет ссылки')),
                    genai_types.GroundingChunk(web=genai_types.GroundingChunkWeb(
                        uri='https://example.net/',
                    )),
                ]),
            )],
        )
        token = self.query('Вопрос 😀 <tag>')
        self.chosen(token)
        args, kwargs = self.bot.edit_message_text.call_args
        text = args[0]
        self.assertEqual(text, 'Вопрос 😀 <tag>\n\nОтвет 😀\n\nИсточники:\n1. Погода 🌤\n2. https://example.net/')
        self.assertIsNone(kwargs['parse_mode'])
        self.assertEqual([entity.url for entity in kwargs['entities']],
                         ['https://example.org/weather', 'https://example.net/'])
        for entity, label in zip(kwargs['entities'], ['Погода 🌤', 'https://example.net/']):
            selected = text.encode('utf-16-le')[entity.offset * 2:(entity.offset + entity.length) * 2]
            self.assertEqual(selected.decode('utf-16-le'), label)
            self.assertEqual(entity.type, 'text_link')
        self.chosen(token, message_id='second-message')
        self.client.models.generate_content.assert_called_once()
        self.assertEqual(self.bot.edit_message_text.call_args.args, args)
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['entities'], kwargs['entities'])

    def test_sources_survive_long_answer_and_urls_are_not_shortened(self):
        self.use_plain_fallback()
        long_url = 'https://example.org/' + 'a' * 6000
        self.client.models.generate_content.return_value = SimpleNamespace(
            text='😀' * 5000, usage_metadata=None,
            candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[
                SimpleNamespace(web=SimpleNamespace(title='Источник 🌤 ' * 50, uri=long_url)),
                SimpleNamespace(web=SimpleNamespace(title='Другой источник', uri='https://example.net/')),
            ]))],
        )
        self.chosen(self.query('Вопрос 😀'))
        text = self.bot.edit_message_text.call_args.args[0]
        entities = self.bot.edit_message_text.call_args.kwargs['entities']
        self.assertLessEqual(len(text.encode('utf-16-le')) // 2, 4096)
        self.assertIn('сокращён', text)
        self.assertTrue(text.endswith('2. Другой источник'))
        self.assertEqual(entities[0].url, long_url)
        self.assertLessEqual(entities[0].length, 160)
        for entity in entities:
            self.assertLessEqual(entity.offset + entity.length, len(text.encode('utf-16-le')) // 2)

    def test_missing_grounding_metadata_does_not_add_sources(self):
        self.use_plain_fallback()
        for candidates in (None, [], [SimpleNamespace(grounding_metadata=None)],
                           [SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[]))]):
            with self.subTest(candidates=candidates):
                self.client.models.generate_content.return_value = SimpleNamespace(
                    text='Answer', usage_metadata=None, candidates=candidates,
                )
                self.chosen(self.query())
                self.assertEqual(self.bot.edit_message_text.call_args.args[0], 'Question\n\nAnswer')
                self.assertEqual(self.bot.edit_message_text.call_args.kwargs['entities'], [])

    def test_many_sources_fit_message_limit(self):
        self.use_plain_fallback()
        self.client.models.generate_content.return_value = SimpleNamespace(
            text='😀' * 5000, usage_metadata=None,
            candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[
                SimpleNamespace(web=SimpleNamespace(title='🌤' * 100, uri=f'https://example.org/{i}'))
                for i in range(100)
            ]))],
        )
        self.chosen(self.query())
        text = self.bot.edit_message_text.call_args.args[0]
        entities = self.bot.edit_message_text.call_args.kwargs['entities']
        self.assertLessEqual(len(text.encode('utf-16-le')) // 2, 4096)
        self.assertGreater(len(entities), 1)
        self.assertLess(len(entities), 100)
        self.assertEqual(entities[-1].offset + entities[-1].length, len(text.encode('utf-16-le')) // 2)

    def test_rich_response_keeps_markdown_and_shared_source_links(self):
        answer = '# Погода\n\n**Температура:** +2 °C\n\n| Город | °C |\n|---|---|\n| СПб | 2 |\n\n```python\nprint(2)\n```'
        self.client.models.generate_content.return_value = SimpleNamespace(
            text=answer, usage_metadata=None,
            candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[
                SimpleNamespace(web=SimpleNamespace(title='Погода [СПб]', uri='https://example.org/weather')),
            ]))],
        )
        token = self.query('Как **погода**?')
        self.chosen(token)
        self.bot.edit_message_text.assert_called_once()
        kwargs = self.bot.edit_message_text.call_args.kwargs
        self.assertEqual(kwargs['inline_message_id'], 'inline-message')
        expected = ('Как \\*\\*погода\\*\\*?\n\n' + answer
                    + source_links_markdown([('Погода [СПб]', 'https://example.org/weather')]))
        self.assertEqual(kwargs['rich_message'].markdown, expected)
        self.assertNotIn('parse_mode', kwargs)
        self.assertNotIn('entities', kwargs)
        self.assertEqual(kwargs['reply_markup'].keyboard, [])
        self.chosen(token, message_id='second-message')
        self.client.models.generate_content.assert_called_once()
        self.assertEqual(self.last_answer(), expected)

    def test_rich_response_keeps_more_than_plain_text_limit(self):
        self.client.models.generate_content.return_value.text = '**' + 'a' * 7000 + '**'
        self.chosen(self.query())
        markdown = self.last_answer()
        self.assertIn('a' * 7000, markdown)
        self.assertNotIn('сокращён', markdown)

    def test_long_rich_response_closes_code_and_keeps_sources(self):
        self.client.models.generate_content.return_value = SimpleNamespace(
            text='```python\n' + 'print(123)\n' * 4000 + '```', usage_metadata=None,
            candidates=[SimpleNamespace(grounding_metadata=SimpleNamespace(grounding_chunks=[
                SimpleNamespace(web=SimpleNamespace(title='Документация', uri='https://example.org/docs')),
            ]))],
        )
        self.chosen(self.query())
        markdown = self.last_answer()
        self.assertLessEqual(len(markdown), 16000)
        self.assertIn('сокращён', markdown)
        self.assertEqual(markdown.count('```'), 2)
        self.assertTrue(markdown.endswith('[Документация](https://example.org/docs)'))

    def test_unchanged_rich_answer_does_not_downgrade_to_plain_text(self):
        self.bot.edit_message_text.side_effect = ApiTelegramException(
            'editMessageText', None,
            {'error_code': 400, 'description': 'Bad Request: message is not modified'},
        )
        self.chosen(self.query())
        self.bot.edit_message_text.assert_called_once()
        self.assertIn('rich_message', self.bot.edit_message_text.call_args.kwargs)

    def test_sdk_serializes_rich_inline_edit_without_text_or_parse_mode(self):
        import json
        from telebot import TeleBot

        token = self.query()
        self.panel.bot = TeleBot('123:TEST', threaded=False)
        self.addCleanup(self.panel.bot.stop_bot)
        with patch('telebot.apihelper._make_request', return_value=True) as request:
            self.chosen(token)
        request.assert_called_once()
        payload = request.call_args.kwargs['params']
        self.assertEqual(payload['inline_message_id'], 'inline-message')
        self.assertEqual(json.loads(payload['rich_message']), {'markdown': 'Question\n\nAnswer'})
        self.assertNotIn('text', payload)
        self.assertNotIn('parse_mode', payload)

    def test_jobs_expire_and_cache_is_bounded(self):
        self.panel.MAX_JOBS = 2
        first = self.query()
        self.query('Second')
        self.query('Third')
        self.assertNotIn(first, self.panel.jobs)
        self.assertEqual(len(self.panel.jobs), 2)
        token = self.query('Expired')
        self.panel.jobs[token]['created'] -= 1000
        self.panel.callback(SimpleNamespace(id='callback', data='inline:' + token,
                                           from_user=self.actor, inline_message_id='message'))
        self.client.models.generate_content.assert_not_called()
        self.assertTrue(self.bot.answer_callback_query.call_args.kwargs['show_alert'])

    def test_parallel_work_is_bounded_and_duplicate_selection_deduplicated(self):
        queued = []
        self.panel.submit = lambda fn, *args: queued.append((fn, args))
        first = self.query()
        self.chosen(first)
        self.chosen(first)
        self.chosen(self.query('Another request'))
        second_actor = SimpleNamespace(id=124)
        self.chosen(self.query(actor=second_actor), actor=second_actor)
        third_actor = SimpleNamespace(id=125)
        self.chosen(self.query(actor=third_actor), actor=third_actor)
        self.assertEqual(len(queued), 2)
        for fn, args in queued:
            fn(*args)
        self.assertEqual(self.panel.active_users, set())

    def test_registers_inline_chosen_and_callback_handlers(self):
        with patch('inline_bot.ThreadPoolExecutor'):
            panel = register_inline_handlers(self.bot, self.client, self.sessions)
        self.bot.register_inline_handler.assert_called_once()
        self.bot.register_chosen_inline_handler.assert_called_once()
        predicate = self.bot.register_callback_query_handler.call_args.kwargs['func']
        self.assertTrue(predicate(SimpleNamespace(data='inline:token')))
        self.assertFalse(predicate(SimpleNamespace(data='model_id_1')))
        self.assertFalse(predicate(SimpleNamespace(data=None)))

    def test_sdk_updates_show_menu_before_starting_generation(self):
        from telebot import TeleBot, types

        bot = TeleBot('123:TEST', threaded=False)
        self.addCleanup(bot.stop_bot)
        panel = register_inline_handlers(bot, self.client, self.sessions)
        self.addCleanup(panel.executor.shutdown, wait=True, cancel_futures=True)
        actor = {'id': 123, 'is_bot': False, 'first_name': 'User'}
        update = types.Update.de_json({
            'update_id': 1,
            'inline_query': {'id': 'query', 'from': actor, 'query': 'Привет', 'offset': ''},
        })
        with patch.object(bot, 'answer_inline_query') as answer:
            bot.process_new_updates([update])
        answer.assert_called_once()
        result = answer.call_args.args[1][0]
        self.assertEqual(result.title, 'Спросить Gemini')
        self.assertEqual(result.description, 'Привет')
        self.assertNotIn('нажмите', result.input_message_content.message_text)
        self.assertEqual(result.reply_markup.keyboard[0][0].text, 'Обновить ответ')
        self.client.models.generate_content.assert_not_called()
        chosen = types.Update.de_json({
            'update_id': 2,
            'chosen_inline_result': {'result_id': result.id, 'from': actor,
                                     'query': 'Привет', 'inline_message_id': 'inline-message'},
        })
        panel.submit = lambda fn, *args: fn(*args)
        with patch.object(bot, 'edit_message_text') as edit:
            bot.process_new_updates([chosen])
        self.client.models.generate_content.assert_called_once()
        edit.assert_called_once()
        self.assertEqual(edit.call_args.kwargs['inline_message_id'], 'inline-message')
        self.assertEqual(edit.call_args.kwargs['rich_message'].markdown, 'Привет\n\nAnswer')
        self.assertEqual(edit.call_args.kwargs['reply_markup'].keyboard, [])
