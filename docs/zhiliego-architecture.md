# Архитектура Backend «ЖильеGO»

## 🏗️ Общая архитектура системы

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   КЛИЕНТСКИЙ УРОВЕНЬ                            │
├─────────────────────┬───────────────────┬─────────────────┬───────────────────┤
│   Telegram Users    │   WhatsApp Users   │   Web Portal   │   Mobile Apps     │
│    [@zhilego_bot]   │  [+7 XXX XXX XXXX] │  [zhilego.kz]  │  [iOS/Android]    │
└──────────┬──────────┴─────────┬─────────┴────────┬────────┴────────┬──────────┘
           │                    │                   │                 │
           ▼                    ▼                   ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY LAYER                                  │
│                         Nginx (Load Balancer + SSL)                            │
│                    ┌─────────────────────────────────┐                         │
│                    │   Rate Limiting: 100 req/min    │                         │
│                    │   JWT Validation               │                         │
│                    │   Request Routing              │                         │
│                    └─────────────────────────────────┘                         │
└───────────┬──────────────────┬─────────────────┬─────────────────┬────────────┘
            │                  │                 │                 │
            ▼                  ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ПРИЛОЖЕНИЕ (Django 5.2)                              │
├───────────────────┬─────────────────┬──────────────────┬──────────────────────┤
│  Webhook Handler  │   REST API v1   │  Admin Portal   │   Background Jobs    │
│  ┌─────────────┐  │  ┌────────────┐ │ ┌─────────────┐ │  ┌────────────────┐  │
│  │  Telegram   │  │  │ /listings  │ │ │Django Admin │ │  │  Celery Beat   │  │
│  │  WhatsApp   │  │  │ /bookings  │ │ │ Statistics  │ │  │  Scheduled     │  │
│  │  Kaspi      │  │  │ /payments  │ │ │ User Mgmt   │ │  │  Notifications │  │
│  └─────────────┘  │  │ /users     │ │ └─────────────┘ │  └────────────────┘  │
│                   │  └────────────┘ │                 │                      │
└───────────────────┴─────────────────┴──────────────────┴──────────────────────┘
```

## 🔧 Детальная архитектура компонентов

### 1. Django Applications Structure
```
booking_bot/
├── core/                    # Базовые классы и утилиты
│   ├── middleware.py       # CSRF, Auth, Logging
│   ├── exceptions.py       # Кастомные исключения
│   └── validators.py       # Общие валидаторы
│
├── users/                   # Управление пользователями
│   ├── models.py           # User, UserProfile
│   ├── auth.py            # JWT + Telegram Auth
│   └── permissions.py      # Role-based access
│
├── listings/                # Управление объектами
│   ├── models.py           # Property, Photo, Review
│   ├── filters.py          # Django-filters
│   └── tasks.py           # Celery tasks
│
├── bookings/                # Бронирования
│   ├── models.py           # Booking, BookingStatus
│   ├── state_machine.py    # FSM для статусов
│   └── availability.py     # Проверка доступности
│
├── payments/                # Платежи
│   ├── models.py           # Payment, Transaction
│   ├── kaspi_service.py    # Kaspi integration
│   └── reconciliation.py   # Сверка платежей
│
├── telegram_bot/            # Telegram интеграция
│   ├── handlers.py         # Message handlers
│   ├── keyboards.py        # Reply keyboards
│   └── states.py          # User state machine
│
└── whatsapp_bot/           # WhatsApp интеграция
    ├── webhook.py          # Twilio webhook
    ├── handlers.py         # Message processing
    └── templates.py        # Message templates
