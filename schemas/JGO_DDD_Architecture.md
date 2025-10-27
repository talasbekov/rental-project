# ЖильеGO - DDD Architecture

## Общее описание проекта
Платформа посуточной аренды жилья с веб-интерфейсом и Telegram-ботом. Поддерживает различные типы жилья, бронирование, онлайн-оплату и систему отзывов. Включает роли: пользователь, риелтор (администратор), супер админ (руководитель риелторов), суперпользователь.

---

## Текущая архитектура монолита
- **Язык:** Python 3.14 (Django 5)
- **База данных:** PostgreSQL (транзакции, блокировки для предотвращения двойного бронирования)
- **Хранилище:** Minio (S3-совместимое хранилище для фото)
- **Кеш и очереди:** Redis + Celery (фоновые задачи, уведомления)
- **Интерфейсы:** Django Web + Python Telegram Bot
- **Хостинг:** PS.kz (казахстанский провайдер)
- **Взаимодействие:** Синхронное (HTTP) + асинхронное (Celery tasks)
- **Архитектура:** Монолит (пока), планируется переход к модульному монолиту с четкими границами контекстов

---

## Проблемы текущего решения

**Проблема 1: Конкурентные бронирования**
- Критическая проблема двойного бронирования одного объекта несколькими пользователями одновременно
- Требуется транзакционная целостность с блокировками (SELECT FOR UPDATE)
- Необходим календарь доступности с проверкой пересечений дат

**Проблема 2: Сложная доменная логика оплаты**
- Разные методы оплаты (Kaspi, наличные, карты)
- Необходимость отслеживания статусов платежей
- Автоматическая отмена неоплаченных броней через определенное время

**Проблема 3: Множество типов жилья**
- Квартира, дом, коттедж, комната, хостел, гостиница (будущее)
- Разные бизнес-правила для каждого типа
- Гостиницы требуют управление номерами (один объект = много номеров)

**Проблема 4: Множественные интерфейсы**
- Веб-приложение и Telegram-бот должны работать с единой логикой
- Необходима четкая изоляция презентационного слоя от бизнес-логики

**Проблема 5: Масштабирование географии**
- MVP: только Астана
- Этап 2: несколько городов
- Необходимость поддержки мультиязычности (русский, казахский, английский)

---

## Определение доменов и границ контекстов

### **ДОМЕН: Управление недвижимостью (Property Management)**

#### **Поддомен: Каталог недвижимости**
  - **Контекст: Property Catalog**
    - **Сущности:**
      - `Property` (объект жилья) - ID, название, описание, статус, дата создания
      - `PropertyType` (тип жилья) - квартира, дом, коттедж, комната, хостел, гостиница
      - `PropertyPhoto` (фотографии) - URL, порядок, описание
      - `Amenity` (удобства) - Wi-Fi, парковка, кухня и т.д.
      - `Room` (номер) - для гостиниц: тип номера, количество мест
      
    - **Объекты-значения:**
      - `Address` (город, район, улица, дом, подъезд, этаж)
      - `Location` (координаты: широта, долгота)
      - `Price` (цена за сутки, валюта)
      - `PropertyClass` (комфорт, бизнес, премиум)
      - `RoomCount` (количество комнат)
      - `AccessInfo` (код домофона, код квартиры, инструкции)
      
    - **Агрегаты:**
      - `Property` (корневая сущность) - управляет своими фото, удобствами, ценами
      
    - **Репозитории:**
      - `PropertyRepository` - сохранение/получение объектов жилья
      - `AmenityRepository` - управление справочником удобств
      
    - **Сервисы:**
      - `PropertyManagementService` - добавление, редактирование, архивирование объектов
      - `PropertyValidationService` - валидация данных (фото до 6 шт, размер до 7 МБ)
      - `PropertyPhotosService` - работа с Minio S3

