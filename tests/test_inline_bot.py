import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database import crud, model_catalog
from database.models import UsageRecord, ChatSession
from inline_bot import InlineBot, INLINE_MODEL, register_inline_handlers


class TestInlineBot(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
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
        self.assertEqual((request['model'], request['contents']), (INLINE_MODEL, 'Question'))
        self.assertEqual(request['config'].response_modalities, ['TEXT'])
        self.assertNotIn('PRIVATE', str(request))
        self.assertEqual(self.bot.edit_message_text.call_args.kwargs['inline_message_id'], 'inline-message')
        self.assertIn('Answer', self.bot.edit_message_text.call_args.args[0])
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
        self.assertIn('Answer', self.bot.edit_message_text.call_args.args[0])

    def test_long_unicode_output_fits_inline_message_limit(self):
        self.client.models.generate_content.return_value.text = '😀' * 5000
        self.chosen(self.query('Вопрос ' * 200))
        text = self.bot.edit_message_text.call_args.args[0]
        self.assertLessEqual(len(text.encode('utf-16-le')) // 2, 4096)
        self.assertIn('😀', text)
        self.assertIn('сокращён', text)

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
        self.assertEqual(result.title, 'Спросить Flash Lite')
        self.assertEqual(result.description, 'Привет')
        self.client.models.generate_content.assert_not_called()
        chosen = types.Update.de_json({
            'update_id': 2,
            'chosen_inline_result': {'result_id': result.id, 'from': actor,
                                     'query': 'Привет', 'inline_message_id': 'inline-message'},
        })
        with patch.object(panel, 'start') as start:
            bot.process_new_updates([chosen])
        start.assert_called_once()
        self.assertEqual(start.call_args.args[0], result.id.removeprefix('ask_'))
        self.assertEqual(start.call_args.args[1].id, 123)
        self.assertEqual(start.call_args.args[2], 'inline-message')
