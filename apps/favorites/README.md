# Favorites API Documentation

Полнофункциональное API для управления избранными объектами недвижимости.

## Endpoints

### 1. Список избранных

**GET** `/api/v1/favorites/`

Получить список всех избранных объектов текущего пользователя.

**Query Parameters:**
- `city` (string, optional) - фильтр по городу
- `district` (string, optional) - фильтр по району
- `min_price` (decimal, optional) - минимальная цена
- `max_price` (decimal, optional) - максимальная цена

**Response:**
```json
[
  {
    "id": 1,
    "user_id": 42,
    "property_id": 123,
    "property": {
      "id": 123,
      "title": "Уютная 2-комнатная квартира",
      "slug": "uyutnaya-2-komnatnaya-kvartira",
      "city": "Астана",
      "district": "Есильский",
      "base_price": "5000.00",
      "currency": "KZT",
      "property_class": "business",
      "rooms": 2,
      "max_guests": 4,
      "status": "active",
      "average_rating": 4.8,
      "reviews_count": 23,
      "main_photo_url": "/media/properties/123/main.jpg"
    },
    "created_at": "2025-10-20T14:30:00Z"
  }
]
```

**Пример запроса:**
```bash
# Все избранные
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/favorites/

# Фильтр по городу и цене
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/favorites/?city=Астана&min_price=3000&max_price=7000"
```

---

### 2. Добавить в избранное

**POST** `/api/v1/favorites/`

Добавить объект в избранное.

**Request Body:**
```json
{
  "property": 123
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "user_id": 42,
  "property_id": 123,
  "property": { /* полная информация об объекте */ },
  "created_at": "2025-10-27T20:15:00Z"
}
```

**Errors:**
- **400** - Объект уже в избранном
- **404** - Объект не найден

**Пример запроса:**
```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"property": 123}' \
  http://localhost:8000/api/v1/favorites/
```

---

### 3. Удалить из избранного

**DELETE** `/api/v1/favorites/{id}/`

Удалить объект из избранного по ID записи Favorite.

**Response (204 No Content)**

**Пример запроса:**
```bash
curl -X DELETE \
  -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/favorites/1/
```

---

### 4. Переключить избранное (Toggle)

**POST** `/api/v1/favorites/toggle/`

Умный метод: если объект в избранном - удаляет, если нет - добавляет.

**Request Body:**
```json
{
  "property_id": 123
}
```

**Response (200 OK или 201 Created):**

При добавлении:
```json
{
  "action": "added",
  "favorite": {
    "id": 1,
    "user_id": 42,
    "property_id": 123,
    "property": { /* детали объекта */ },
    "created_at": "2025-10-27T20:15:00Z"
  },
  "message": "Объект добавлен в избранное"
}
```

При удалении:
```json
{
  "action": "removed",
  "property_id": 123,
  "message": "Объект удален из избранного"
}
```

**Пример запроса:**
```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"property_id": 123}' \
  http://localhost:8000/api/v1/favorites/toggle/
```

**Использование на Frontend:**
```javascript
// React/Vue пример
const toggleFavorite = async (propertyId) => {
  const response = await fetch('/api/v1/favorites/toggle/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ property_id: propertyId })
  });

  const data = await response.json();

  if (data.action === 'added') {
    console.log('Добавлено в избранное');
    setIsFavorite(true);
  } else {
    console.log('Удалено из избранного');
    setIsFavorite(false);
  }
};
```

---

### 5. Массовое удаление

**POST** `/api/v1/favorites/bulk-delete/`

Удалить несколько избранных объектов одновременно.

**Request Body:**
```json
{
  "favorite_ids": [1, 2, 3, 4, 5]
}
```

**Response (200 OK):**
```json
{
  "deleted": 5,
  "message": "Удалено 5 избранных"
}
```

**Пример запроса:**
```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"favorite_ids": [1, 2, 3]}' \
  http://localhost:8000/api/v1/favorites/bulk-delete/
```

---

### 6. Проверить наличие в избранном

**GET** `/api/v1/favorites/check/{property_id}/`

Быстрая проверка, находится ли объект в избранном у текущего пользователя.

**Response (200 OK):**

Если в избранном:
```json
{
  "is_favorite": true,
  "favorite_id": 42
}
```

