import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin import AdminPanel, register_admin_handlers
from constants import DEFAULT_MODEL, FLASH_MODEL
from database import model_catalog
from database.db import Base


def google_model(name, label=None):
    return SimpleNamespace(name='models/' + name, display_name=label or name,
                           supported_actions=['generateContent'])


class TestAdminModels(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        self.bot = MagicMock()
        self.client = MagicMock()
        self.panel = AdminPanel(self.bot, self.sessions, model_client=self.client)
        self.actor = SimpleNamespace(id=66765326, first_name='Admin')
        self.message = SimpleNamespace(
            chat=SimpleNamespace(id=self.actor.id, type='private'), message_id=1,
            from_user=self.actor, text='/admin',
        )
        with self.sessions() as session:
            model_catalog.ensure_catalog(session)

    def call(self, data, actor=None, chat_type='private'):
        message = SimpleNamespace(chat=SimpleNamespace(id=self.actor.id, type=chat_type), message_id=1)
        self.panel.callback(SimpleNamespace(
            id='callback', data=data, from_user=actor or self.actor, message=message,
        ))

    def rendered_text(self):
        return self.bot.edit_message_text.call_args.args[0]

    def buttons(self):
        markup = self.bot.edit_message_text.call_args.kwargs['reply_markup'].to_dict()
        return [button for row in markup['inline_keyboard'] for button in row]

    def model_id(self, name):
        with self.sessions() as session:
            return model_catalog.get_model(session, name).id

    def test_home_links_models_and_registration_passes_client(self):
        self.panel.command(self.message)
        markup = self.bot.send_message.call_args.kwargs['reply_markup'].to_dict()
        routes = [button['callback_data'] for row in markup['inline_keyboard'] for button in row]
        self.assertIn('admin:models:0', routes)
        panel = register_admin_handlers(self.bot, self.sessions, model_client=self.client)
        self.assertIs(panel.model_client, self.client)

    def test_unauthorized_model_routes_never_access_db_or_google(self):
        routes = [
            'admin:models:0', 'admin:model:1:0', 'admin:modelrefresh',
            'admin:modelaccess:1:disabled:0', 'admin:modeldefault:1:0',
        ]
        with patch.object(self.panel, 'sessions') as sessions:
            for route in routes:
                self.call(route, actor=SimpleNamespace(id=999))
                self.call(route, chat_type='supergroup')
            sessions.assert_not_called()
        self.client.models.list.assert_not_called()
        self.bot.edit_message_text.assert_not_called()

    def test_refresh_adds_disabled_models_and_preserves_access_and_default(self):
        flash_id = self.model_id(FLASH_MODEL)
        self.call(f'admin:modelaccess:{flash_id}:public:0')
        self.call(f'admin:modeldefault:{flash_id}:0')
        new_name = 'gemini-9.1-flash-preview'
        self.client.models.list.return_value = [google_model(FLASH_MODEL), google_model(new_name)]
        self.call('admin:modelrefresh')
        self.client.models.list.assert_called_once_with()
        self.assertIn('Новых моделей: 1', self.rendered_text())
        with self.sessions() as session:
            self.assertEqual(model_catalog.get_default_model(session), FLASH_MODEL)
            self.assertEqual(model_catalog.get_model(session, FLASH_MODEL).access, 'public')
            self.assertEqual(model_catalog.get_model(session, new_name).access, 'disabled')
            self.assertIsNotNone(model_catalog.get_last_sync(session))
        self.call('admin:models:0')
        self.assertTrue(any('⭐' in button['text'] for button in self.buttons()))

    def test_failed_refresh_keeps_catalog_and_never_displays_provider_error(self):
        def broken_pages():
            yield google_model('gemini-9.1-flash-preview')
            raise RuntimeError('credential=DO_NOT_DISPLAY')
        self.client.models.list.return_value = broken_pages()
        self.call('admin:modelrefresh')
        self.assertIn('Не удалось обновить', self.rendered_text())
        self.assertNotIn('DO_NOT_DISPLAY', self.rendered_text())
        with self.sessions() as session:
            self.assertIsNone(model_catalog.get_model(session, 'gemini-9.1-flash-preview'))
            self.assertIsNone(model_catalog.get_last_sync(session))
            self.assertEqual(model_catalog.get_default_model(session), DEFAULT_MODEL)

    def test_access_and_default_controls_enforce_public_default(self):
        default_id = self.model_id(DEFAULT_MODEL)
        flash_id = self.model_id(FLASH_MODEL)
        self.call(f'admin:modelaccess:{default_id}:disabled:0')
        with self.sessions() as session:
            self.assertEqual(model_catalog.get_model(session, DEFAULT_MODEL).access, 'public')
        self.assertNotIn('Настройка сохранена.', self.rendered_text())
        self.call(f'admin:modeldefault:{flash_id}:0')
        with self.sessions() as session:
            self.assertEqual(model_catalog.get_default_model(session), DEFAULT_MODEL)
        self.call(f'admin:modelaccess:{flash_id}:public:0')
        self.call(f'admin:modeldefault:{flash_id}:0')
        self.call(f'admin:modelaccess:{default_id}:whitelist:0')
        with self.sessions() as session:
            self.assertEqual(model_catalog.get_default_model(session), FLASH_MODEL)
            self.assertEqual(model_catalog.get_model(session, DEFAULT_MODEL).access, 'whitelist')
        self.call(f'admin:modelaccess:{default_id}:disabled:0')
        with self.sessions() as session:
            self.assertEqual(model_catalog.get_model(session, DEFAULT_MODEL).access, 'disabled')

    def test_pagination_long_model_names_and_stale_buttons(self):
        long_name = 'gemini-9.1-flash-' + 'a' * 100
        self.client.models.list.return_value = [google_model(long_name)] + [
            google_model(f'gemini-9.1-flash-preview-{i}') for i in range(12)
        ]
        self.call('admin:modelrefresh')
        self.call('admin:models:1')
        self.assertIn('Страница 2 из 2', self.rendered_text())
        for button in self.buttons():
            self.assertLessEqual(len(button['callback_data'].encode()), 64)
        self.call(f'admin:model:{self.model_id(long_name)}:1')
        self.assertIn(long_name, self.rendered_text())
        for button in self.buttons():
            self.assertLessEqual(len(button['callback_data'].encode()), 64)
        self.call('admin:models:999')
        self.assertIn('Страница 2 из 2', self.rendered_text())
        self.call('admin:model:99999:0')
        self.assertIn('Модель не найдена', self.rendered_text())
        for route in ('admin:modelaccess:1:invalid:0', 'admin:model:99999999999999999999:0'):
            self.call(route)
            self.assertIn('Кнопка устарела', self.rendered_text())

    def test_missing_model_warning_and_no_client_fallback(self):
        self.client.models.list.return_value = [google_model(DEFAULT_MODEL)]
        self.call('admin:modelrefresh')
        self.call(f'admin:model:{self.model_id(FLASH_MODEL)}:0')
        self.assertIn('Нет в последнем каталоге Google', self.rendered_text())
        self.assertIn('Whitelist', self.rendered_text().replace('whitelist', 'Whitelist'))
        self.panel.model_client = None
        self.call('admin:modelrefresh')
        self.assertIn('Обновление каталога сейчас недоступно', self.rendered_text())


if __name__ == '__main__':
    unittest.main()