#### **Поддомен: Поиск и фильтрация**
  - **Контекст: Search & Discovery**
    - **Сущности:**
      - `SearchQuery` - история поисковых запросов пользователя
      - `SearchFilter` - сохраненные фильтры
      
    - **Объекты-значения:**
      - `SearchCriteria` (город, район, тип, комнаты, класс, цена min/max)
      - `DateRange` (дата заезда, дата выезда)
      - `SortOrder` (по цене, по дате добавления, по рейтингу)
      
    - **Агрегаты:**
      - `SearchResult` - результаты поиска с пагинацией
      
    - **Репозитории:**
      - `SearchRepository` - оптимизированные запросы с индексами
      
    - **Сервисы:**
      - `PropertySearchService` - поиск по критериям
      - `AvailabilityCheckService` - проверка доступности на даты
      - `SearchIndexService` - поддержка полнотекстового поиска (будущее)

#### **Поддомен: Календарь доступности**
  - **Контекст: Availability Calendar**
    - **Сущности:**
      - `Calendar` - календарь объекта с блокировками
      - `DateBlock` - занятая/заблокированная дата
      
    - **Объекты-значения:**
      - `DateRange` (начало, конец)
      - `BlockReason` (забронировано, техническое обслуживание, заблокировано владельцем)
      
    - **Агрегаты:**
      - `PropertyCalendar` - управляет доступностью дат для объекта
      
    - **Репозитории:**
      - `CalendarRepository` - работа с календарем
      
    - **Сервисы:**
      - `AvailabilityService` - проверка пересечений дат
      - `CalendarSyncService` - синхронизация с внешними календарями (будущее)

---

### **ДОМЕН: Бронирование (Booking Management)**

#### **Поддомен: Процесс бронирования**
  - **Контекст: Booking Lifecycle**
    - **Сущности:**
      - `Booking` - ID, пользователь, объект, статус, даты, цена
      - `BookingStatus` - ожидает оплаты, оплачено, подтверждено, заселен, завершено, отменено
      - `CancellationRequest` - запрос на отмену
      
    - **Объекты-значения:**
      - `BookingDates` (дата/время заезда, дата/время выезда)
      - `TotalAmount` (итоговая сумма: цена × ночи + комиссии)
      - `GuestInfo` (ФИО, телефон, комментарии)
      - `BookingCode` (уникальный код брони)
      
    - **Агрегаты:**
      - `Booking` (корневая сущность) - управляет жизненным циклом брони
      
    - **Репозитории:**
      - `BookingRepository` - CRUD операции с транзакциями
      
    - **Сервисы:**
      - `BookingService` - создание, подтверждение брони
      - `BookingValidationService` - проверка доступности, предотвращение двойного бронирования
      - `BookingCancellationService` - отмена с правилами и штрафами
      - `BookingExpirationService` - автоматическая отмена неоплаченных (Celery)

#### **Поддомен: История и текущие бронирования**
  - **Контекст: Booking History**
    - **Сущности:**
      - `BookingHistory` - завершенные и отмененные брони
      - `ActiveBooking` - текущие активные брони
      
    - **Объекты-значения:**
      - `BookingPeriod` (прошлые, текущие, будущие)
      
    - **Репозитории:**
      - `BookingHistoryRepository`
      
    - **Сервисы:**
      - `BookingHistoryService` - просмотр истории
      - `ActiveBookingService` - управление текущими

---

### **ДОМЕН: Платежная система (Payment System)**

#### **Поддомен: Обработка платежей**
  - **Контекст: Payment Processing**
    - **Сущности:**
      - `Payment` - ID, бронирование, сумма, метод, статус, дата
      - `PaymentMethod` - Kaspi, карта, наличные
      - `Transaction` - детали транзакции с платежным шлюзом
      - `Refund` - возврат средств
      
    - **Объекты-значения:**
      - `PaymentStatus` (pending, processing, completed, failed, refunded)
      - `PaymentAmount` (сумма, валюта)
      - `TransactionId` (ID от платежного провайдера)
      - `PaymentCallback` (данные callback от Kaspi)
      
    - **Агрегаты:**
      - `Payment` (корневая сущность)
      
    - **Репозитории:**
      - `PaymentRepository`
      - `TransactionRepository`
      
    - **Сервисы:**
      - `PaymentService` - создание платежа
      - `KaspiPaymentGateway` - интеграция с Kaspi API
      - `PaymentCallbackHandler` - обработка ответов от шлюза
      - `RefundService` - возврат средств
      - `PaymentNotificationService` - уведомления о статусе

