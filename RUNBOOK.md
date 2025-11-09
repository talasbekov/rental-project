# ZhilyeGO - Runbook

Это руководство по запуску проекта "с нуля".

## Требования

- Docker 24.0+
- Docker Compose 2.20+
- 2GB свободного места на диске
- Порты 5432, 6379, 8000 должны быть свободны

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd rental-project
```

### 2. Настройка окружения

Скопируйте файл с примерами переменных окружения:

```bash
cp .env.example .env
```

**ВАЖНО:** Откройте `.env` и обновите следующие значения:

```bash
# Обязательно изменить в production:
DJANGO_SECRET_KEY=your-very-strong-secret-key-here
ENCRYPTION_KEY=your-encryption-key-from-fernet

# Сгенерировать ENCRYPTION_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Сборка и запуск контейнеров

```bash
# Сборка образов
docker compose build --no-cache

# Запуск всех сервисов
docker compose up -d

# Проверка статуса
docker compose ps
```

### 4. Применение миграций и создание статики

```bash
# Миграции уже применяются автоматически при старте web-сервиса
# Но если нужно выполнить вручную:
docker compose exec web python manage.py migrate

# Статика также собирается автоматически
# Но если нужно пересобрать:
docker compose exec web python manage.py collectstatic --noinput
```

### 5. Создание суперпользователя

```bash
docker compose exec web python manage.py createsuperuser
```

Следуйте инструкциям для создания админа.

### 6. Проверка работы

Откройте в браузере:

- **Админка Django**: http://localhost:8000/admin/
- **API**: http://localhost:8000/api/v1/

## Проверка здоровья сервисов

```bash
# Проверка всех контейнеров
docker compose ps

# Логи всех сервисов
docker compose logs

# Логи конкретного сервиса
docker compose logs web
docker compose logs celery_worker
docker compose logs celery_beat

# Следить за логами в реальном времени
docker compose logs -f web
```

## Остановка и перезапуск

```bash
# Остановка всех сервисов
docker compose stop

# Перезапуск
docker compose restart

# Остановка и удаление контейнеров (данные в volumes сохраняются)
docker compose down

# Полная очистка (ВНИМАНИЕ: удаляет данные БД)
docker compose down -v
```

## Работа с базой данных

### Подключение к PostgreSQL

```bash
docker compose exec db psql -U zhilyego -d zhilyego
```

### Бэкап базы данных

```bash
docker compose exec db pg_dump -U zhilyego zhilyego > backup_$(date +%Y%m%d_%H%M%S).sql
```

### Восстановление из бэкапа

```bash
cat backup.sql | docker compose exec -T db psql -U zhilyego -d zhilyego
```

## Работа с Celery

### Проверка состояния Celery worker

```bash
docker compose exec celery_worker celery -A config.celery inspect active
docker compose exec celery_worker celery -A config.celery inspect stats
```

### Проверка запланированных задач (Celery Beat)

```bash
docker compose exec celery_beat celery -A config.celery inspect scheduled
```

### Ручной запуск задачи

```bash
docker compose exec web python manage.py shell
>>> from apps.bookings.tasks import expire_pending_bookings
>>> expire_pending_bookings.delay()
```

## Разработка

### Запуск тестов

```bash
# Установка dev-зависимостей
docker compose exec web pip install -r requirements-dev.txt

# Запуск всех тестов
docker compose exec web pytest

# Запуск с покрытием
docker compose exec web pytest --cov=apps

# Запуск конкретного теста
docker compose exec web pytest apps/bookings/tests/test_models.py
```

### Линтинг и форматирование

```bash
# Black
docker compose exec web black .

# isort
docker compose exec web isort .

# Flake8
docker compose exec web flake8 .
```

### Выполнение Django команд

```bash
# Любая manage.py команда
docker compose exec web python manage.py <command>

# Примеры:
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py showmigrations
docker compose exec web python manage.py shell
```

## Troubleshooting

### Проблема: Порт 8000 занят

```bash
# Найти процесс, занимающий порт
sudo lsof -i :8000

# Или изменить порт в docker-compose.yml
ports:
  - "8001:8000"
```

### Проблема: База данных не инициализируется

```bash
# Проверить логи БД
docker compose logs db

# Пересоздать volume
docker compose down -v
docker compose up -d
```

### Проблема: Celery worker не запускается

```bash
# Проверить подключение к Redis
docker compose exec redis redis-cli ping

# Проверить логи
docker compose logs celery_worker

# Перезапустить worker
docker compose restart celery_worker
```

### Проблема: Ошибки миграций

```bash
# Откат последней миграции
docker compose exec web python manage.py migrate app_name migration_name

# Сброс миграций (ОСТОРОЖНО)
docker compose down -v
docker compose up -d
```

## Production Deployment

Для production необходимо:

1. Изменить `.env`:
   - Установить `DJANGO_DEBUG=False`
   - Использовать сильный `DJANGO_SECRET_KEY`
   - Указать правильные `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS`

2. Использовать `docker-compose.prod.yml` (если есть)

3. Настроить nginx как reverse proxy

4. Настроить SSL/TLS сертификаты

5. Настроить мониторинг (Sentry, Prometheus, etc.)

6. Настроить регулярные бэкапы БД

## Полезные ссылки

- Django документация: https://docs.djangoproject.com/
- DRF документация: https://www.django-rest-framework.org/
- Celery документация: https://docs.celeryproject.org/
