"""Private Telegram admin panel; independent of bot startup and Gemini."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telebot import types
from telebot.apihelper import ApiTelegramException

from constants import get_model_alias
from database import crud
from database import model_catalog
from database import usage as usage_queries

ADMIN_IDS = frozenset({66765326})
PAGE_SIZE = 8
USAGE_PAGE_SIZE = 5
DISPLAY_TIMEZONE = ZoneInfo('Europe/Moscow')
MODEL_ACCESS_LABELS = {
    'public': '🌐 Доступна всем',
    'whitelist': '🔑 Только whitelist',
    'disabled': '🚫 Отключена',
}


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


def token_value(data, name):
    requests = data['requests']
    known = data[name + '_known']
    if not requests:
        return '0'
    if not known:
        return 'неизвестно'
    value = f"{data[name]:,}".replace(',', ' ')
    return value + (' (частично)' if known < requests else '')


def usage_lines(data, compact=False):
    requests = data['requests']
    successes = data['successes'] or 0
    duration = f"{data['duration']:.2f} с" if requests else '—'
    lines = [f'Запросы: {requests} · Успешно: {successes} · Ошибки: {requests - successes}']
    fields = [('prompt_tokens', 'Вход'), ('output_tokens', 'Ответ'), ('thinking_tokens', 'Thinking'),
              ('cached_tokens', 'Из кеша'), ('tool_tokens', 'Вход инструментов'), ('total_tokens', 'Всего')]
    if compact:
        lines.append(' · '.join(f'{label}: {token_value(data, name)}' for name, label in fields))
    else:
        lines.extend(f'{label}: {token_value(data, name)}' for name, label in fields)
        unknown = requests - data['total_tokens_known']
        if unknown:
            lines.append(f'Без данных об общем расходе: {unknown} запросов')
    lines.append(f'Среднее время API: {duration}')
    return lines


class AdminPanel:
    def __init__(self, bot, session_factory, model_client=None):
        self.bot = bot
        self.sessions = session_factory
        self.model_client = model_client

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
            [('🤖 Модели', 'admin:models:0')],
            [('🔎 Найти пользователя', 'admin:search')],
            [('📊 Статистика', 'admin:stats')],
            [('📈 Расход', 'admin:usage:today:sum:0:0')],
        ), edit)

    def models(self, message, page=0, notice=None):
        with self.sessions() as session:
            models = model_catalog.list_models(session)
            default = model_catalog.get_default_model(session)
            last_sync = model_catalog.get_last_sync(session)
            pages = max(1, (len(models) + PAGE_SIZE - 1) // PAGE_SIZE)
            page = min(page, pages - 1)
            rows = []
            for model in models[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]:
                status = {'public': '🌐', 'whitelist': '🔑', 'disabled': '🚫'}[model.access]
                marker = '⭐ ' if model.name == default else ''
                missing = ' ⚠️' if not model.available else ''
                label = f'{marker}{status} {model.display_name or model.name}{missing}'[:64]
                rows.append([(label, f'admin:model:{model.id}:{page}')])
        navigation = []
        if page:
            navigation.append(('←', f'admin:models:{page - 1}'))
        if page + 1 < pages:
            navigation.append(('→', f'admin:models:{page + 1}'))
        if navigation:
            rows.append(navigation)
        rows.extend([
            [('🔄 Обновить список Google', 'admin:modelrefresh')],
            [('В меню', 'admin:home')],
        ])
        lines = [
            f'🤖 Модели: {len(models)}', f'Страница {page + 1} из {pages}',
            f'По умолчанию: {default}',
            f'Каталог обновлён: {format_date(last_sync)} (Москва)',
            '', '🌐 Всем · 🔑 Whitelist · 🚫 Отключена · ⭐ По умолчанию',
            '⚠️ Нет в последнем каталоге Google; настройка доступа сохранена.',
            'Новые модели отключены, пока ты их не включишь.',
            'Наличие в каталоге не гарантирует доступ по тарифу и квотам ключа.',
        ]
        if notice:
            lines.extend(['', notice])
        self.show(message, '\n'.join(lines), keyboard(*rows), edit=True)

    def model_card(self, message, model_id, page=0, notice=None):
        with self.sessions() as session:
            model = model_catalog.get_model_by_id(session, model_id)
            back = [('← К моделям', f'admin:models:{page}')]
            if model is None:
                self.show(message, 'Модель не найдена. Обнови список моделей.', keyboard(back), edit=True)
                return
            is_default = model.name == model_catalog.get_default_model(session)
            lines = [
                (model.display_name or model.name)[:200], model.name[:300],
                f'Доступ: {MODEL_ACCESS_LABELS[model.access]}',
                f'По умолчанию: {"да ⭐" if is_default else "нет"}',
            ]
            if not model.available:
                lines.extend(['', '⚠️ Нет в последнем каталоге Google. Доступ сохранён; '
                              'модель может быть снята с обслуживания.'])
            rows = [[(label, f'admin:modelaccess:{model.id}:{access}:{page}')]
                    for access, label in MODEL_ACCESS_LABELS.items()]
            if not is_default:
                rows.append([('⭐ Сделать по умолчанию', f'admin:modeldefault:{model.id}:{page}')])
            rows.append(back)
            lines.extend(['', 'Настройки применяются без перезапуска.',
                          'По умолчанию можно выбрать только модель, доступную всем.'])
        if notice:
            lines.extend(['', notice])
        self.show(message, '\n'.join(lines), keyboard(*rows), edit=True)

    def refresh_models(self, message):
        if self.model_client is None:
            self.models(message, notice='Обновление каталога сейчас недоступно. Попробуй позже.')
            return
        try:
            # Fetch every page before beginning a write transaction.
            models = list(self.model_client.models.list())
            with self.sessions() as session:
                result = model_catalog.sync_catalog(session, models)
        except Exception:
            # Provider exceptions can include request URLs and credentials.
            self.models(message, notice='Не удалось обновить каталог Google. '
                        'Настройки и предыдущий каталог сохранены. Попробуй позже.')
            return
        self.models(message, notice=f'Каталог обновлён. Новых моделей: {result["added"]}; '
                    f'нет в каталоге: {result["missing"]}.')

    def change_model(self, message, model_id, page, access=None):
        try:
            with self.sessions() as session:
                if access is None:
                    model_catalog.set_default_model(session, model_id)
                else:
                    model_catalog.set_model_access(session, model_id, access)
        except ValueError as error:
            self.model_card(message, model_id, page, notice=str(error))
            return
        self.model_card(message, model_id, page, notice='Настройка сохранена.')

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
        self.show(message, text, keyboard([action], [('📈 Расход', f'admin:usage:today:sum:{user_id}:0')], back, [('В меню', 'admin:home')]), edit)

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

    def usage(self, message, period='today', group='sum', user_id=0, page=0):
        now = datetime.now(timezone.utc)
        today = now.astimezone(DISPLAY_TIMEZONE).replace(hour=0, minute=0, second=0, microsecond=0)
        since = None if period == 'all' else (
            today - timedelta(days={'today': 0, 'week': 6, 'month': 29}[period])
        ).astimezone(timezone.utc).replace(tzinfo=None)
        until = now.replace(tzinfo=None)
        target = user_id or None
        labels = {'today': 'Сегодня', 'week': '7 дней', 'month': '30 дней', 'all': 'Всё время'}
        lines = [f'📈 Расход · {labels[period]} (Москва)']
        with self.sessions() as session:
            if target:
                user = crud.get_user(session, target)
                lines.append(f'Пользователь: {user_label(user) if user else target} · ID {target}')
            data = usage_queries.summary(session, since, until, target)
            lines.extend(['', *usage_lines(data)])
            detail_rows = []
            if group != 'sum':
                results, page, pages = usage_queries.breakdown(
                    session, group, since, until, target, page, USAGE_PAGE_SIZE,
                )
                lines.extend(['', 'По моделям:' if group == 'models' else 'По пользователям:'])
                if not results:
                    lines.append('Запросов пока нет.')
                for result in results:
                    label = (get_model_alias(result['group_id'], result['group_id'])
                             if group == 'models' else result['label'])
                    lines.extend(['', label[:100], *usage_lines(result, compact=True)])
                    if group == 'users':
                        detail_rows.append([(label[:50], f'admin:usage:{period}:sum:{result["group_id"]}:0')])
                if pages > 1:
                    lines.append(f'Страница {page + 1} из {pages}')
                    navigation = []
                    if page:
                        navigation.append(('←', f'admin:usage:{period}:{group}:{user_id}:{page - 1}'))
                    if page + 1 < pages:
                        navigation.append(('→', f'admin:usage:{period}:{group}:{user_id}:{page + 1}'))
                    detail_rows.append(navigation)
            first = data['first_recorded_at']
            lines.extend(['', f'Учёт с: {format_date(first) if first else "первого запроса после обновления"}',
                          'Кеш входит во входные токены. Время — вызов API.'])
        def route(p=period, g=group, u=user_id, n=0):
            return f'admin:usage:{p}:{g}:{u}:{n}'
        rows = [
            [(label, route(p=p)) for p, label in [('today', 'Сегодня'), ('week', '7 дней'), ('month', '30 дней'), ('all', 'Всё время')]],
            [('Общее', route(g='sum')), ('По моделям', route(g='models'))],
        ]
        if not target:
            rows.append([('По пользователям', route(g='users'))])
        rows.extend(detail_rows)
        rows.append([('Обновить', route(n=page))])
        if target:
            rows.append([('← Карточка', f'admin:user:{user_id}:all:0'), ('Общий расход', 'admin:usage:today:sum:0:0')])
        rows.append([('В меню', 'admin:home')])
        self.show(message, '\n'.join(lines), keyboard(*rows), edit=True)

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
        elif parts == ['admin', 'modelrefresh']:
            self.refresh_models(call.message)
        elif (action == 'models' and len(parts) == 3
              and parts[2].isascii() and parts[2].isdecimal() and len(parts[2]) <= 9):
            self.models(call.message, int(parts[2]))
        elif (action in ('model', 'modeldefault') and len(parts) == 4
              and parts[2].isascii() and parts[2].isdecimal() and len(parts[2]) <= 19
              and int(parts[2]) < 2**63
              and parts[3].isascii() and parts[3].isdecimal() and len(parts[3]) <= 9):
            if action == 'model':
                self.model_card(call.message, int(parts[2]), int(parts[3]))
            else:
                self.change_model(call.message, int(parts[2]), int(parts[3]))
        elif (action == 'modelaccess' and len(parts) == 5
              and parts[2].isascii() and parts[2].isdecimal() and len(parts[2]) <= 19
              and int(parts[2]) < 2**63 and parts[3] in MODEL_ACCESS_LABELS
              and parts[4].isascii() and parts[4].isdecimal() and len(parts[4]) <= 9):
            self.change_model(call.message, int(parts[2]), int(parts[4]), access=parts[3])
        elif (action == 'usage' and len(parts) == 6
              and parts[2] in ('today', 'week', 'month', 'all')
              and parts[3] in ('sum', 'models', 'users')
              and parts[4].isdecimal() and len(parts[4]) <= 19
              and int(parts[4]) < 2**63 and parts[5].isdecimal()):
            self.usage(call.message, parts[2], parts[3], int(parts[4]), int(parts[5]))
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


def register_admin_handlers(bot, session_factory, model_client=None):
    panel = AdminPanel(bot, session_factory, model_client=model_client)
    bot.register_message_handler(panel.command, commands=['admin'])
    bot.register_callback_query_handler(panel.callback, func=lambda call: bool(call.data and call.data.startswith('admin:')))
    return panel
