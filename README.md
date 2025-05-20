[RU](#ru-section) - [EN](#en-section)

<a id="ru-section"></a>
## RU
---

# Telegram-бот на основе Google Gemini

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-%40degenerative__ai__bot-blue)](https://t.me/degenerative_ai_bot)
[![Deploy to Server](https://github.com/aeee78/tg_gemini_bot/actions/workflows/deploy.yml/badge.svg)](https://github.com/aeee78/tg_gemini_bot/actions/workflows/deploy.yml)

Этот проект реализует Telegram-бота, использующего Google Gemini API для взаимодействия с пользователями. Бот поддерживает различные модели Gemini, генерацию изображений, обработку файлов, интеграцию с Google Search, быстрые инструменты для специфических задач и гибкое управление диалогом.

## > Рабочий бот доступен по адресу [@degenerative_ai_bot](https://t.me/degenerative_ai_bot)

## Основные возможности

-   **Интеллектуальный чат:** Бот поддерживает контекст разговора для естественного общения.
-   **Поддержка нескольких моделей Gemini:** Выбирайте оптимальную модель для ваших задач:
    -   `2.5 Flash 🚀` (`gemini-2.5-flash-preview-05-20`)
    -   `2.5 Pro💡` (`gemini-2.5-pro-preview-05-06`) - Доступ к этой модели может быть разблокирован с помощью специального кода (см. команду `/unlock_pro`).
    -   `2.0 Flash❓` (`gemini-2.0-flash`)
-   **Генерация изображений:** Создавайте изображения по текстовому запросу с помощью команды `/generate <запрос>` (используется модель `gemini-2.0-flash-exp-image-generation`).
-   **Описание изображений:** Отправьте боту изображение, и он его опишет.
-   **Обработка файлов:** Отправляйте боту файлы (PDF, TXT, PY, JS, HTML, CSS, MD, CSV, XML, RTF) размером до 20 МБ. Бот учтет их содержимое при ответах в текущей сессии.
-   **Режимы отправки сообщений:**
    -   `Мгновенный ⚡`: Каждое сообщение/фото/файл отправляется в Gemini сразу.
    -   `Ручной ✍️`: Сообщения/фото/файлы накапливаются в буфере. Нажмите кнопку "Отправить всё", чтобы отправить их разом.
-   **Интеграция с Google Search:** Включите поиск Google (кнопка "Поиск: ..."), чтобы бот мог использовать актуальную информацию из интернета и предоставлять ссылки на источники.
-   **Быстрые инструменты (Quick Tools):** Набор команд (например, `/translate`, `/rewrite`, `/prompt`) для выполнения специфических задач с предопределенными инструкциями. Эти команды не влияют на основной чат. Полный список см. в разделе "Команды".
-   **Управление контекстом:** Начните "Новый чат", чтобы очистить историю и контекст (включая загруженные файлы).
-   **Обработка длинных ответов:** Ответы, превышающие лимит Telegram, автоматически разбиваются. Полный текст можно получить в виде файла .txt (инлайн-кнопка "Получить в виде файла") или .md (кнопка "Получить .MD 📄").
-   **Динамический интерфейс:** Основная клавиатура отображает текущую выбранную модель, режим отправки и статус поиска Google.

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
    PRO_CODE=<ваш_код_для_pro_доступа_опционально> # Установите этот код, чтобы включить команду /unlock_pro для доступа к модели 2.5 Pro
    ```
6.  **Запустите бота:**
    ```bash
    python gemini_bot.py
    ```

## Использование

1.  **Начало работы:** Отправьте боту команду `/start`. Бот поприветствует вас и покажет основную клавиатуру.
2.  **Общение:**
    -   Просто пишите текстовые сообщения.
    -   Отправляйте фотографии (бот их опишет или учтет в контексте, если включен ручной режим).
    -   Отправляйте поддерживаемые файлы (бот учтет их содержимое).
3.  **Выбор модели:** Нажмите кнопку `Модель: ...`, чтобы выбрать другую версию Gemini из списка. Доступ к `2.5 Pro💡` может потребовать ввода кода через команду `/unlock_pro <код>`. Смена модели начинает новый чат.
4.  **Режим отправки:** Нажмите кнопку `Режим: ...`, чтобы переключиться между `Мгновенный ⚡` и `Ручной ✍️`. В ручном режиме используйте кнопку `Отправить всё` для отправки накопленных сообщений/фото/файлов.
5.  **Поиск Google:** Нажмите кнопку `Поиск: ...`, чтобы включить или выключить использование Google Search.
6.  **Генерация изображений:** Используйте команду `/generate <ваш текстовый запрос>`.
7.  **Скачивание длинных ответов:** Если ответ был разбит, используйте инлайн-кнопку "Получить в виде файла" (.txt) или основную кнопку "Получить .MD 📄" (.md).
8.  **Новый диалог:** Нажмите кнопку `Новый чат`, чтобы сбросить историю и контекст беседы.
9.  **Быстрые инструменты:** Используйте команды, начинающиеся со `/` (например, `/translate <текст>`), для выполнения специфических задач. См. полный список в разделе "Команды".
10. **Разблокировка PRO модели:** Если администратор бота настроил `PRO_CODE`, вы можете использовать команду `/unlock_pro <код_доступа>` для получения доступа к модели `2.5 Pro💡`.
11. **Справка:** Используйте команду `/help` для получения подробной информации о возможностях бота.

## Команды

-   `/start` - 🚀 Перезапустить бота / Начать чат
-   `/generate <запрос>` - 🖼️ Сгенерировать изображение (напр. `/generate кот`)
-   `/help` - ℹ️ Справка по возможностям бота
-   `/unlock_pro <код>` - 🔑 Разблокировать доступ к модели `2.5 Pro💡` (если `PRO_CODE` настроен в .env).

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

## Развертывание (Deployment)

Проект настроен на автоматическое развертывание на сервер (Debian/Ubuntu-based) с помощью GitHub Actions при каждом пуше в ветку `main`.

-   **Workflow (`.github/workflows/deploy.yml`):**
    1.  Копирует файлы проекта (исключая `venv`, `.env`, `.git`, `.github`, `whitelist.txt`) на сервер через `rsync`.
    2.  На сервере:
        *   Устанавливает системные зависимости (например, `rsync`, `python3.13-venv`, `curl`).
        *   Устанавливает/обновляет `uv` (быстрый менеджер пакетов Python).
        *   Создает виртуальное окружение `.venv` с помощью `uv` и Python 3.13.
        *   Устанавливает зависимости из `requirements.txt` с помощью `uv pip install`.
        *   Перезапускает сервис `systemd` (например, `tg_gemini_bot.service`), который должен быть предварительно настроен на сервере для запуска бота.

-   **Необходимые секреты GitHub Actions:** `SERVER_SSH_KEY` (приватный SSH ключ) и `SERVER_IP` (IP адрес сервера).

-   **Важные примечания:**
    *   **Systemd сервис:** Файл сервиса (например, `tg_gemini_bot.service`) должен быть заранее создан в `/etc/systemd/system/` и настроен для запуска `gemini_bot.py` из виртуального окружения.
    *   **Python версия:** Скрипт развертывания ориентирован на Python 3.13.
    *   **`whitelist.txt`:** Этот файл исключен из синхронизации, чтобы не перезаписывать существующий на сервере.
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

This project implements a Telegram bot that uses the Google Gemini API to interact with users. The bot supports various Gemini models, image generation, file processing, Google Search integration, quick tools for specific tasks, and flexible dialogue management.

## > Live bot available at [@degenerative_ai_bot](https://t.me/degenerative_ai_bot)

## Key Features

-   **Intelligent Chat:** The bot maintains conversation context for natural communication.
-   **Support for Multiple Gemini Models:** Choose the optimal model for your tasks:
    -   `2.5 Flash 🚀` (`gemini-2.5-flash-preview-05-20`)
    -   `2.5 Pro💡` (`gemini-2.5-pro-preview-05-06`) - Access to this model can be unlocked with a special code (see the `/unlock_pro` command).
    -   `2.0 Flash❓` (`gemini-2.0-flash`)
-   **Image Generation:** Create images from text prompts using the `/generate <prompt>` command (uses the `gemini-2.0-flash-exp-image-generation` model).
-   **Image Description:** Send an image to the bot, and it will describe it.
-   **File Processing:** Send files (PDF, TXT, PY, JS, HTML, CSS, MD, CSV, XML, RTF) up to 20 MB to the bot. The bot will consider their content in responses during the current session.
-   **Message Sending Modes:**
    -   `Instant ⚡`: Each message/photo/file is sent to Gemini immediately.
    -   `Manual ✍️`: Messages/photos/files accumulate in a buffer. Press the "Send all" button to send them at once.
-   **Google Search Integration:** Enable Google Search (button "Search: ...") so the bot can use up-to-date information from the internet and provide source links.
-   **Quick Tools:** A set of commands (e.g., `/translate`, `/rewrite`, `/prompt`) for performing specific tasks with predefined instructions. These commands do not affect the main chat. See the "Commands" section for a full list.
-   **Context Management:** Start a "New Chat" to clear history and context (including uploaded files).
-   **Handling Long Responses:** Responses exceeding Telegram's limit are automatically split. The full text can be obtained as a .txt file (inline button "Get as file") or .md file (button "Get .MD 📄").
-   **Dynamic Interface:** The main keyboard displays the currently selected model, sending mode, and Google Search status.

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
    PRO_CODE=<your_pro_access_code_optional> # Set this code to enable the /unlock_pro command for accessing the 2.5 Pro model
    ```
6.  **Run the bot:**
    ```bash
    python gemini_bot.py
    ```

## Usage

1.  **Getting Started:** Send the `/start` command to the bot. The bot will greet you and show the main keyboard.
2.  **Interacting:**
    -   Simply type text messages.
    -   Send photos (the bot will describe them or consider them in context if manual mode is enabled).
    -   Send supported files (the bot will consider their content).
3.  **Model Selection:** Press the `Model: ...` button to choose a different Gemini version from the list. Access to `2.5 Pro💡` may require entering a code via the `/unlock_pro <code>` command. Changing the model starts a new chat.
4.  **Sending Mode:** Press the `Mode: ...` button to switch between `Instant ⚡` and `Manual ✍️`. In manual mode, use the `Send all` button to send accumulated messages/photos/files.
5.  **Google Search:** Press the `Search: ...` button to enable or disable Google Search.
6.  **Image Generation:** Use the `/generate <your text prompt>` command.
7.  **Downloading Long Responses:** If a response was split, use the inline button "Get as file" (.txt) or the main button "Get .MD 📄" (.md).
8.  **New Dialogue:** Press the `New Chat` button to reset the conversation history and context.
9.  **Quick Tools:** Use commands starting with `/` (e.g., `/translate <text>`) to perform specific tasks. See the full list in the "Commands" section.
10. **Unlock PRO Model:** If the bot administrator has configured `PRO_CODE`, you can use the `/unlock_pro <access_code>` command to gain access to the `2.5 Pro💡` model.
11. **Help:** Use the `/help` command to get detailed information about the bot's features.

## Commands

-   `/start` - 🚀 Restart bot / Start chat
-   `/generate <prompt>` - 🖼️ Generate image (e.g., `/generate cat`)
-   `/help` - ℹ️ Help with bot features
-   `/unlock_pro <code>` - 🔑 Unlock access to the `2.5 Pro💡` model (if `PRO_CODE` is set in .env).

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

## Deployment

The project is configured for automatic deployment to a server (Debian/Ubuntu-based) using GitHub Actions on every push to the `main` branch.

-   **Workflow (`.github/workflows/deploy.yml`):**
    1.  Copies project files (excluding `venv`, `.env`, `.git`, `.github`, `whitelist.txt`) to the server via `rsync`.
    2.  On the server:
        *   Installs system dependencies (e.g., `rsync`, `python3.13-venv`, `curl`).
        *   Installs/updates `uv` (a fast Python package manager).
        *   Creates a `.venv` virtual environment using `uv` and Python 3.13.
        *   Installs dependencies from `requirements.txt` using `uv pip install`.
        *   Restarts the `systemd` service (e.g., `tg_gemini_bot.service`), which must be pre-configured on the server to run the bot.

-   **Required GitHub Actions Secrets:** `SERVER_SSH_KEY` (private SSH key) and `SERVER_IP` (server IP address).

-   **Important Notes:**
    *   **Systemd service:** The service file (e.g., `tg_gemini_bot.service`) must be created in `/etc/systemd/system/` beforehand and configured to run `gemini_bot.py` from the virtual environment.
    *   **Python version:** The deployment script targets Python 3.13.
    *   **`whitelist.txt`:** This file is excluded from synchronization to avoid overwriting an existing one on the server.
    *   **Permissions:** The script assumes it has permissions to install packages and manage `systemd` services on the server.

**Note:** You can also host the project for free on [pythonanywhere.com](https://www.pythonanywhere.com/), but automatic deployment via GitHub Actions is configured for a dedicated server with `systemd`.