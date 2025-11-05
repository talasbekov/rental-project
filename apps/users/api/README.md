# Super Admin API Documentation

Комплексный API для управления риелторами и аналитикой агентства недвижимости.

## Обзор

Super Admin API предоставляет владельцу агентства (super_admin) полный контроль над:
- **Управление командой**: создание, редактирование, активация/деактивация риелторов
- **Аналитика**: производительность риелторов, топ-объекты, доходы
- **Агентство**: просмотр информации и статистики агентства

## Аутентификация

Все endpoints требуют:
1. JWT токен в заголовке: `Authorization: Bearer <token>`
2. Роль пользователя: `super_admin` или `superuser`

```bash
# Пример заголовка
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

---

## Endpoints

### 1. Список риелторов агентства

**GET** `/api/v1/super-admin/realtors/`

Получить список всех риелторов в агентстве текущего Super Admin.

**Response (200 OK):**
```json
[
  {
    "id": 5,
    "email": "realtor@example.com",
    "username": "Иван Петров",
    "phone": "+77011234567",
    "role": "realtor",
    "role_display": "Риелтор",
    "agency_id": 1,
    "avatar": null,
    "is_active": true,
    "is_email_verified": true,
    "is_phone_verified": true,
    "last_activity_at": "2025-10-27T10:30:00Z",
    "created_at": "2025-01-15T09:00:00Z",
    "properties_count": 12
  }
]
```

**Пример запроса:**
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/super-admin/realtors/
```

---

### 2. Детали риелтора

**GET** `/api/v1/super-admin/realtors/{id}/`

Получить подробную информацию о конкретном риелторе.

**Response (200 OK):**
```json
{
  "id": 5,
  "email": "realtor@example.com",
  "username": "Иван Петров",
  "phone": "+77011234567",
  "role": "realtor",
  "role_display": "Риелтор",
  "agency_id": 1,
  "agency_name": "Astana Elite Realty",
  "avatar": "/media/avatars/realtor_5.jpg",
  "telegram_id": 123456789,
  "is_active": true,
  "is_email_verified": true,
  "is_phone_verified": true,
  "is_identity_verified": false,
  "last_activity_at": "2025-10-27T10:30:00Z",
  "created_at": "2025-01-15T09:00:00Z",
  "updated_at": "2025-10-20T14:45:00Z",
  "properties_count": 12,
  "bookings_count": 48
}
```

**Пример запроса:**
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/super-admin/realtors/5/
```

---

### 3. Создать риелтора

**POST** `/api/v1/super-admin/realtors/`

Создать нового риелтора в агентстве.

**Request Body:**
```json
{
  "email": "newrealtor@example.com",
  "username": "Алексей Сидоров",
  "phone": "+77012345678",
  "password": "SecurePassword123!",
  "telegram_id": 987654321
}
```

**Response (201 Created):**
```json
{
  "id": 6,
  "email": "newrealtor@example.com",
  "username": "Алексей Сидоров",
  "phone": "+77012345678",
  "role": "realtor",
  "role_display": "Риелтор",
  "agency_id": 1,
  "agency_name": "Astana Elite Realty",
  "avatar": null,
  "telegram_id": 987654321,
  "is_active": true,
  "is_email_verified": false,
  "is_phone_verified": false,
  "is_identity_verified": false,
  "created_at": "2025-10-27T15:00:00Z",
  "updated_at": "2025-10-27T15:00:00Z",
  "properties_count": 0,
  "bookings_count": 0
}
```

**Errors:**
- **400** - Превышен лимит риелторов агентства
- **400** - Email или телефон уже используется

**Пример запроса:**
```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newrealtor@example.com",
    "username": "Алексей Сидоров",
    "phone": "+77012345678",
    "password": "SecurePassword123!"
  }' \
  http://localhost:8000/api/v1/super-admin/realtors/
```

---

### 4. Обновить риелтора

**PATCH** `/api/v1/super-admin/realtors/{id}/`

Обновить информацию о риелторе (частичное обновление).

**Request Body:**
```json
{
  "username": "Иван Петрович",
  "telegram_id": 111222333,
  "is_phone_verified": true
}
```

**Response (200 OK):**
```json
{
  "id": 5,
  "email": "realtor@example.com",
  "username": "Иван Петрович",
  "phone": "+77011234567",
  "role": "realtor",
  "telegram_id": 111222333,
  "is_active": true,
  "is_email_verified": true,
  "is_phone_verified": true,
  ...
}
```

**Пример запроса:**
```bash
curl -X PATCH \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"username": "Иван Петрович"}' \
  http://localhost:8000/api/v1/super-admin/realtors/5/
