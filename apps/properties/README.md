# Property Calendar & Seasonal Pricing API

Этот модуль предоставляет REST API для управления календарём доступности, сезонными тарифами и публичным отображением цен объектов недвижимости.

## Эндпоинты

### 0. Поиск объектов

- `GET /api/v1/properties/search/` — выдача объектов с фильтрами и сортировками.

Параметры фильтров (все опционально, комбинируются):
- `city` (icontains)
- `district` (icontains)
- `property_type` (id)
- `property_class` (exact)
- `rooms_min`, `rooms_max`
- `price_min`, `price_max` (по `base_price`)
- `guests` (минимальная вместимость `max_guests >= guests`)
- `amenities` — список id через запятую, объект должен содержать все перечисленные удобства
- `start`, `end` (YYYY-MM-DD) — исключить занятые/заблокированные на период объекты

Сортировка: параметр `ordering` принимает одно из `base_price`, `-base_price`, `created_at`, `-created_at`, `is_featured`, `-is_featured`, `rooms`, `-rooms`.

### 1. Блокировки календаря

- `GET /api/v1/properties/<id>/calendar/availability/` — список блокировок (фильтры: `start`, `end`, `availability_type`, `status`).
- `POST /api/v1/properties/<id>/calendar/availability/` — создать блокировку.
- `PATCH|PUT|DELETE /api/v1/properties/<id>/calendar/availability/{availability_id}/` — обновление/удаление.
- `POST /api/v1/properties/<id>/calendar/availability/bulk-delete/` — массовое удаление.

Payload (create):
```json
{
  "start_date": "2025-11-01",
  "end_date": "2025-11-05",
  "status": "blocked",
  "availability_type": "manual_block",
  "reason": "Личные планы",
  "color_code": "#FFB347"
}
```

### 2. Сезонные тарифы

- `GET /api/v1/properties/<id>/calendar/seasonal-rates/`
- `POST /api/v1/properties/<id>/calendar/seasonal-rates/`
- `PATCH|PUT|DELETE /api/v1/properties/<id>/calendar/seasonal-rates/{rate_id}/`
- `POST /api/v1/properties/<id>/calendar/seasonal-rates/bulk-delete/`

Payload (create):
```json
{
  "start_date": "2025-12-20",
  "end_date": "2026-01-08",
  "price_per_night": "45000.00",
  "min_nights": 3,
  "max_nights": 10,
  "description": "Новогодний период",
  "color_code": "#B19CD9"
}
```

### 3. Настройки календаря

- `GET /api/v1/properties/<id>/calendar/settings/`
- `PUT|PATCH /api/v1/properties/<id>/calendar/settings/`

Поля: `default_price`, `advance_notice`, `booking_window`, `allowed_check_in_days`, `allowed_check_out_days`, `auto_apply_seasonal`.

### 4. Публичный календарь

- `GET /api/v1/properties/<id>/calendar/public/?start=2025-11-01&end=2025-11-10`

Ответ:
```json
{
  "property_id": 1,
  "dates": [
    {
      "date": "2025-11-01",
      "status": "available",
      "final_price": "25000.00",
      "pricing_source": "base",
      "min_nights": 1
    }
  ]
}
```

## Права доступа

- **Риелтор** / **Супер Админ** — управление календарём своих объектов.
- **Суперпользователь платформы** — полный доступ.
- **Гости** — только публичный эндпоинт `/calendar/public/`.

## Валидация

- Нельзя создавать блокировки, перекрывающие существующие брони/блокировки.
- Повторяющиеся блокировки пока не поддерживаются (запросы с `repeat_rule != none` отклоняются).
- Сезонные тарифы проверяются на корректность диапазона дат и `min_nights/max_nights`.

## Тесты

Автотесты расположены в `apps/properties/tests/test_calendar_api.py` и включают сценарии:

- Создание блокировок календаря.
- Защита от пересечений.
- Создание сезонных тарифов.
- Обновление настроек календаря.
- Публичный календарь с проверкой статусов и цен.

## Интеграция на фронтенде

- Списки и карточки календаря могут использовать HEX цвета (`color_code`) для визуализации.
- Параметры `start` / `end` обязательны для всех запросов календаря.
- В ответах календаря присутствуют вычисленные поля `status_display`, `availability_type_display`, `pricing_source`.