```

### 2. База данных (PostgreSQL 15)
```
┌─────────────────────────────────────────────────────────────┐
│                     PostgreSQL Cluster                      │
├─────────────────────────┬───────────────────────────────────┤
│      Primary DB         │         Read Replicas            │
│  ┌─────────────────┐    │    ┌──────────┐ ┌──────────┐    │
│  │  Transactional  │    │    │ Analytics│ │ Reports  │    │
│  │     Data        │───▶│    │ Queries  │ │ Queries  │    │
│  │                 │    │    └──────────┘ └──────────┘    │
│  └─────────────────┘    │                                  │
│                         │                                  │
│  Key Tables:            │    Indexes:                      │
│  - users (50K)          │    - property_location (GiST)    │
│  - properties (5K)      │    - booking_dates (B-tree)     │
│  - bookings (100K)      │    - user_phone (Hash)         │
│  - payments (100K)      │    - property_status           │
│  - reviews (20K)        │                                  │
└─────────────────────────┴───────────────────────────────────┘
```

### 3. Кеширование (Redis)
```
┌─────────────────────────────────────────────────────────────┐
│                      Redis Cluster                          │
├──────────────┬──────────────┬──────────────┬───────────────┤
│  Session     │   Cache      │  Message     │   Rate        │
│  Storage     │   Layer      │  Broker      │   Limiter     │
│              │              │              │               │
│ • User       │ • Properties │ • Celery     │ • API calls   │
│   sessions   │   listings   │   tasks      │   100/min     │
│ • Bot states │ • Prices     │ • Priority   │ • Webhooks    │
│ • Auth       │ • Available  │   queues     │   10/sec      │
│   tokens     │   dates      │              │               │
│              │              │              │               │
│ TTL: 24h     │ TTL: 5-60min│ TTL: 7 days  │ TTL: 1min     │
└──────────────┴──────────────┴──────────────┴───────────────┘
```

### 4. Асинхронные задачи (Celery + RabbitMQ)
```
┌─────────────────────────────────────────────────────────────┐
│                    Celery Architecture                      │
├─────────────────────────┬───────────────────────────────────┤
│     Task Producers      │         Task Consumers          │
│                         │                                  │
│ Django Views ──┐        │    ┌─── Worker 1 (payments)    │
│ Webhooks ──────┼────▶   │    ├─── Worker 2 (notifications)│
│ Scheduled ─────┘        │    ├─── Worker 3 (analytics)   │
│                         │    └─── Worker 4 (general)      │
│                         │                                  │
│     RabbitMQ Queues:    │       Task Examples:            │
│ • high_priority         │ • send_booking_confirmation    │
│ • default              │ • process_kaspi_payment        │
│ • notifications        │ • generate_daily_report        │
│ • scheduled            │ • sync_property_availability   │
└─────────────────────────┴───────────────────────────────────┘
```

### 5. Интеграция с внешними сервисами
```
┌─────────────────────────────────────────────────────────────┐
│                 External Services Integration               │
├────────────────┬────────────────┬──────────────────────────┤
│  Telegram API  │  WhatsApp API  │     Kaspi.kz API        │
│                │                │                          │
│ Bot API:       │ Twilio API:    │ Payment Gateway:        │
│ • sendMessage  │ • Send SMS     │ • /payment/create       │
│ • sendPhoto    │ • Webhook      │ • /payment/status       │
│ • getUpdates   │ • Templates    │ • /payment/refund       │
│                │                │                          │
│ Webhook URL:   │ Webhook URL:   │ Callback URL:           │
│ /telegram/     │ /whatsapp/     │ /kaspi/callback/        │
│ webhook/       │ webhook/       │                          │
│                │                │                          │
│ Rate: 30/sec   │ Rate: 100/sec  │ Rate: 10/sec            │
└────────────────┴────────────────┴──────────────────────────┘
```

## 🔄 Поток данных (Data Flow)

### Сценарий: Бронирование через Telegram
```
User                Telegram            Django              Redis           PostgreSQL         Kaspi
 │                     │                  │                   │                 │               │
 │  "Забронировать"    │                  │                   │                 │               │
 ├────────────────────▶│                  │                   │                 │               │
 │                     │   POST webhook   │                   │                 │               │
 │                     ├─────────────────▶│                   │                 │               │
 │                     │                  │   Get user state  │                 │               │
 │                     │                  ├──────────────────▶│                 │               │
 │                     │                  │◀──────────────────┤                 │               │
 │                     │                  │                   │                 │               │
 │                     │                  │   Check availability               │               │
 │                     │                  ├─────────────────────────────────────▶│               │
 │                     │                  │◀─────────────────────────────────────┤               │
 │                     │                  │                   │                 │               │
 │                     │                  │   Create booking  │                 │               │
 │                     │                  ├─────────────────────────────────────▶│               │
 │                     │                  │◀─────────────────────────────────────┤               │
 │                     │                  │                   │                 │               │
 │                     │                  │   Init payment    │                 │               │
 │                     │                  ├───────────────────────────────────────────────────▶│
 │                     │                  │◀───────────────────────────────────────────────────┤
 │                     │                  │                   │                 │               │
 │                     │  Send payment URL│                   │                 │               │
 │                     │◀─────────────────┤                   │                 │               │
 │   Payment link      │                  │                   │                 │               │
 │◀────────────────────┤                  │                   │                 │               │
 │                     │                  │                   │                 │               │
 │   [User pays]       │                  │                   │                 │               │
 ├────────────────────────────────────────────────────────────────────────────────────────────▶│
 │                     │                  │                   │                 │               │
 │                     │                  │  Webhook callback │                 │               │
 │                     │                  │◀───────────────────────────────────────────────────┤
 │                     │                  │                   │                 │               │
 │                     │                  │  Update booking   │                 │               │
 │                     │                  ├─────────────────────────────────────▶│               │
 │                     │                  │                   │                 │               │
 │                     │                  │  Get access codes │                 │               │
 │                     │                  ├─────────────────────────────────────▶│               │
 │                     │                  │◀─────────────────────────────────────┤               │
 │                     │                  │                   │                 │               │
 │                     │  Send keys       │                   │                 │               │
 │                     │◀─────────────────┤                   │                 │               │
 │   Access codes      │                  │                   │                 │               │
 │◀────────────────────┤                  │                   │                 │               │