```

---

### 5. Деактивировать риелтора

**POST** `/api/v1/super-admin/realtors/{id}/deactivate/`

Временно деактивировать риелтора (запретить вход, сохранив данные).

**Response (200 OK):**
```json
{
  "message": "Риелтор realtor@example.com деактивирован.",
  "realtor": {
    "id": 5,
    "email": "realtor@example.com",
    "is_active": false,
    ...
  }
}
```

**Errors:**
- **400** - Риелтор уже деактивирован
- **403** - Нет прав на управление этим риелтором

**Пример запроса:**
```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/super-admin/realtors/5/deactivate/
```

---

### 6. Активировать риелтора

**POST** `/api/v1/super-admin/realtors/{id}/activate/`

Активировать ранее деактивированного риелтора.

**Response (200 OK):**
```json
{
  "message": "Риелтор realtor@example.com активирован.",
  "realtor": {
    "id": 5,
    "email": "realtor@example.com",
    "is_active": true,
    ...
  }
}
```

**Пример запроса:**
```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/super-admin/realtors/5/activate/
```

---

### 7. Статистика риелтора

**GET** `/api/v1/super-admin/realtors/{id}/stats/`

Получить детальную статистику производительности риелтора.

**Query Parameters:**
- `start` (YYYY-MM-DD, optional) - начало периода
- `end` (YYYY-MM-DD, optional) - конец периода

**Response (200 OK):**
```json
{
  "realtor_id": 5,
  "realtor_name": "Иван Петров",
  "realtor_email": "realtor@example.com",
  "properties_count": 12,
  "active_properties": 10,
  "total_bookings": 48,
  "confirmed_bookings": 40,
  "completed_bookings": 35,
  "cancelled_bookings": 3,
  "total_revenue": "2850000.00",
  "average_booking_value": "71250.00",
  "period_start": "2025-01-01",
  "period_end": "2025-10-31"
}
```

**Пример запроса:**
```bash
# За все время
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/super-admin/realtors/5/stats/

# За период
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/super-admin/realtors/5/stats/?start=2025-01-01&end=2025-10-31"
```

---

### 8. Информация об агентстве

**GET** `/api/v1/super-admin/agency/`

Получить информацию об агентстве текущего Super Admin.

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "name": "Astana Elite Realty",
    "description": "Премиум агентство недвижимости в Астане",
    "city": "Астана",
    "address": "ул. Мангилик Ел, 55",
    "phone": "+77172555000",
    "email": "info@aer.kz",
    "website": "https://aer.kz",
    "telegram_chat_id": null,
    "commission_rate": "12.00",
    "properties_limit": 0,
    "realtors_limit": 20,
    "owner_id": 3,
    "owner_email": "admin@aer.kz",
    "is_active": true,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-10-15T10:30:00Z",
    "realtors_count": 8,
    "properties_count": 45
  }
]
```

**Пример запроса:**
```bash
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/super-admin/agency/
```

---

### 9. Статистика агентства

**GET** `/api/v1/super-admin/agency/stats/`

Получить агрегированную статистику по всем риелторам агентства.

**Query Parameters:**
- `start` (YYYY-MM-DD, optional) - начало периода
- `end` (YYYY-MM-DD, optional) - конец периода

**Response (200 OK):**
```json
{
  "agency_id": 1,
  "agency_name": "Astana Elite Realty",
  "total_realtors": 8,
  "active_realtors": 7,
  "total_properties": 50,
  "active_properties": 45,
  "total_bookings": 240,
  "confirmed_bookings": 200,
  "completed_bookings": 180,
  "total_revenue": "15000000.00",
  "average_booking_value": "75000.00"
}
```

**Пример запроса:**
```bash
# За все время
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/super-admin/agency/stats/

# За период
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/super-admin/agency/stats/?start=2025-01-01&end=2025-10-31"
```

---

### 10. ТОП-исполнители

**GET** `/api/v1/super-admin/agency/top-performers/`

Получить рейтинг лучших риелторов и объектов агентства.

**Query Parameters:**
- `limit` (int, default 5) - количество элементов в топе
- `period` (int, default 30) - период в днях