#### **Поддомен: Финансовая отчетность**
  - **Контекст: Financial Reporting**
    - **Сущности:**
      - `PayoutSchedule` - расписание выплат владельцам
      - `Commission` - комиссии платформы
      
    - **Объекты-значения:**
      - `PayoutAmount` (сумма выплаты)
      - `CommissionRate` (процент комиссии)
      
    - **Репозитории:**
      - `FinancialReportRepository`
      
    - **Сервисы:**
      - `PayoutService` - выплаты владельцам (будущее)
      - `CommissionCalculationService`
      - `FinancialReportService` - отчеты

---

### **ДОМЕН: Управление пользователями (Identity & Access)**

#### **Поддомен: Аутентификация и авторизация**
  - **Контекст: Authentication & Authorization**
    - **Сущности:**
      - `User` - ID, username, email, телефон, роль, дата регистрации
      - `Role` - пользователь, риелтор (админ), супер админ, суперпользователь
      - `Permission` - права доступа
      - `TelegramAccount` - привязка Telegram ID к пользователю
      
    - **Объекты-значения:**
      - `Credentials` (login, password hash)
      - `Token` (JWT, refresh token)
      - `TelegramId` (Telegram user ID)
      
    - **Агрегаты:**
      - `User` (корневая сущность)
      
    - **Репозитории:**
      - `UserRepository`
      - `RoleRepository`
      
    - **Сервисы:**
      - `AuthenticationService` - вход/выход
      - `RegistrationService` - регистрация
      - `TelegramAuthService` - привязка Telegram аккаунта
      - `PasswordResetService`
      - `RoleManagementService`

#### **Поддомен: Профили**
  - **Контекст: User Profiles**
    - **Сущности:**
      - `UserProfile` - расширенная информация о пользователе
      - `RealtorProfile` - профиль риелтора с компанией
      
    - **Объекты-значения:**
      - `FullName` (имя, фамилия)
      - `ContactInfo` (email, телефон)
      - `RealtorCompany` (название компании, позиция)
      
    - **Репозитории:**
      - `ProfileRepository`
      
    - **Сервисы:**
      - `ProfileService` - управление профилем

---

### **ДОМЕН: Отзывы и рейтинги (Reviews & Ratings)**

#### **Поддомен: Система отзывов**
  - **Контекст: Review Management**
    - **Сущности:**
      - `Review` - ID, пользователь, объект, бронирование, рейтинг, текст, фото, дата
      - `ReviewPhoto` - фото к отзыву
      - `ReviewModeration` - статус модерации
      
    - **Объекты-значения:**
      - `Rating` (1-5 звезд)
      - `ReviewText` (комментарий)
      - `ReviewStatus` (pending, approved, rejected)
      
    - **Агрегаты:**
      - `Review` (корневая сущность)
      
    - **Репозитории:**
      - `ReviewRepository`
      
    - **Сервисы:**
      - `ReviewService` - создание, редактирование отзывов
      - `ReviewModerationService` - модерация (будущее)
      - `RatingCalculationService` - расчет среднего рейтинга объекта
      - `ReviewNotificationService` - уведомления о новых отзывах

---

### **ДОМЕН: Уведомления (Notifications)**