```

## 🔐 Безопасность и масштабирование

### Security Layers
```
┌─────────────────────────────────────────────────────────────┐
│                    Security Architecture                    │
├─────────────────┬────────────────┬─────────────────────────┤
│   Network       │  Application   │      Data               │
│                 │                │                         │
│ • Cloudflare    │ • JWT Auth     │ • Encryption at rest   │
│ • SSL/TLS       │ • RBAC         │ • Field-level encrypt  │
│ • VPN           │ • API Keys     │ • Backup encryption    │
│ • Firewall      │ • Rate limit   │ • PII tokenization     │
│ • DDoS protect  │ • CORS         │ • Audit logs           │
└─────────────────┴────────────────┴─────────────────────────┘
```

### Scaling Strategy
```
┌─────────────────────────────────────────────────────────────┐
│                    Horizontal Scaling                       │
├──────────────────────────┬──────────────────────────────────┤
│   Current (MVP)          │      Target (12 months)         │
│                          │                                 │
│ • 1 Django instance      │ • 5 Django instances (K8s)      │
│ • 1 PostgreSQL master    │ • 1 master + 2 replicas        │
│ • 1 Redis instance       │ • Redis Cluster (3 nodes)       │
│ • 2 Celery workers       │ • 10 workers (autoscaling)      │
│                          │                                 │
│ Capacity:                │ Capacity:                       │
│ • 100 req/sec            │ • 1000 req/sec                  │
│ • 1K concurrent users    │ • 20K concurrent users          │
│ • 99.5% uptime           │ • 99.9% uptime                  │
└──────────────────────────┴──────────────────────────────────┘
```

## 🚀 DevOps Pipeline
```
┌─────────────────────────────────────────────────────────────┐
│                      CI/CD Pipeline                         │
├────────────┬────────────┬────────────┬─────────────────────┤
│   Develop  │    Test    │   Stage    │    Production       │
│            │            │            │                     │
│  GitHub    │  GitHub    │  Docker    │   Kubernetes        │
│  Feature   │  Actions   │  Registry  │   ┌─────────────┐   │
│  Branch ──▶│  ┌──────┐  │  ┌──────┐  │   │ Deployment  │   │
│            │  │Tests │  │  │Build │  │   │ • Rolling   │   │
│            │  │Lint  │──▶  │Image │──▶   │ • Blue/Green│   │
│            │  │Security │  │Push  │  │   │ • Canary    │   │
│            │  └──────┘  │  └──────┘  │   └─────────────┘   │
│            │            │            │                     │
│ Webhook    │  Coverage  │  Deploy    │   Monitor:          │
│ on push    │  > 80%     │  to stage  │   • Prometheus      │
│            │            │            │   • Grafana         │
│            │            │            │   • Sentry          │
└────────────┴────────────┴────────────┴─────────────────────┘
```

## 📊 Мониторинг и наблюдаемость
```
┌─────────────────────────────────────────────────────────────┐
│                 Observability Stack                         │
├─────────────┬──────────────┬────────────┬──────────────────┤
│   Metrics   │     Logs     │   Traces   │    Alerts        │
│             │              │            │                  │
│ Prometheus: │ ELK Stack:   │ Jaeger:    │ AlertManager:    │
│ • Response  │ • App logs   │ • Request  │ • Downtime       │
│   time      │ • Error logs │   flow     │ • Error rate     │
│ • Error rate│ • Access logs│ • Latency  │ • Payment fails  │
│ • Throughput│ • Audit logs │ • Deps     │ • Low inventory  │
│             │              │            │                  │
│ Grafana     │ Kibana       │ Jaeger UI  │ PagerDuty        │
│ Dashboards  │ Search       │ Trace View │ Escalation       │
└─────────────┴──────────────┴────────────┴──────────────────┘
```