**Response (200 OK):**
```json
{
  "period_days": 30,
  "start_date": "2025-09-27",
  "top_realtors": [
    {
      "realtor_id": 5,
      "realtor_name": "Иван Петров",
      "realtor_email": "realtor@example.com",
      "revenue": 850000.00
    },
    {
      "realtor_id": 7,
      "realtor_name": "Мария Иванова",
      "realtor_email": "maria@example.com",
      "revenue": 720000.00
    }
  ],
  "top_properties": [
    {
      "property_id": 42,
      "property_title": "Luxury Penthouse в центре",
      "owner_email": "realtor@example.com",
      "bookings_count": 15
    },
    {
      "property_id": 38,
      "property_title": "Двушка с видом на Байтерек",
      "owner_email": "maria@example.com",
      "bookings_count": 12
    }
  ]
}
```

**Пример запроса:**
```bash
# ТОП-5 за 30 дней
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/v1/super-admin/agency/top-performers/

# ТОП-10 за 90 дней
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/super-admin/agency/top-performers/?limit=10&period=90"
```

---

## Permissions

### Кто имеет доступ?

1. **Super Admin** (`role=super_admin`):
   - Видит и управляет только своим агентством и его риелторами
   - Не может просматривать данные других агентств

2. **Platform Superuser** (`role=superuser` или `is_superuser=True`):
   - Полный доступ ко всем агентствам и риелторам
   - Административный доступ

### Проверка прав

```python
# В Django views/serializers
if user.is_super_admin():
    # Доступ к своему агентству
    agency = user.agency
    realtors = agency.employees.filter(role='realtor')

if user.is_platform_superuser():
    # Доступ ко всем данным
    all_agencies = RealEstateAgency.objects.all()
```

---

## Ограничения

### Лимиты агентства

При создании риелтора проверяется `agency.realtors_limit`:
- Если `realtors_limit = 0` - безлимитно
- Если `realtors_limit > 0` - проверяется текущее количество активных риелторов

**Ошибка при превышении лимита:**
```json
{
  "detail": "Достигнут лимит риелторов для агентства (20). Удалите неактивных или свяжитесь с поддержкой."
}
```

### Валидация

- **Email**: уникальный в системе
- **Phone**: уникальный в системе
- **Password**: минимум 8 символов

---

## Примеры интеграции

### React/Next.js Dashboard

```jsx
import { useState, useEffect } from 'react';

function RealtorsManagement() {
  const [realtors, setRealtors] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchRealtors();
  }, []);

  const fetchRealtors = async () => {
    setLoading(true);
    const response = await fetch('/api/v1/super-admin/realtors/', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    });
    const data = await response.json();
    setRealtors(data);
    setLoading(false);
  };

  const createRealtor = async (formData) => {
    const response = await fetch('/api/v1/super-admin/realtors/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(formData)
    });

    if (response.ok) {
      const newRealtor = await response.json();
      setRealtors([...realtors, newRealtor]);
      return true;
    }
    return false;
  };

  const toggleRealtorStatus = async (realtorId, isActive) => {
    const action = isActive ? 'deactivate' : 'activate';
    const response = await fetch(
      `/api/v1/super-admin/realtors/${realtorId}/${action}/`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      }
    );

    if (response.ok) {
      fetchRealtors(); // Refresh list
    }
  };

  return (
    <div>
      <h1>Управление риелторами</h1>
      {loading ? (
        <p>Загрузка...</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Email</th>
              <th>Имя</th>
              <th>Объектов</th>
              <th>Статус</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {realtors.map(realtor => (
              <tr key={realtor.id}>
                <td>{realtor.email}</td>
                <td>{realtor.username}</td>
                <td>{realtor.properties_count}</td>
                <td>{realtor.is_active ? '✅ Активен' : '❌ Неактивен'}</td>
                <td>
                  <button onClick={() => toggleRealtorStatus(realtor.id, realtor.is_active)}>
                    {realtor.is_active ? 'Деактивировать' : 'Активировать'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

### Analytics Dashboard

```jsx
import { useState, useEffect } from 'react';
import { Line, Bar } from 'react-chartjs-2';