#### **Поддомен: Система уведомлений**
  - **Контекст: Notification System**
    - **Сущности:**
      - `Notification` - ID, получатель, тип, канал, статус, дата
      - `NotificationTemplate` - шаблоны сообщений
      
    - **Объекты-значения:**
      - `NotificationType` (booking_created, payment_received, check_in_reminder, etc.)
      - `NotificationChannel` (email, telegram, sms)
      - `NotificationStatus` (pending, sent, failed)
      - `NotificationContent` (тема, текст, параметры)
      
    - **Агрегаты:**
      - `Notification` (корневая сущность)
      
    - **Репозитории:**
      - `NotificationRepository`
      - `TemplateRepository`
      
    - **Сервисы:**
      - `NotificationService` - отправка уведомлений (через Celery)
      - `EmailNotificationService` - отправка email
      - `TelegramNotificationService` - отправка через бот
      - `SmsNotificationService` - SMS (будущее)
      - `NotificationTemplateService` - управление шаблонами

---

### **ДОМЕН: Аналитика (Analytics & Reporting)**

#### **Поддомен: Бизнес-аналитика**
  - **Контекст: Business Analytics**
    - **Сущности:**
      - `Analytics` - метрики и статистика
      - `Report` - отчеты для разных ролей
      
    - **Объекты-значения:**
      - `Period` (день, неделя, месяц, год)
      - `RevenueMetrics` (доходы, комиссии)
      - `BookingMetrics` (количество броней, загрузка)
      - `UserMetrics` (ТОП пользователей)
      - `PropertyMetrics` (ТОП объектов)
      - `CancellationMetrics` (причины отмен)
      
    - **Репозитории:**
      - `AnalyticsRepository`
      - `ReportRepository`
      
    - **Сервисы:**
      - `AnalyticsService` - сбор метрик
      - `RevenueReportService` - отчеты по доходам
      - `OccupancyReportService` - отчеты по загрузке
      - `TopPerformersService` - ТОП-5 объектов/пользователей/риелторов
      - `CancellationAnalysisService` - анализ отмен
      - `ExportService` - экспорт в CSV/XLSX

#### **Поддомен: Аналитика для риелторов**
  - **Контекст: Realtor Analytics**
    - **Сущности:**
      - `RealtorMetrics` - метрики конкретного риелтора
      - `RealtorReport` - отчеты риелтора
      
    - **Сервисы:**
      - `RealtorAnalyticsService` - статистика по своим объектам
      
#### **Поддомен: Аналитика для супер админа**
  - **Контекст: SuperAdmin Analytics**
    - **Сущности:**
      - `AgencyMetrics` - метрики агентства недвижимости
      - `RealtorPerformance` - производительность риелторов в команде
      
    - **Сервисы:**
      - `AgencyAnalyticsService` - статистика по агентству
      - `TeamPerformanceService` - анализ команды

---

### **ДОМЕН: Telegram Bot Interface**

#### **Поддомен: Управление ботом**
  - **Контекст: Bot Management**
    - **Сущности:**
      - `BotUser` - пользователь бота (связан с User)
      - `BotSession` - сессия диалога с ботом
      - `BotCommand` - история команд
      
    - **Объекты-значения:**
      - `ChatId` (Telegram chat ID)
      - `MessageId` (ID сообщения)
      - `BotState` (текущее состояние FSM)
      - `KeyboardLayout` (inline клавиатуры)
      
    - **Агрегаты:**
      - `BotConversation` - управляет диалогом
      
    - **Репозитории:**
      - `BotSessionRepository`
      
    - **Сервисы:**
      - `BotService` - основной сервис бота
      - `BotMenuService` - управление меню
      - `BotSearchService` - поиск через бот
      - `BotBookingService` - бронирование через бот
      - `BotPropertyManagementService` - управление объектами (для риелторов)
      - `BotAnalyticsService` - аналитика в боте

---

## Взаимодействие между контекстами (Integration Events)

### События домена:

**Property Management →**
- `PropertyCreated` → Search, Notifications
- `PropertyUpdated` → Search, Calendar
- `PropertyDeleted` → Search, Calendar, Booking (отмена броней)

**Booking →**
- `BookingCreated` → Payment, Notifications, Calendar, Analytics
- `BookingConfirmed` → Notifications, Analytics
- `BookingCancelled` → Payment (возврат), Notifications, Calendar, Analytics
- `BookingCompleted` → Reviews, Analytics

