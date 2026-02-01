# Учительский журнал (Web)

Веб-приложение на Python для оценок и посещаемости. Работает в браузере, хранит данные в SQLite.

## Возможности

- список учеников с краткой сводкой;
- карточка ученика: оценки, посещаемость, средние по предметам;
- быстрые формы добавления оценок и отметок посещаемости;
- автоматические расчёты средней оценки и процента посещаемости.
- отдельные роли: учитель (с инвайтом на админ‑панель) и ученик (просмотр своего профиля).

## Быстрый старт

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Откройте в браузере: `http://127.0.0.1:5000`

## Настройки

- `JOURNAL_DB_PATH` — путь к файлу базы данных SQLite (по умолчанию `data/journal.db`).
- `JOURNAL_SECRET` — секретный ключ для flash-сообщений (в продакшене обязательно поменять).
- `SUPABASE_URL` — URL проекта Supabase.
- `SUPABASE_ANON_KEY` — публичный ключ Supabase (anon).
- `SUPABASE_SERVICE_ROLE_KEY` — сервисный ключ Supabase (нужен для авто‑подтверждения регистрации).
- `SUPABASE_DB_URL` — строка подключения к Postgres в Supabase (если задана, используется Postgres вместо SQLite).
- `SUPABASE_POOLER_URL` — строка подключения к Transaction Pooler (рекомендуется для Vercel).
- `DATABASE_URL` — альтернативный URL подключения к Postgres (резервный вариант).
- `ADMIN_EMAILS` — список email через запятую, которым сразу выдаётся роль admin.
- `ADMIN_TELEGRAM_IDS` — список Telegram ID через запятую для роли admin.
- `INVITE_TTL_DAYS` — срок действия инвайта в днях (по умолчанию 7).
- `APP_BASE_URL` — базовый URL приложения для ссылок из Telegram (например, https://jornual.vercel.app).
- `TELEGRAM_BOT_TOKEN` — токен Telegram-бота.
- `TELEGRAM_BOT_USERNAME` — username бота без @.
- `TELEGRAM_WEBHOOK_SECRET` — секрет для URL вебхука (используется в пути).
- `TELEGRAM_TOKEN_TTL_MINUTES` — время жизни ссылки подтверждения в минутах (по умолчанию 15).
- `TELEGRAM_LOGIN_TTL_SECONDS` — время жизни подписи Telegram‑логина (по умолчанию 600 сек).
- `TELEGRAM_LOGIN_TOKEN_TTL_MINUTES` — время жизни ссылки входа из бота (по умолчанию 10 мин).

## Telegram-подтверждение

1) Создайте бота через @BotFather и получите токен.  
2) Укажите в переменных окружения `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`, `TELEGRAM_WEBHOOK_SECRET`.  
3) Вызовите `setWebhook`, чтобы Telegram слал апдейты на ваш домен:

```
https://api.telegram.org/bot<token>/setWebhook?url=https://<domain>/telegram/webhook/<secret>
```

4) В Supabase Auth отключите подтверждение email, чтобы авторизация не зависела от писем.

Также доступен вход через Telegram без почты — бот выдаёт ссылку для входа.
Для корректных ссылок укажите `APP_BASE_URL`.

## Деплой на Vercel

- Добавлены `api/index.py` и `vercel.json`.
- На Vercel база хранится в `/tmp/journal.db` (эфемерное хранилище). Для постоянных данных лучше подключить внешнюю БД и указать `JOURNAL_DB_PATH`.

## CLI-версия

Файл `journal.py` — старая консольная версия. Можно оставить как резерв или использовать для миграции данных.