function AgencyAnalytics() {
  const [stats, setStats] = useState(null);
  const [topPerformers, setTopPerformers] = useState(null);

  useEffect(() => {
    fetchStats();
    fetchTopPerformers();
  }, []);

  const fetchStats = async () => {
    const response = await fetch('/api/v1/super-admin/agency/stats/', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    });
    const data = await response.json();
    setStats(data);
  };

  const fetchTopPerformers = async () => {
    const response = await fetch('/api/v1/super-admin/agency/top-performers/', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    });
    const data = await response.json();
    setTopPerformers(data);
  };

  if (!stats || !topPerformers) return <p>Загрузка...</p>;

  return (
    <div>
      <h1>Аналитика агентства: {stats.agency_name}</h1>

      <div className="stats-grid">
        <div className="stat-card">
          <h3>Риелторов</h3>
          <p className="stat-value">{stats.active_realtors} / {stats.total_realtors}</p>
        </div>

        <div className="stat-card">
          <h3>Объектов</h3>
          <p className="stat-value">{stats.active_properties} / {stats.total_properties}</p>
        </div>

        <div className="stat-card">
          <h3>Бронирований</h3>
          <p className="stat-value">{stats.total_bookings}</p>
        </div>

        <div className="stat-card">
          <h3>Доход</h3>
          <p className="stat-value">{stats.total_revenue.toLocaleString()} ₸</p>
        </div>
      </div>

      <div className="top-performers">
        <h2>ТОП-5 риелторов по доходу (30 дней)</h2>
        <Bar
          data={{
            labels: topPerformers.top_realtors.map(r => r.realtor_name),
            datasets: [{
              label: 'Доход (₸)',
              data: topPerformers.top_realtors.map(r => r.revenue),
              backgroundColor: 'rgba(54, 162, 235, 0.6)'
            }]
          }}
        />
      </div>

      <div className="top-properties">
        <h2>ТОП-5 объектов по бронированиям (30 дней)</h2>
        <Bar
          data={{
            labels: topPerformers.top_properties.map(p => p.property_title),
            datasets: [{
              label: 'Бронирований',
              data: topPerformers.top_properties.map(p => p.bookings_count),
              backgroundColor: 'rgba(255, 99, 132, 0.6)'
            }]
          }}
        />
      </div>
    </div>
  );
}
```

---

## Error Handling

Все endpoints возвращают стандартные HTTP коды:
- **200 OK** - успешная операция
- **201 Created** - объект создан
- **204 No Content** - объект удален
- **400 Bad Request** - невалидные данные
- **401 Unauthorized** - не авторизован
- **403 Forbidden** - недостаточно прав
- **404 Not Found** - объект не найден

**Формат ошибок:**
```json
{
  "detail": "Описание ошибки"
}
```

или для ошибок валидации:

```json
{
  "email": ["Пользователь с таким email уже существует."],
  "phone": ["Неверный формат телефона."]
}
```

---

## Testing

```bash
# Запуск тестов для Super Admin API
python manage.py test apps.users.tests.test_superadmin_api

# Создать тестового Super Admin и риелтора
python manage.py shell
```

```python
from apps.users.models import CustomUser, RealEstateAgency

# Создать агентство
agency = RealEstateAgency.objects.create(
    name="Test Agency",
    city="Астана",
    phone="+77172555000",
    email="test@agency.kz",
    commission_rate=12.0,
    realtors_limit=20
)

# Создать Super Admin
super_admin = CustomUser.objects.create_user(
    email="admin@agency.kz",
    password="SecurePass123!",
    phone="+77011111111",
    role=CustomUser.RoleChoices.SUPER_ADMIN,
    agency=agency
)
agency.owner = super_admin
agency.save()

# Создать риелтора
realtor = CustomUser.objects.create_user(
    email="realtor@agency.kz",
    password="RealtorPass123!",
    phone="+77022222222",
    role=CustomUser.RoleChoices.REALTOR,
    agency=agency
)
```

---

## Roadmap

### Планируется добавить:

1. **Экспорт отчетов**:
   - CSV/XLSX выгрузка статистики
   - PDF отчеты по агентству

2. **Уведомления**:
   - Email уведомления при создании риелтора
   - Telegram интеграция для агентства

3. **Аналитика**:
   - Динамика доходов по месяцам
   - Конверсия бронирований
   - Прогнозы на основе ML

4. **Пользователи**:
   - Массовое редактирование риелторов
   - Импорт из CSV

---

## Безопасность

### Важные моменты:

1. **Изоляция данных**: Super Admin видит только свое агентство
2. **Аудит**: Все изменения риелторов логируются (TODO)
3. **Пароли**: Хэшируются с использованием Django PBKDF2
4. **JWT токены**: Истекают через 24 часа (настраивается)

### Рекомендации:

- Используйте HTTPS в продакшене
- Храните JWT токены в httpOnly cookies
- Реализуйте rate limiting для API endpoints
- Регулярно обновляйте зависимости

---

## Поддержка

По вопросам и багам обращайтесь:
- Email: support@zhilyego.kz
- Telegram: @zhilyego_support
- GitHub Issues: [github.com/zhilyego/issues](https://github.com/zhilyego/issues)