Если не в избранном:
```json
{
  "is_favorite": false,
  "favorite_id": null
}
```

**Пример запроса:**
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/favorites/check/123/
```

**Использование на Frontend:**
```javascript
// Проверка при загрузке карточки объекта
useEffect(() => {
  const checkFavorite = async () => {
    const response = await fetch(`/api/v1/favorites/check/${propertyId}/`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    setIsFavorite(data.is_favorite);
    setFavoriteId(data.favorite_id);
  };

  checkFavorite();
}, [propertyId]);
```

---

### 7. Статистика по избранным

**GET** `/api/v1/favorites/stats/`

Получить статистику по избранным объектам пользователя.

**Response (200 OK):**
```json
{
  "total": 15,
  "by_city": [
    {
      "property__city": "Астана",
      "count": 12
    },
    {
      "property__city": "Алматы",
      "count": 3
    }
  ],
  "average_price": 6250.50
}
```

**Пример запроса:**
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/favorites/stats/
```

---

## Permissions

Все endpoints требуют авторизации (`IsAuthenticated`).

Пользователь может видеть и управлять только своими избранными.

---

## Оптимизация

API оптимизирован с использованием:
- `select_related('user', 'property')` - JOIN для связанных таблиц
- `prefetch_related('property__reviews', 'property__photos')` - оптимизация N+1 запросов
- Фильтрация только активных объектов (`status='active'`)

---

## Примеры интеграции

### React Component

```jsx
import { useState, useEffect } from 'react';

function FavoriteButton({ propertyId }) {
  const [isFavorite, setIsFavorite] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Проверяем при загрузке
    fetch(`/api/v1/favorites/check/${propertyId}/`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => r.json())
      .then(data => setIsFavorite(data.is_favorite));
  }, [propertyId]);

  const handleToggle = async () => {
    setLoading(true);

    const response = await fetch('/api/v1/favorites/toggle/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ property_id: propertyId })
    });

    const data = await response.json();
    setIsFavorite(data.action === 'added');
    setLoading(false);
  };

  return (
    <button
      onClick={handleToggle}
      disabled={loading}
      className={isFavorite ? 'favorite-active' : 'favorite-inactive'}
    >
      {isFavorite ? '❤️' : '🤍'} {isFavorite ? 'В избранном' : 'Добавить в избранное'}
    </button>
  );
}
```

### Vue Component

```vue
<template>
  <button
    @click="toggleFavorite"
    :disabled="loading"
    :class="{'favorite-active': isFavorite}"
  >
    {{ isFavorite ? '❤️' : '🤍' }}
    {{ isFavorite ? 'В избранном' : 'Добавить' }}
  </button>
</template>

<script>
export default {
  props: ['propertyId'],
  data() {
    return {
      isFavorite: false,
      loading: false
    }
  },
  mounted() {
    this.checkFavorite();
  },
  methods: {
    async checkFavorite() {
      const response = await fetch(`/api/v1/favorites/check/${this.propertyId}/`, {
        headers: { 'Authorization': `Bearer ${this.token}` }
      });
      const data = await response.json();
      this.isFavorite = data.is_favorite;
    },
    async toggleFavorite() {
      this.loading = true;

      const response = await fetch('/api/v1/favorites/toggle/', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ property_id: this.propertyId })
      });

      const data = await response.json();
      this.isFavorite = data.action === 'added';
      this.loading = false;
    }
  }
}
</script>
```

---

## Error Handling

Все endpoints возвращают стандартные HTTP коды:
- **200 OK** - успешная операция
- **201 Created** - объект создан
- **204 No Content** - объект удален
- **400 Bad Request** - невалидные данные
- **401 Unauthorized** - не авторизован
- **404 Not Found** - объект не найден

Формат ошибок:
```json
{
  "detail": "Описание ошибки"
}
```

или

```json
{
  "field_name": ["Ошибка валидации поля"]
}
```

---

## Testing

```bash
# Запуск тестов
python manage.py test apps.favorites

# Создать тестовые данные
python manage.py shell
from apps.users.models import CustomUser
from apps.properties.models import Property
from apps.favorites.models import Favorite

user = CustomUser.objects.first()
property = Property.objects.first()
favorite = Favorite.objects.create(user=user, property=property)
```
