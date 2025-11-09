# Telegram Bot Production Setup Guide

Полное руководство по настройке и запуску Telegram-бота ЖильеGO в продакшен-режиме с webhook.

## Содержание

1. [Требования](#требования)
2. [Быстрый старт](#быстрый-старт)
3. [Детальная настройка](#детальная-настройка)
4. [Управление webhook](#управление-webhook)
5. [Troubleshooting](#troubleshooting)
6. [Архитектура](#архитектура)

---

## Требования

### Обязательно

- Docker & Docker Compose
- Telegram Bot Token (получить у @BotFather)
- Порты 8000, 4040, 5432, 6379 свободны

### Опционально

- ngrok authtoken (для персистентных URL)

---

## Быстрый старт

### 1. Подготовка окружения

```bash
# Копируем .env
cp .env.example .env

# Редактируем .env и устанавливаем TELEGRAM_BOT_TOKEN
nano .env
```

Обязательно установите:
```bash
TELEGRAM_BOT_TOKEN=your-bot-token-from-botfather
```

### 2. Запуск (автоматический режим)

```bash
# Автоматический запуск с webhook
./scripts/start_bot_production.sh
```

Этот скрипт:
- ✅ Запустит все Docker контейнеры
- ✅ Дождется готовности сервисов
- ✅ Получит ngrok URL
- ✅ Автоматически настроит webhook
- ✅ Покажет финальный URL webhook

### 3. Проверка работы

Отправьте `/start` вашему боту в Telegram!

---

## Детальная настройка

### Шаг 1: Создание бота в Telegram

1. Найдите @BotFather в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям
4. Сохраните токен

### Шаг 2: Конфигурация .env

```bash
############################
# Bots & External APIs
############################
TELEGRAM_BOT_TOKEN=7302267102:AAG_F7yUjzxctn0rVOUebQi1rCzXuEPZUEI
BOT_SERVICE_USERNAME=bot_user
WEBHOOK_SECRET=your-webhook-secret-token

############################
# ngrok (опционально)
############################
NGROK_AUTHTOKEN=your-ngrok-authtoken
```

### Шаг 3: Получение ngrok authtoken (опционально)

1. Регистрация: https://dashboard.ngrok.com/signup
2. Получение токена: https://dashboard.ngrok.com/get-started/your-authtoken
3. Добавьте в `.env`:
   ```bash
   NGROK_AUTHTOKEN=your_token_here
   ```

### Шаг 4: Запуск контейнеров

```bash
# Сборка образов
docker compose build --no-cache

# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps
```

Все сервисы должны быть в состоянии "healthy" или "running":
- ✅ rental_db (healthy)
- ✅ rental_redis (healthy)
- ✅ rental_web (healthy)
- ✅ rental_celery_worker (running)
- ✅ rental_celery_beat (running)
- ✅ rental_ngrok (running)

### Шаг 5: Получение ngrok URL

```bash
# Через API
curl http://localhost:4040/api/tunnels | jq '.tunnels[0].public_url'

# Или через веб-интерфейс
# Откройте в браузере: http://localhost:4040
```

Вы получите URL вида: `https://xxxx-xx-xxx-xxx-xxx.ngrok-free.app`

### Шаг 6: Настройка webhook

#### Автоматический метод (рекомендуется)

```bash
# Автоматическое определение ngrok URL и настройка webhook
python3 scripts/setup_telegram_webhook.py auto
```

#### Ручной метод

```bash
# С указанием URL вручную
python3 scripts/setup_telegram_webhook.py set --url https://your-ngrok-url.ngrok-free.app/telegram/webhook/

# С секретным токеном
python3 scripts/setup_telegram_webhook.py set \
    --url https://your-ngrok-url.ngrok-free.app/telegram/webhook/ \
    --token your-secret-token
```

#### Проверка webhook

```bash
# Получить информацию о webhook
python3 scripts/setup_telegram_webhook.py info
```

Ожидаемый вывод:
```
Current webhook URL: https://xxxx.ngrok-free.app/telegram/webhook/
Pending updates: 0
Last error: None
Max connections: 40
```

---

## Управление webhook

### Просмотр информации

```bash
python3 scripts/setup_telegram_webhook.py info
```

### Установка webhook

```bash
# Автоматически (с ngrok)
python3 scripts/setup_telegram_webhook.py auto

# Вручную
python3 scripts/setup_telegram_webhook.py set --url https://your-domain.com/telegram/webhook/
```

### Удаление webhook (переход на polling)

```bash
python3 scripts/setup_telegram_webhook.py delete
```

### Проверка здоровья бота

```bash
# HTTP запрос
curl http://localhost:8000/telegram/health/

# Или через ngrok
curl https://your-ngrok-url.ngrok-free.app/telegram/health/
```

Ожидаемый ответ:
```json
{
  "status": "healthy",
  "bot": {
    "id": 123456789,
    "username": "YourBotName",
    "name": "Your Bot Display Name"
  }
}
```

---

## Troubleshooting

### Проблема: ngrok URL не определяется

**Симптомы:**
```
❌ ngrok not running or URL not found
```

**Решение:**
```bash
# Проверьте статус ngrok
docker compose logs ngrok

# Перезапустите ngrok
docker compose restart ngrok

# Подождите 5-10 секунд и проверьте снова
curl http://localhost:4040/api/tunnels
```

### Проблема: Webhook не устанавливается

**Симптомы:**
```
❌ Error setting webhook: Conflict: can't use getUpdates method while webhook is active
```

**Решение:**
```bash
# Удалите существующий webhook
python3 scripts/setup_telegram_webhook.py delete

# Подождите 5 секунд
sleep 5

# Установите заново
python3 scripts/setup_telegram_webhook.py auto
```

### Проблема: Бот не отвечает на сообщения

**Проверки:**

1. **Webhook установлен?**
   ```bash
   python3 scripts/setup_telegram_webhook.py info
   ```

2. **Web сервис работает?**
   ```bash
   docker compose ps web
   docker compose logs web | tail -50
   ```

3. **ngrok работает?**
   ```bash
   curl http://localhost:4040/api/tunnels
   ```

4. **Логи webhook запросов:**
   ```bash
   # Откройте ngrok dashboard
   open http://localhost:4040

   # Или смотрите логи Django
   docker compose logs -f web
   ```

### Проблема: Ошибка "TELEGRAM_BOT_TOKEN not configured"

**Решение:**
```bash
# Проверьте .env
cat .env | grep TELEGRAM_BOT_TOKEN

# Если пусто, добавьте:
echo "TELEGRAM_BOT_TOKEN=your-token-here" >> .env

# Перезапустите контейнеры
docker compose restart web
```

### Проблема: Порт 4040 занят

**Решение:**
```bash
# Найдите процесс
lsof -i :4040

# Или измените порт в docker-compose.yml
# ngrok:
#   ports:
#     - "4041:4040"  # Используйте 4041 вместо 4040
```

### Проблема: "Invalid JSON" в логах webhook

**Причина:** Telegram отправляет некорректные данные или проблема с кодировкой

**Решение:**
```bash
# Включите debug логирование
# В .env добавьте:
echo "DJANGO_DEBUG=True" >> .env

# Перезапустите
docker compose restart web

# Смотрите детальные логи
docker compose logs -f web
```

---

## Архитектура

### Компоненты системы

```
┌─────────────────┐
│   Telegram      │
│    Servers      │
└────────┬────────┘
         │ HTTPS POST
         ▼
┌─────────────────┐
│     ngrok       │  (публичный URL)
│  xxxx.ngrok.app │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Django Web    │  (webhook endpoint)
│  /telegram/     │  /telegram/webhook/
│   webhook/      │  /telegram/health/
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Bot Handlers   │  (apps/telegrambot/bot.py)
│  - Commands     │  build_application()
│  - Callbacks    │  process_update()
│  - Messages     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Business      │
│    Logic        │  (services, models)
└─────────────────┘
```

### Поток обработки сообщения

1. **Пользователь** отправляет сообщение боту
2. **Telegram** отправляет POST запрос на webhook URL
3. **ngrok** проксирует запрос на локальный Django
4. **Django webhook view** (`telegram_webhook`) получает данные
5. **Bot application** обрабатывает Update через handlers
6. **Business logic** выполняет нужные действия
7. **Bot** отправляет ответ пользователю через Telegram API

### Файловая структура

```
rental-project/
├── apps/
│   └── telegrambot/
│       ├── bot.py                 # Основная логика бота
│       ├── views.py               # Webhook views (НОВОЕ)
│       ├── urls.py                # URL routing (НОВОЕ)
│       ├── models.py              # TelegramProfile, VerificationCode
│       ├── services.py            # Бизнес-логика
│       └── management/
│           └── commands/
│               └── telegram_bot.py  # Polling mode (deprecated)
├── scripts/
│   ├── setup_telegram_webhook.py    # Управление webhook (НОВОЕ)
│   └── start_bot_production.sh      # Автозапуск (НОВОЕ)
├── config/
│   └── urls.py                      # + telegram/ route (ОБНОВЛЕНО)
├── docker-compose.yml               # + ngrok service (ОБНОВЛЕНО)
└── .env.example                     # + NGROK_AUTHTOKEN (ОБНОВЛЕНО)
```

---

## Полезные команды

### Мониторинг

```bash
# Логи всех сервисов
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f web
docker compose logs -f ngrok

# Статус контейнеров
docker compose ps

# Ресурсы
docker stats
```

### Управление

```bash
# Перезапуск сервиса
docker compose restart web

# Пересборка после изменения кода
docker compose build web
docker compose up -d web

# Остановка всех сервисов
docker compose stop

# Полная очистка
docker compose down -v
```

### Отладка

```bash
# Войти в контейнер
docker compose exec web bash

# Запустить Django shell
docker compose exec web python manage.py shell

# Проверить миграции
docker compose exec web python manage.py showmigrations

# Выполнить миграции
docker compose exec web python manage.py migrate
```

---

## Production Deployment

Для реального production (не ngrok):

### 1. Используйте реальный домен

```bash
# Вместо ngrok используйте свой домен с SSL
WEBHOOK_URL=https://yourdomain.com/telegram/webhook/
```

### 2. Настройте nginx

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /telegram/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. Установите webhook

```bash
python3 scripts/setup_telegram_webhook.py set \
    --url https://yourdomain.com/telegram/webhook/ \
    --token your-secret-token
```

### 4. Мониторинг

- Настройте Sentry для отслеживания ошибок
- Используйте Prometheus + Grafana для метрик
- Настройте логирование в ELK stack

---

## Контакты и поддержка

- Документация Django: https://docs.djangoproject.com/
- Telegram Bot API: https://core.telegram.org/bots/api
- python-telegram-bot: https://docs.python-telegram-bot.org/
- ngrok docs: https://ngrok.com/docs

---

**Последнее обновление:** 2025-10-30

**Версия:** 1.0.0