**Payment →**
- `PaymentReceived` → Booking (подтверждение), Notifications, Analytics
- `PaymentFailed` → Booking (отмена), Notifications
- `RefundProcessed` → Notifications, Analytics

**Reviews →**
- `ReviewCreated` → Notifications (риелтору), Analytics
- `ReviewApproved` → Property (обновление рейтинга)

**Identity →**
- `UserRegistered` → Notifications
- `UserRoleChanged` → Permissions, Notifications

---

## Технические детали реализации

### Слоистая архитектура внутри монолита:

```
apps/
├── property/              # Property Management Domain
│   ├── domain/            # Сущности, Value Objects, Aggregates
│   ├── application/       # Services, Use Cases
│   ├── infrastructure/    # Repositories, External integrations
│   └── interfaces/        # Views, Serializers, API
│
├── booking/               # Booking Domain
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── interfaces/
│
├── payment/               # Payment Domain
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── interfaces/
│
├── identity/              # Identity & Access Domain
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── interfaces/
│
├── reviews/               # Reviews Domain
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── interfaces/
│
├── notifications/         # Notifications Domain
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── interfaces/
│
├── analytics/             # Analytics Domain
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   └── interfaces/
│
└── telegram_bot/          # Telegram Interface
    ├── handlers/          # Command handlers
    ├── services/          # Bot services (использует другие домены)
    └── keyboards/         # Inline keyboards
```

### Shared Kernel (общие компоненты):

```
shared/
├── domain/
│   ├── base_entity.py
│   ├── base_value_object.py
│   └── domain_events.py
│
├── application/
│   └── event_bus.py
│
└── infrastructure/
    ├── database.py
    ├── cache.py
    └── message_broker.py
```

---

## Поэтапная реализация

### **Этап 1 (MVP):**
- Property Management (без редактирования)
- Booking (базовый)
- Payment (offline)
- Identity (базовая авторизация)
- Notifications (email)

### **Этап 2:**
- Property Management (полный CRUD)
- Booking (с предотвращением двойного бронирования)
- Payment (Kaspi интеграция)
- Telegram Bot (полная функциональность)
- Reviews (базовая)
- Analytics (для админов)

### **Этап 3:**
- Reviews (с модерацией)
- Analytics (расширенная для всех ролей)
- Система сообщений (чат)
- Динамическое ценообразование
- Акции и промокоды

---

## Критические требования

### Транзакционная целостность:
```python
# Пример предотвращения двойного бронирования
with transaction.atomic():
    property = Property.objects.select_for_update().get(id=property_id)
    if property.is_available(date_from, date_to):
        booking = Booking.create(...)
        property.block_dates(date_from, date_to)
    else:
        raise PropertyNotAvailableError()
```

### Обработка конкурентности:
- Использование PostgreSQL блокировок
- Оптимистичные блокировки (version field)
- Celery для фоновых задач (автоотмена неоплаченных)

### Безопасность:
- Шифрование паролей (Django built-in)
- Защита платежных данных (PCI DSS через Kaspi)
- Логирование доступа к кодам квартир
- RBAC (Role-Based Access Control)

---

## Итоги по ролям

| Роль             | Property | Booking | Payment | Reviews | Analytics | Full Access |
|------------------|----------|---------|---------|---------|-----------|-------------|
| Пользователь     | Поиск    | ✅      | ✅      | ✅      | ❌        | ❌          |
| Риелтор          | ✅ (свои)| ✅ (свои)| ✅ (свои)| ✅ (свои)| ✅ (свои) | ❌          |
| СуперАдмин       | ✅ (команды)| ✅ (команды)| ✅ (команды)| ✅ (команды)| ✅ (команды) | ❌   |
| Суперпользователь| ✅ (все) | ✅ (все)| ✅ (все)| ✅ (все)| ✅ (все)  | ✅          |
