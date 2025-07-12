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
-   **Автоматическое определение:** Выберите модель `2.0 Flash+IMG🎨` и бот автоматически будет генерировать изображения

### 🧠 **Поддержка моделей Gemini**
-   **`2.5 Flash 🚀`** (`gemini-2.5-flash`) - Быстрая модель для повседневных задач
-   **`2.5 Pro💡`** (`gemini-2.5-pro`) - Продвинутая модель для сложных задач (доступ через `/unlock_pro`)
-   **`2.5 Flash Lite🐣`** (`gemini-2.5-flash-lite-preview-06-17`) - Облегченная версия
-   **`2.0 Flash+IMG🎨`** (`gemini-2.0-flash-preview-image-generation`) - **Модель с генерацией изображений**

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
    PRO_CODE=<ваш_код_для_pro_доступа_опционально> # Установите этот код, чтобы включить команду /unlock_pro для доступа к модели 2.5 Pro
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
1. **Выберите модель генерации:** Нажмите `Модель: ...` → `2.0 Flash+IMG🎨`
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
- **Markdown:** Кнопка "Получить .MD �"
- **Текст:** Инлайн-кнопка "Скачать в формате .txt" (для длинных ответов)

## Команды

### Основные команды
- `/start` - 🚀 Перезапустить бота / Начать чат
- `/help` - ℹ️ Справка по возможностям бота
- `/unlock_pro <код>` - 🔑 Разблокировать доступ к модели `2.5 Pro💡`

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
1. Выберите модель `2.0 Flash+IMG🎨`
2. Напишите: "Нарисуй футуристический город на закате"
3. Получите сгенерированное изображение

### Редактирование изображений (Image → Image)
1. Выберите модель `2.0 Flash+IMG🎨`
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

> **💡 Подсказка:** Модель `2.0 Flash+IMG🎨` автоматически определяет, когда нужно генерировать изображения. Google Search и URL Context для неё отключены, так как они не поддерживаются.

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

-   **Необходимые секреты GitHub Actions:** `SERVER_SSH_KEY` (приватный SSH ключ), `SERVER_IP` (IP адрес сервера) и SERVER_SSH_PORT (опционально): SSH порт вашего сервера, если он отличается от стандартного порта 22. Если этот секрет не указан или пуст, будет использован порт 22.

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

This project implements a Telegram bot that uses the Google Gemini API to interact with users. The bot supports various Gemini models, **intelligent image generation and editing**, file processing, Google Search integration, quick tools for specific tasks, and flexible dialogue management.

## > Live bot available at [@degenerative_ai_bot](https://t.me/degenerative_ai_bot)

## Key Features

### 🎨 **Image Generation and Editing**
-   **Text → Image:** Simply write "Draw a cat in space" and get an image
-   **Image + Text → Image:** Upload a photo and ask "Change style to vintage" 
-   **Multi-step editing:** Step-by-step image modifications in dialogue
-   **Automatic detection:** Select `2.0 Flash+IMG🎨` model and the bot will automatically generate images

### 🧠 **Gemini Models Support**
-   **`2.5 Flash 🚀`** (`gemini-2.5-flash`) - Fast model for everyday tasks
-   **`2.5 Pro💡`** (`gemini-2.5-pro`) - Advanced model for complex tasks (access via `/unlock_pro`)
-   **`2.5 Flash Lite🐣`** (`gemini-2.5-flash-lite-preview-06-17`) - Lightweight version
-   **`2.0 Flash+IMG🎨`** (`gemini-2.0-flash-preview-image-generation`) - **Image generation model**

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
    PRO_CODE=<your_pro_access_code_optional> # Set this code to enable the /unlock_pro command for accessing the 2.5 Pro model
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
1. **Select generation model:** Press `Model: ...` → `2.0 Flash+IMG🎨`
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
- **Markdown:** "Get .MD �" button
- **Text:** Inline button "Download as .txt" (for long responses)

## Commands

### Main Commands
- `/start` - 🚀 Restart bot / Start chat
- `/help` - ℹ️ Help with bot features
- `/unlock_pro <code>` - 🔑 Unlock access to `2.5 Pro💡` model

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
1. Select model `2.0 Flash+IMG🎨`
2. Write: "Draw a futuristic city at sunset"
3. Receive generated image

### Image Editing (Image → Image)
1. Select model `2.0 Flash+IMG🎨`
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

> **💡 Tip:** Model `2.0 Flash+IMG🎨` automatically determines when to generate images. Google Search and URL Context are disabled for it as they are not supported.

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

-   **Required GitHub Actions Secrets:** `SERVER_SSH_KEY` (private SSH key), `SERVER_IP` (server IP address) and SERVER_SSH_PORT (optional): The SSH port of your server if it differs from the default port 22. If this secret is not provided or is empty, port 22 will be used.

-   **Important Notes:**
    *   **Systemd service:** The service file (e.g., `tg_gemini_bot.service`) must be created in `/etc/systemd/system/` beforehand and configured to run `gemini_bot.py` from the virtual environment.
    *   **Python version:** The deployment script targets Python 3.13.
    *   **`whitelist.txt`:** This file is excluded from synchronization to avoid overwriting an existing one on the server.
    *   **Permissions:** The script assumes it has permissions to install packages and manage `systemd` services on the server.

**Note:** You can also host the project for free on [pythonanywhere.com](https://www.pythonanywhere.com/), but automatic deployment via GitHub Actions is configured for a dedicated server with `systemd`.