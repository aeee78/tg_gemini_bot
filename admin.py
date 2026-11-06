"""Private Telegram admin panel; independent of bot startup and Gemini."""
from datetime import timezone
from zoneinfo import ZoneInfo

from telebot import types
from telebot.apihelper import ApiTelegramException

from constants import get_model_alias
from database import crud

ADMIN_IDS = frozenset({66765326})
PAGE_SIZE = 8
DISPLAY_TIMEZONE = ZoneInfo('Europe/Moscow')


def format_date(value):
    if value is None:
        return 'неизвестно'
    return value.replace(tzinfo=timezone.utc).astimezone(DISPLAY_TIMEZONE).strftime('%d.%m.%Y %H:%M')


def user_label(user):
    name = ' '.join(filter(None, [user.first_name, user.last_name])) or str(user.id)
    username = f' @{user.username}' if user.username else ''
    return f'{name}{username}'


def keyboard(*rows):
    markup = types.InlineKeyboardMarkup()
    for row in rows:
        markup.row(*(types.InlineKeyboardButton(text, callback_data=data) for text, data in row))
    return markup


class AdminPanel:
    def __init__(self, bot, session_factory):
        self.bot = bot
        self.sessions = session_factory

    def allowed(self, actor, chat):
        return (actor is not None and actor.id in ADMIN_IDS
                and chat.type == 'private' and chat.id == actor.id)

    def show(self, message, text, markup, edit=False):
        if edit:
            try:
                self.bot.edit_message_text(
                    text, chat_id=message.chat.id, message_id=message.message_id,
                    reply_markup=markup, parse_mode=None,
                )
            except ApiTelegramException as error:
                if 'message is not modified' not in error.description.lower():
                    raise
        else:
            self.bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode=None)

    def home(self, message, edit=False):
        self.show(message, 'Админка\nВыбери раздел:', keyboard(
            [('👥 Пользователи', 'admin:users:all:0')],
            [('🔑 Белый список', 'admin:users:pro:0')],
            [('🔎 Найти пользователя', 'admin:search')],
            [('📊 Статистика', 'admin:stats')],
        ), edit)

    def users(self, message, scope='all', page=0, edit=True):
        with self.sessions() as session:
            total, users = crud.get_admin_users(session, scope == 'pro', page * PAGE_SIZE, PAGE_SIZE)
            pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            page = min(page, pages - 1)
            if total and not users:
                _, users = crud.get_admin_users(session, scope == 'pro', page * PAGE_SIZE, PAGE_SIZE)
            rows = [[(
                f'{"🔑" if user.pro_access else "👤"} {user_label(user)}'[:64],
                f'admin:user:{user.id}:{scope}:{page}',
            )] for user in users]
        navigation = []
        if page:
            navigation.append(('←', f'admin:users:{scope}:{page - 1}'))
        if page + 1 < pages:
            navigation.append(('→', f'admin:users:{scope}:{page + 1}'))
        if navigation:
            rows.append(navigation)
        rows.append([('В меню', 'admin:home')])
        title = 'Белый список' if scope == 'pro' else 'Пользователи'
        self.show(message, f'{title}: {total}\nСтраница {page + 1} из {pages}', keyboard(*rows), edit)

    def card(self, message, user_id, scope='all', page=0, edit=True):
        with self.sessions() as session:
            user = crud.get_user(session, user_id)
            back = [('← К списку', f'admin:users:{scope}:{page}')]
            if user is None:
                self.show(message, 'Пользователь не найден.', keyboard(back), edit)
                return
            text = (
                f'{user_label(user)}\nID: {user.id}\n'
                f'Доступ к закрытым моделям: {"есть" if user.pro_access else "нет"}\n'
                f'Регистрация: {format_date(user.registered_at)}\n'
                f'Последняя активность: {format_date(user.last_active_at)}\n'
                f'Время: Москва\n'
                f'Модель: {get_model_alias(user.current_model)}\n'
                f'Режим отправки: {user.send_mode}\n'
                f'Поиск Google: {"включён" if user.search_enabled else "выключен"}\n'
                f'Язык Telegram: {user.language_code or "неизвестно"}'
            )
            action = (
                ('Отозвать доступ', f'admin:confirm:{user_id}:{scope}:{page}')
                if user.pro_access else
                ('Выдать доступ', f'admin:set:{user_id}:1:{scope}:{page}')
            )
        self.show(message, text, keyboard([action], back, [('В меню', 'admin:home')]), edit)

    def search(self, message, query):
        with self.sessions() as session:
            users = crud.find_admin_users(session, query)
            if len(users) == 1:
                self.card(message, users[0].id, edit=False)
                return
            rows = [[(user_label(user)[:64], f'admin:user:{user.id}:all:0')] for user in users]
        rows.append([('В меню', 'admin:home')])
        self.show(message, 'Результаты поиска:' if users else 'Пользователь не найден.', keyboard(*rows))

    def stats(self, message):
        with self.sessions() as session:
            stats = crud.get_admin_statistics(session)
        lines = [
            'Статистика', f'Всего пользователей: {stats["total"]}',
            f'С доступом: {stats["pro"]}',
            f'Активны за сутки: {stats["day"]}',
            f'Активны за неделю: {stats["week"]}',
            f'Активны за 30 дней: {stats["month"]}',
            '', 'Выбранные модели:',
        ]
        lines.extend(f'{get_model_alias(model, model)}: {count}' for model, count in stats['models'])
        lines.extend(['', 'Активность считается по обращениям после начала её учёта.'])
        self.show(message, '\n'.join(lines), keyboard(
            [('Обновить', 'admin:stats')], [('В меню', 'admin:home')],
        ), edit=True)

    def command(self, message):
        if not self.allowed(message.from_user, message.chat):
            return
        with self.sessions() as session:
            crud.record_user_activity(session, message.from_user)
        parts = message.text.split(maxsplit=1)
        if len(parts) == 2:
            self.search(message, parts[1].strip())
        else:
            self.home(message)

    def callback(self, call):
        if call.message is None or not self.allowed(call.from_user, call.message.chat):
            self.bot.answer_callback_query(call.id, 'Нет доступа.', show_alert=True)
            return
        self.bot.answer_callback_query(call.id)
        with self.sessions() as session:
            crud.record_user_activity(session, call.from_user)
        parts = call.data.split(':')
        action = parts[1] if len(parts) > 1 else ''
        if parts == ['admin', 'home']:
            self.home(call.message, edit=True)
        elif parts == ['admin', 'search']:
            self.show(call.message, 'Для поиска отправь:\n/admin ID\nили\n/admin @username',
                      keyboard([('В меню', 'admin:home')]), edit=True)
        elif parts == ['admin', 'stats']:
            self.stats(call.message)
        elif action == 'users' and len(parts) == 4 and parts[2] in ('all', 'pro') and parts[3].isdigit():
            self.users(call.message, parts[2], int(parts[3]))
        elif action in ('user', 'confirm') and len(parts) == 5 and parts[2].isdigit() and parts[3] in ('all', 'pro') and parts[4].isdigit():
            user_id, scope, page = int(parts[2]), parts[3], int(parts[4])
            if action == 'user':
                self.card(call.message, user_id, scope, page)
            else:
                self.show(call.message, f'Отозвать доступ у пользователя {user_id}?', keyboard(
                    [('Да, отозвать', f'admin:set:{user_id}:0:{scope}:{page}')],
                    [('Отмена', f'admin:user:{user_id}:{scope}:{page}')],
                ), edit=True)
        elif action == 'set' and len(parts) == 6 and parts[2].isdigit() and parts[3] in ('0', '1') and parts[4] in ('all', 'pro') and parts[5].isdigit():
            user_id, enabled, scope, page = int(parts[2]), parts[3] == '1', parts[4], int(parts[5])
            with self.sessions() as session:
                if crud.get_user(session, user_id) is not None:
                    crud.set_user_pro_access(session, user_id, enabled)
            self.card(call.message, user_id, scope, page)
        else:
            self.show(call.message, 'Кнопка устарела. Открой /admin заново.',
                      keyboard([('В меню', 'admin:home')]), edit=True)


def register_admin_handlers(bot, session_factory):
    panel = AdminPanel(bot, session_factory)
    bot.register_message_handler(panel.command, commands=['admin'])
    bot.register_callback_query_handler(panel.callback, func=lambda call: bool(call.data and call.data.startswith('admin:')))
    return panel
