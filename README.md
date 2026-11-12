[RU](#ru-section) - [EN](#en-section)

<a id="ru-section"></a>
## RU
---

# Telegram-бот на основе Google Gemini

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-%40degenerative__ai__bot-blue)](https://t.me/degenerative_ai_bot)
[![Deploy to Server](https://github.com/aeee78/tg_gemini_bot/actions/workflows/deploy.yml/badge.svg)](https://github.com/aeee78/tg_gemini_bot/actions/workflows/deploy.yml)

Этот проект реализует Telegram-бота, использующего Google Gemini API для взаимодействия с пользователями. Бот поддерживает различные модели Gemini, **интеллектуальную генерацию и редактирование изображений**, обработку файлов, интеграцию с Google Search, быстрые инструменты для специфических задач и гибкое управление диалогом.

## > Рабочий бот доступен по адресу [@degenerative_ai_bot](https://t.me/degenerative_ai_bot)

## Основные возможности

### 🎨 **Генерация и редактирование изображений**
-   **Text → Image:** Просто напишите "Нарисуй кота в космосе" и получите изображение
-   **Image + Text → Image:** Загрузите фото и попросите "Измени стиль на винтаж" 
-   **Многоэтапное редактирование:** Пошаговое изменение изображений в диалоге
-   **Автоматическое определение:** Выберите модель `3.1 Flash IMG🎨` и бот автоматически будет генерировать изображения

### 🧠 **Поддержка моделей Gemini**
-   **`3.8 Flash 🚀`** (`gemini-3.8-flash`) - Быстрая модель для сложных задач (доступ через `/unlock_pro`)
-   **`3.5 Flash Lite🐣`** (`gemini-3.5-flash-lite`) - Экономичная и сверхбыстрая модель по умолчанию
-   **`3.1 Flash IMG🎨`** (`gemini-3.1-flash-image`) - **Модель с генерацией и редактированием изображений** (доступ через `/unlock_pro`)

### 📁 **Работа с файлами**
-   **Поддержка форматов:** PDF, DOCX, TXT, CSV, JSON, XML, HTML, CSS, JS, PY и другие
-   **Анализ изображений:** JPG, PNG, GIF, WebP - бот опишет содержимое
-   **Размер файлов:** до 20 МБ
-   **Контекст:** Файлы сохраняются в памяти диалога до начала нового чата

### 🔍 **Google Search интеграция**
-   Поиск актуальной информации в интернете (кнопка "Поиск: ...")
-   Автоматическое отображение источников со ссылками
-   Возможность включения/выключения для каждого запроса

### ⚡ **Интеллектуальные режимы работы**
-   **Мгновенный ⚡:** Каждое сообщение/фото/файл отправляется сразу
-   **Ручной ✍️:** Накопление в буфере для отправки комплексных запросов
-   **Контекстная память:** Бот помнит всю историю диалога
-   **Быстрые инструменты:** Специализированные команды для конкретных задач

## Установка и настройка

1.  **Клонируйте репозиторий:**
    ```bash
    git clone https://github.com/aeee78/tg_gemini_bot.git
    cd tg_gemini_bot
    ```
2.  **Создайте и активируйте виртуальное окружение (рекомендуется):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate  # Windows
    ```
3.  **Установите зависимости:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Получите API ключи:**
    -   **Telegram API:** Создайте бота и получите токен через [@BotFather](https://t.me/BotFather).
    -   **Google Gemini API:** Получите API ключ в [Google AI Studio](https://aistudio.google.com/apikey).
5.  **Настройте переменные окружения:**
    Создайте файл `.env` в корневой директории проекта (можно скопировать `.env.example` и переименовать: `cp env.example .env`). Добавьте ваши ключи:
    ```plaintext
    TELEGRAM_TOKEN=<ваш_токен_telegram>
    GEMINI_API_KEY=<ваш_api_ключ_gemini>
    PRO_CODE=<ваш_код_для_pro_доступа_опционально> # Установите этот код, чтобы включить команду /unlock_pro для доступа к некоторым моделям
    ```
6.  **Запустите бота:**
    ```bash
    python gemini_bot.py
    ```

## Использование

### 🚀 **Начало работы**
1. Отправьте боту команду `/start` - бот поприветствует вас и покажет основную клавиатуру
2. Выберите нужную модель через кнопку `Модель: ...`

### 🎨 **Генерация изображений**
1. **Выберите модель генерации:** Нажмите `Модель: ...` → `3.1 Flash IMG🎨`
2. **Создавайте изображения:**
   - **Текст → Изображение:** "Нарисуй кота в космическом шлеме"
   - **Изображение + Текст → Новое изображение:** Загрузите фото → "Измени стиль на аниме"
   - **Серия изменений:** "Добавь шляпу" → "Измени цвет на красный" → "Добавь фон"

### 💬 **Обычное общение**
1. **Текстовые сообщения:** Просто пишите - бот помнит контекст диалога
2. **Фотографии:** Отправляйте изображения для анализа или как основу для генерации
3. **Файлы:** Поддерживаются PDF, DOCX, TXT, CSV и другие форматы до 20 МБ

### ⚙️ **Настройки и режимы**
- **Модель:** `Модель: ...` - выбор между текстовыми и генеративными моделями
- **Режим отправки:** `Режим: ...` - мгновенный ⚡ или ручной ✍️
- **Google Search:** `Поиск: ...` - включение поиска актуальной информации
- **Новый чат:** Очистка истории и контекста диалога

### 📥 **Скачивание ответов**
- **Markdown:** Кнопка "Получить .MD 📄"
- **Текст:** Инлайн-кнопка "Скачать в формате .txt" (для длинных ответов)

## Команды

### Основные команды
- `/start` - 🚀 Перезапустить бота / Начать чат
- `/help` - ℹ️ Справка по возможностям бота
- `/unlock_pro <код>` - 🔑 Разблокировать 3.8 Flash, генерацию изображений и команды `/promptpro`, `/table`, `/dayplanner`

### Быстрые инструменты

Эти команды выполняют одноразовые задачи и не влияют на контекст вашего основного чата. Они используют предопределенные системные инструкции для конкретных целей.

-   `/translate <текст>` - ru<>en Перевод текста
-   `/prompt <текст_промпта>` - ✨ Улучшение промпта (запроса) для AI
-   `/promptpro <текст_промпта>` - 🚀 PRO Улучшение промпта (запроса) для AI
-   `/rewrite <текст>` - 🎓 Переписать текст в академическом стиле (для диплома или курсовой)
-   `/simplify <текст>` - 💡 Упростить текст, сделать его понятнее
-   `/elaborate <текст>` - 📚 Расширить текст, добавить детали (академ. стиль)
-   `/formal <текст>` - 👔 Сделать текст более формальным и деловым
-   `/proofread <текст>` - ✍️ Коррекция грамматики, орфографии, пунктуации
-   `/list <текст>` - 📋 Преобразовать текст в маркированный или нумерованный список
-   `/table <текст>` - 📊 Преобразовать текст в таблицу Markdown
-   `/todo <текст>` - ☑️ Создать список задач (todo list) из текста
-   `/markdown <текст>` - #️⃣ Добавить базовое Markdown форматирование
-   `/dayplanner <описание_дня>` - 📅 Умный планировщик дня (задачи, еда)

## 🎨 Примеры использования генерации изображений

### Простая генерация (Text → Image)
1. Выберите модель `3.1 Flash IMG🎨`
2. Напишите: "Нарисуй футуристический город на закате"
3. Получите сгенерированное изображение

### Редактирование изображений (Image → Image)
1. Выберите модель `3.1 Flash IMG🎨`
2. Загрузите фото своей комнаты
3. Напишите: "Измени интерьер в стиле минимализм"
4. Получите обновленное изображение

### Многоэтапное редактирование
1. Загрузите фото машины → "Сделай её кабриолетом"
2. Продолжите: "Измени цвет на красный"
3. Завершите: "Добавь красивый пейзаж на фон"

### Создание иллюстрированного контента
- "Создай рецепт борща с пошаговыми иллюстрациями"
- "Нарисуй инфографику о пользе спорта"
- "Создай комикс про кота-программиста"

> **💡 Подсказка:** Модель `3.1 Flash IMG🎨` автоматически определяет, когда нужно генерировать изображения. Google Search и URL Context для неё отключены, так как они не поддерживаются.

## Развертывание (Deployment)

Проект настроен на автоматическое развертывание на сервер (Debian/Ubuntu-based) с помощью GitHub Actions при каждом пуше в ветку `main`.

-   **Workflow (`.github/workflows/deploy.yml`):**
    1.  Запускает тесты на Python 3.13 с зависимостями из закоммиченного `requirements.txt`; ошибка блокирует выкладку. Для pull request выполняются только проверки.
    2.  Создаёт резервную копию кода и SQLite в `/home/tg_gemini_bot_backups` и копирует файлы через `rsync`, сохраняя `.env`, `bot.db*`, whitelist и виртуальные окружения.
    3.  На сервере:
        *   Устанавливает системные зависимости (например, `rsync`, `python3.13-venv`, `curl`).
        *   Устанавливает/обновляет `uv` (быстрый менеджер пакетов Python).
        *   Создает виртуальное окружение `.venv` с помощью `uv` и Python 3.13.
        *   Синхронизирует проверенные версии из `requirements.txt` через `uv pip sync`; обновление версий выполняется отдельно от деплоя.
        *   Перезапускает сервис `systemd` (например, `tg_gemini_bot.service`), который должен быть предварительно настроен на сервере для запуска бота.
        *   Проверяет активность сервиса и чтение каталога моделей. Выкладки из `main` выполняются последовательно.

-   **Необходимые секреты GitHub Actions:** `SERVER_SSH_KEY` (приватный SSH ключ), `SERVER_IP` (IP адрес сервера) и SERVER_SSH_PORT (опционально): SSH порт вашего сервера, если он отличается от стандартного порта 22. Если этот секрет не указан или пуст, будет использован порт 22.

-   **Важные примечания:**
    *   **Systemd сервис:** Файл сервиса (например, `tg_gemini_bot.service`) должен быть заранее создан в `/etc/systemd/system/` и настроен для запуска `gemini_bot.py` из виртуального окружения.
    *   **Python версия:** Скрипт развертывания ориентирован на Python 3.13.
    *   **Доступ к закрытым моделям:** Хранится в `users.pro_access` в `bot.db`. При первом запуске обновлённого бота все ID из `whitelist.txt` однократно импортируются с `pro_access=True`, включая отсутствующих в базе пользователей. Повторный запуск не восстанавливает отозванный доступ. Файл остаётся резервной копией, исключённой из синхронизации; новые разблокировки сохраняются только в базе.
    *   **Права доступа:** Скрипт предполагает наличие прав на установку пакетов и управление сервисами `systemd` на сервере.

**Примечание:** Вы также можете бесплатно разместить проект на [pythonanywhere.com](https://www.pythonanywhere.com/), но автоматическое развертывание через GitHub Actions настроено для выделенного сервера с `systemd`.

<br>
<br>

<a id="en-section"></a>
## EN
---

# Google Gemini-based Telegram Bot

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-%40degenerative__ai__bot-blue)](https://t.me/degenerative_ai_bot)
[![Deploy to Server](https://github.com/aeee78/tg_gemini_bot/actions/workflows/deploy.yml/badge.svg)](https://github.com/aeee78/tg_gemini_bot/actions/workflows/deploy.yml)

This project implements a Telegram bot that uses the Google Gemini API to interact with users. The bot supports various Gemini models, **intelligent image generation and editing**, file processing, Google Search integration, quick tools for specific tasks, and flexible dialogue management.

## > Live bot available at [@degenerative_ai_bot](https://t.me/degenerative_ai_bot)

## Key Features

### 🎨 **Image Generation and Editing**
-   **Text → Image:** Simply write "Draw a cat in space" and get an image
-   **Image + Text → Image:** Upload a photo and ask "Change style to vintage" 
-   **Multi-step editing:** Step-by-step image modifications in dialogue
-   **Automatic detection:** Select `3.1 Flash IMG🎨` model and the bot will automatically generate images

### 🧠 **Gemini Models Support**
-   **`3.8 Flash 🚀`** (`gemini-3.8-flash`) - Fast model for complex tasks (access via `/unlock_pro`)
-   **`3.5 Flash Lite🐣`** (`gemini-3.5-flash-lite`) - Economical and ultra-fast default model
-   **`3.1 Flash IMG🎨`** (`gemini-3.1-flash-image`) - **Image generation and editing model** (access via `/unlock_pro`)

### 📁 **File Processing**
-   **Supported formats:** PDF, DOCX, TXT, CSV, JSON, XML, HTML, CSS, JS, PY and others
-   **Image analysis:** JPG, PNG, GIF, WebP - bot will describe content
-   **File size:** up to 20 MB
-   **Context:** Files are stored in dialogue memory until new chat

### 🔍 **Google Search Integration**
-   Search for current information on the internet ("Search: ..." button)
-   Automatic display of sources with links
-   Can be enabled/disabled for each request

### ⚡ **Intelligent Working Modes**
-   **Instant ⚡:** Each message/photo/file is sent immediately
-   **Manual ✍️:** Accumulation in buffer for sending complex requests
-   **Context memory:** Bot remembers entire dialogue history
-   **Quick tools:** Specialized commands for specific tasks

## Installation and Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/aeee78/tg_gemini_bot.git
    cd tg_gemini_bot
    ```
2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate  # Windows
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Obtain API keys:**
    -   **Telegram API:** Create a bot and get a token via [@BotFather](https://t.me/BotFather).
    -   **Google Gemini API:** Get an API key from [Google AI Studio](https://aistudio.google.com/apikey).
5.  **Configure environment variables:**
    Create a `.env` file in the project's root directory (you can copy `.env.example` and rename it: `cp env.example .env`). Add your keys:
    ```plaintext
    TELEGRAM_TOKEN=<your_telegram_token>
    GEMINI_API_KEY=<your_gemini_api_key>
    PRO_CODE=<your_pro_access_code_optional> # Set this code to enable the /unlock_pro command for accessing some models
    ```
6.  **Run the bot:**
    ```bash
    python gemini_bot.py
    ```

## Usage

### 🚀 **Getting Started**
1. Send the `/start` command to the bot - it will greet you and show the main keyboard
2. Select the needed model via `Model: ...` button

### 🎨 **Image Generation**
1. **Select generation model:** Press `Model: ...` → `3.1 Flash IMG🎨`
2. **Create images:**
   - **Text → Image:** "Draw a cat in a space helmet"
   - **Image + Text → New Image:** Upload photo → "Change style to anime"
   - **Series of changes:** "Add a hat" → "Change color to red" → "Add background"

### 💬 **Regular Communication**
1. **Text messages:** Simply write - bot remembers dialogue context
2. **Photos:** Send images for analysis or as base for generation
3. **Files:** Supported PDF, DOCX, TXT, CSV and other formats up to 20 MB

### ⚙️ **Settings and Modes**
- **Model:** `Model: ...` - choice between text and generative models
- **Sending mode:** `Mode: ...` - instant ⚡ or manual ✍️
- **Google Search:** `Search: ...` - enable search for current information
- **New chat:** Clear history and dialogue context

### 📥 **Download Responses**
- **Markdown:** "Get .MD 📄" button
- **Text:** Inline button "Download as .txt" (for long responses)

## Commands

### Main Commands
- `/start` - 🚀 Restart bot / Start chat
- `/help` - ℹ️ Help with bot features
- `/unlock_pro <code>` - 🔑 Unlock 3.8 Flash, image generation, and `/promptpro`, `/table`, `/dayplanner`

### Quick Tools

These commands perform one-off tasks and do not affect your main chat context. They use predefined system instructions for specific purposes.

-   `/translate <text>` - ru<>en Translate text
-   `/prompt <prompt_text>` - ✨ Enhance prompt for AI
-   `/promptpro <prompt_text>` - 🚀 PRO Enhance prompt for AI
-   `/rewrite <text>` - 🎓 Rewrite text in an academic style (for a thesis or coursework)
-   `/simplify <text>` - 💡 Simplify text, make it easier to understand
-   `/elaborate <text>` - 📚 Expand text, add details (academic style)
-   `/formal <text>` - 👔 Make text more formal and business-like
-   `/proofread <text>` - ✍️ Correct grammar, spelling, punctuation
-   `/list <text>` - 📋 Convert text into a bulleted or numbered list
-   `/table <text>` - 📊 Convert text into a Markdown table
-   `/todo <text>` - ☑️ Create a to-do list from text
-   `/markdown <text>` - #️⃣ Add basic Markdown formatting
-   `/dayplanner <day_description>` - 📅 Smart day planner (tasks, meals)

## 🎨 Image Generation Examples

### Simple Generation (Text → Image)
1. Select model `3.1 Flash IMG🎨`
2. Write: "Draw a futuristic city at sunset"
3. Receive generated image

### Image Editing (Image → Image)
1. Select model `3.1 Flash IMG🎨`
2. Upload photo of your room
3. Write: "Change interior to minimalist style"
4. Receive updated image

### Multi-step Editing
1. Upload car photo → "Make it a convertible"
2. Continue: "Change color to red"
3. Finish: "Add beautiful landscape background"

### Creating Illustrated Content
- "Create a borscht recipe with step-by-step illustrations"
- "Draw an infographic about benefits of sports"
- "Create a comic about a programmer cat"

> **💡 Tip:** Model `3.1 Flash IMG🎨` automatically determines when to generate images. Google Search and URL Context are disabled for it as they are not supported.

## Deployment

The project is configured for automatic deployment to a server (Debian/Ubuntu-based) using GitHub Actions on every push to the `main` branch.

-   **Workflow (`.github/workflows/deploy.yml`):**
    1.  Runs tests on Python 3.13 with the committed `requirements.txt`; failures block deployment. Pull requests run validation only.
    2.  Backs up code and SQLite to `/home/tg_gemini_bot_backups`, then copies files via `rsync`, preserving `.env`, `bot.db*`, the whitelist and virtual environments.
    3.  On the server:
        *   Installs system dependencies (e.g., `rsync`, `python3.13-venv`, `curl`).
        *   Installs/updates `uv` (a fast Python package manager).
        *   Creates a `.venv` virtual environment using `uv` and Python 3.13.
        *   Syncs the tested versions from `requirements.txt` using `uv pip sync`; dependency upgrades happen separately from deployment.
        *   Restarts the `systemd` service (e.g., `tg_gemini_bot.service`), which must be pre-configured on the server to run the bot.
        *   Checks service readiness and the model catalog. Deployments from `main` run sequentially.

-   **Required GitHub Actions Secrets:** `SERVER_SSH_KEY` (private SSH key), `SERVER_IP` (server IP address) and SERVER_SSH_PORT (optional): The SSH port of your server if it differs from the default port 22. If this secret is not provided or is empty, port 22 will be used.

-   **Important Notes:**
    *   **Systemd service:** The service file (e.g., `tg_gemini_bot.service`) must be created in `/etc/systemd/system/` beforehand and configured to run `gemini_bot.py` from the virtual environment.
    *   **Python version:** The deployment script targets Python 3.13.
    *   **Premium access:** Stored in `users.pro_access` in `bot.db`. On the first updated startup, all IDs from `whitelist.txt` are imported once with `pro_access=True`, creating missing users. Restarts do not restore revoked access. The file remains an excluded backup; new unlocks are stored only in the database.
    *   **Permissions:** The script assumes it has permissions to install packages and manage `systemd` services on the server.

**Note:** You can also host the project for free on [pythonanywhere.com](https://www.pythonanywhere.com/), but automatic deployment via GitHub Actions is configured for a dedicated server with `systemd`.


### Данные профиля пользователей

Таблица `users` хранит `first_name`, `last_name`, `username` (без `@`),
`language_code`, `registered_at` и `last_active_at`. Профиль обновляется по данным
Telegram при обработке сообщений и нажатий кнопок; удалённые username и фамилия
очищаются. `/start` и `/help` также обновляют профиль и активность.

`registered_at` — время первого обращения, создавшего пользователя в базе
(обычно `/start`), а не дата создания аккаунта Telegram. Для существующих
пользователей и ID, импортированных из whitelist, историческая дата неизвестна
и остаётся `NULL`. Новая активность не подменяет эту дату. `last_active_at`
начинает заполняться при следующем обращении после обновления. Обе даты
хранятся в UTC. Миграция автоматически добавляет поля в существующую SQLite-базу.


### Админка

Личный кабинет администратора реализован в `admin.py` и подключается перед
общими обработчиками сообщений. Команда `/admin` доступна только Telegram ID
`66765326` в личном чате с ботом; тот же доступ проверяется для каждой кнопки.
Администраторские права не выдаются кодом `/unlock_pro`.

- «Пользователи» и «Белый список»: списки по 8 пользователей на странице.
- «Найти пользователя»: `/admin 123456789` или `/admin @username`.
  Username ищется целиком, без учёта регистра, по последним сохранённым данным.
- Карточка: профиль, ID, доступ, регистрация, активность, модель и настройки.
  Даты отображаются по московскому времени; неизвестные даты обозначены явно.
- Выдача доступа и отзыв с подтверждением: изменения сохраняются в
  `users.pro_access`. При следующем обращении после отзыва бот переключает
  закрытую модель на Lite, сохраняя историю.
- Статистика: всего пользователей, пользователей с доступом, активных за
  последние 24 часа / 7 / 30 дней и распределение выбранных моделей.
  Это статистика сохранённых настроек и активности, а не расхода токенов.


### Расход Gemini API

В `/admin` → «📈 Расход» доступны периоды «Сегодня», «7 дней», «30 дней»,
«Всё время», сводка, разбивка по моделям и пользователям с переключением
страниц. В карточке пользователя есть кнопка его расхода. Периоды считаются
по московским календарным дням, включая текущий день, а время в базе — UTC.

Таблица `usage_records` создаётся автоматически при инициализации базы.
Одна запись соответствует вызову Gemini SDK: обычный чат, фото, отправка
буфера или быстрая команда. Хранятся ID пользователя, модель, операция,
время начала, длительность API-вызова, успешность, класс/код ошибки и
входные/выходные/thinking/кеш/tool/общие токены из `usage_metadata`.
Тексты запросов, ответов и ошибок в эту таблицу не записываются.

Кеш уже входит во входные токены. Общий расход берётся из Google, а не
вычисляется суммированием полей. Отсутствующие значения остаются `NULL`:
в интерфейсе показаны неизвестные значения или частичные суммы. Ошибка API
не считается запросом с нулевым расходом; успешный запрос без метаданных
также имеет неизвестный расход. Длительность и успешность относятся к
вызову API, а не доставке ответа в Telegram. При ошибке записи статистики
результат API сохраняется, проблема отмечается в журнале.

Учёт начинается после обновления; история расходов Google и фактический
биллинг не импортируются. Денежная стоимость пока не рассчитывается.


### Inline-вызов в любом чате

У BotFather включите **Inline Mode** для бота (`/setinline`) и задайте
подсказку «Спросите Gemini». Через `/setinlinefeedback`
выберите бота и нажмите **Enabled**, чтобы Telegram сообщал о каждом выборе
результата и генерация начиналась автоматически. Значения `1/10`, `1/100`
и `1/1000` отправляют только часть событий; `1/100` — это 1%, а не 100%.

В любом чате наберите `@имябота вопрос` и выберите «Спросить Gemini».
Бот отправит заготовку «Gemini готовит ответ…» и автоматически отредактирует
это же сообщение, заменив её ответом. Кнопка «Обновить ответ» — запасной
вариант, если событие выбора не пришло; после ответа кнопка убирается.
Для автоматического запуска нужен feedback **Enabled**. Inline Mode обязателен;
Guest Chat Mode и Group Privacy не заменяют эту настройку и менять их не нужно.

Inline всегда использует `gemini-3.5-flash-lite`, независимо от модели личного
диалога и дефолтной модели админки. Права на Flash Lite из админки проверяются
при генерации. `/start` не требуется. Генерация не запускается при наборе
текста, а только при выборе результата или нажатии кнопки автором запроса.
История личного диалога, файлы и буфер не читаются и не изменяются.
В статистике вызов учитывается как `inline`.

Ответ текстовый, до лимита одного сообщения Telegram; длинный ответ обрезается
с пометкой. Одновременно выполняются максимум два inline-запроса, по одному
на пользователя. Повторное событие не запускает вторую генерацию. Временные
запросы хранятся в ограниченном кеше 15 минут; после перезапуска или истечения
срока нужно вызвать бота заново. Если доставка ответа не удалась, повторное
нажатие до истечения срока использует уже полученный ответ.

### Управление моделями в админке

Открой `/admin` → «Модели». В карточке модели можно выбрать доступ:
«Всем», «Только whitelist», «Только админ» или «Отключена», а также назначить её моделью
по умолчанию. По умолчанию разрешено выбирать только общедоступную модель;
перед её отключением или ограничением доступа нужно назначить другую.

«Обновить список Google» загружает каталог через Gemini API с текущим ключом
бота. В раздел попадают Gemini-модели и алиасы Nano Banana для обычного
`generateContent`: специализированные модели для embeddings, TTS, Live
и транскрибации не предлагаются.
Новые модели добавляются отключёнными. Обновление сохраняет выбранные
права и дефолтную модель. Отсутствие модели в последнем ответе Google
отмечается в админке, но автоматически не меняет её доступ: администратор
может отключить её сам. Ошибка загрузки не меняет сохранённый каталог.
Наличие модели в каталоге не гарантирует доступ по тарифу и квотам ключа;
поддержка поиска, аудио и других возможностей зависит от самой модели.

Настройки хранятся в `model_configs` и `model_catalog_settings` в `bot.db`.
При первом запуске импортируется прежняя конфигурация: Flash Lite доступна
всем и выбрана по умолчанию, Flash и модель изображений — только whitelist.
Перезапуск не сбрасывает настройки. Обновление каталога выполняется только
по кнопке в админке, без автоматических сетевых запросов при старте.

Изменения применяются при следующих обращениях без перезапуска бота.
Новые пользователи получают текущую дефолтную модель. Существующий выбор
сохраняется, пока модель доступна пользователю; иначе бот переключает его
на дефолтную с сохранением переносимой истории, файлов и буфера,
уведомляет пользователя и обновляет кнопку текущей модели.
Отключённые модели скрыты из меню, whitelist-модели помечены замком для
пользователей без доступа. Старые кнопки повторно проверяют актуальные права.
Модели «Только админ» видны и доступны только пользователям из `ADMIN_IDS`
в `constants.py`; добавление в whitelist этого доступа не даёт. Администратор
может использовать общие, whitelist- и админские модели без разблокировки
whitelist. Отключённые модели недоступны всем, включая администратора.

Обычные быстрые команды, включая `/translate`, используют текущую дефолтную
модель. Команды с явно заданной моделью в `quick_tools_config.py` сохраняют
своё назначение и тоже проверяют доступ: отключение модели останавливает
вызов, а режимы whitelist и «Только админ» требуют соответствующего доступа.

### Контекст и смена модели

`/start` и смена режима отправки сохраняют ожидающие файлы, буфер и последний
ответ. Вложения удаляются из ожидающих только вместе с успешной записью
переписки в базу. Пустой/заблокированный ответ модели и ошибка записи оставляют
ожидающие данные на месте. Документ в ручном режиме хранится только в буфере,
а подготовленные раньше документы также передаются при отправке фото и буфера.
После успешной отправки вложения остаются в сохранённой истории диалога.

Повреждённая история не заменяется пустой автоматически: бот предлагает
явный сброс кнопкой «Новый чат». Сброс истории, файлов и буфера выполняется
одной транзакцией. Скачивание ответов разрешено только владельцу в личном
чате с ботом; ошибки сетевых клиентов не выводятся пользователю с URL и ключами.

Смена модели сохраняет текстовую историю, изображения, ожидающие файлы, буфер
и последний ответ для скачивания. Модель и перенесённая история сохраняются
в базе одной транзакцией. При переносе удаляются только служебные reasoning
подписи и скрытые reasoning-части прежней модели. Если создать новый чат не
удалось, текущая модель и история остаются прежними. Операции одного
пользователя выполняются последовательно: при попытке сменить модель во
время текущего запроса кнопка попросит дождаться его завершения. Кнопка «Новый чат» по-прежнему очищает диалог.

Кнопка «Контекст 🧠» и `/context` показывают размер истории вместе с
ожидающими файлами и буфером через Gemini `count_tokens`. Также отображаются
лимит входа выбранной модели и его заполнение, если API вернул лимит.
Это оценка текущего снимка: следующее сообщение и служебные инструменты
в неё не входят. Подсчёт не создаёт ответ Gemini и не очищает историю.


### Голосовые сообщения

Отправьте голосовое Telegram — бот передаст аудио Gemini и ответит текстом
на языке пользователя с учётом истории диалога. Поддерживаются Flash Lite
и Flash; для модели изображений бот предложит переключиться на текстовую.
Лимит одного голосового — 20 МБ, проверяются метаданные и размер скачанного
файла. Отдельный сервис транскрибации и преобразование аудио не используются.

В ручном режиме голосовые сохраняются в SQLite-буфере вместе с MIME-типом
и могут быть отправлены кнопкой «Отправить всё» вместе с текстом и другими
вложениями. Если API вернёт ошибку, буфер остаётся. Голосовые включаются
в `/context`, сохраняются в истории и переносятся между текстовыми моделями.
Если в истории есть аудио, переключение на модель изображений предложит
сначала начать новый чат: эта модель не принимает аудиоисторию.
Обычный вызов учитывается в расходе как `voice`, отправка из буфера — `buffer`.
Ожидающие документы при мгновенном голосовом запросе также передаются модели.


Во время генерации ответа бот обновляет статус «печатает…» каждые 4 секунды.
Обновление прекращается после ответа API или ошибки. Это действует для чата,
фото, голосовых, буфера и быстрых команд. Сбой отправки статуса не прерывает
запрос Gemini и не подменяет его ошибку.
