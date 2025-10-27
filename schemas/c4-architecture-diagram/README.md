# C4 диаграммы платформы «ЖильеGO» (PlantUML)

## 📋 Описание

Полный набор C4 архитектурных диаграмм для платформы посуточной аренды жилья «ЖильеGO», реализованной по принципам DDD, CQRS и Event-Driven Architecture.

## 🎯 Структура диаграмм

### Level 1: System Context
**Файл:** `c4-contaxt-diagram.puml`

Показывает систему целиком с пользователями и внешними системами:
- 6 ролей пользователей (Гость, Пользователь, Риелтор, Руководитель агентства, Суперпользователь, Модератор)
- 3 внешние системы (Kaspi Pay, Telegram Bot API, Email Service)

### Level 2: Container
**Файл:** `c4-containers-diagram.puml`

Детализирует технологический стек:
- Django Web Application (REST API, DRF, интеграция с Prometheus/Sentry)
- Telegram Bot (python-telegram-bot 20.x)
- PostgreSQL (write модель)
- Redis (кэш поиска, брокер Celery, rate limiting)
- Celery Workers + Beat
- MinIO (S3 Storage)
- (Опционально) Nginx/Reverse Proxy, Prometheus, Grafana

### Level 3: Component
**Файл:** `c4-components-diagram.puml`

Внутренняя структура Django приложения:
- **Entry Points:** REST API, вебхуки Kaspi/Telegram, Django Admin
- **Application Layer:** Message Bus, Command/Event Handlers, Query Views
- **Domain Layer:** Aggregates, Commands, Events, Value Objects
- **Infrastructure:** UoW, Repositories, Adapters (Payment, Notification, Cache)
- **Read Model:** Redis‑кэш для поиска (расширяется в сторону CQRS)

### Level 4: Code (Sequence)
**Файл:** `c4-CreateBooking-diagram.puml`

Детальный flow создания бронирования:
1. Валидация запроса (REST API или бот)
2. Загрузка агрегата доступности
3. Проверка инвариантов (нет пересечений дат)
4. Создание Booking со статусом HOLD
5. Commit транзакции + PostgreSQL EXCLUDE INDEX
6. Публикация доменных событий (точка расширения)
7. Асинхронная обработка (уведомления, обновление read-модели/кэша)

### Дополнительные диаграммы

#### Domain Model (Class Diagram)
**Файл:** `c4-DomainModel-diagram.puml`

Полная доменная модель DDD:
- Aggregates (Inventory, Property, Booking, Payment)
- Entities (Booking, Allocation)
- Value Objects (DateRange, Money, Location)
- Domain Events (BookingConfirmed, PaymentSucceeded, etc.)
- Commands (CreateBooking, ProcessPayment, etc.)

#### Layered Architecture
**Файл:** `c4-Architecture-diagram.puml`

Hexagonal/Clean Architecture с явным разделением:
- External Systems
- Entry Points (Adapters)
- Application Layer (Command/Query Side)
- Domain Layer (Aggregates, Events, Commands)
- Infrastructure (Repositories, Adapters)
- Data Stores

Показывает Dependency Rule: Domain ← Application ← Infrastructure ← External

#### Deployment Diagram
**Файл:** `c4-deployment-diagram.puml`

Инфраструктура развертывания:
- **MVP (Этап 1):** Docker Compose на одном VPS (PostgreSQL, Redis, MinIO, web, Celery)
- **Этап масштабирования:** интеграция с внешним reverse proxy / мониторингом и дальнейший переход к Kubernetes при росте нагрузки

#### Architectural Decisions
**Файл:** `c4-architecture-decision-diagram.puml`

Связь требований ТЗ с архитектурными решениями:
- Требования (нет двойного бронирования, атомарность, производительность)
- Паттерны (DDD, Hexagonal, CQRS, Event-Driven)
- Технические решения (EXCLUDE INDEX, UoW, Idempotency, Caching)
- Trade-offs (Eventual Consistency, Монолит → Микросервисы)

## 🚀 Как использовать

### Online просмотр

1. **PlantUML Online Server:**
   ```
   http://www.plantuml.com/plantuml/uml/
   ```
   Скопируйте код диаграммы и вставьте в редактор.

2. **PlantUML Proxy (GitHub):**
   ```
   https://www.plantuml.com/plantuml/proxy?src=<RAW_URL>
   ```

### Локальная генерация

#### Установка PlantUML

**macOS:**
```bash
brew install plantuml
```

**Ubuntu/Debian:**
```bash
sudo apt-get install plantuml
```

**Windows:**
```bash
choco install plantuml
```

#### Генерация PNG/SVG

```bash
# PNG
plantuml c4-contaxt-diagram.puml

# SVG (векторная графика)
plantuml -tsvg c4-contaxt-diagram.puml

# PDF
plantuml -tpdf c4-contaxt-diagram.puml

# Все файлы в папке
plantuml *.puml
```

### Интеграция с VS Code

1. Установите расширение **PlantUML** (jebbs.plantuml)
2. Откройте `.puml` файл
3. Нажмите `Alt+D` для preview
4. Или `Ctrl+Shift+P` → "PlantUML: Preview Current Diagram"

### Интеграция с IntelliJ IDEA / PyCharm

1. Установите плагин **PlantUML Integration**
2. Откройте `.puml` файл
3. Правый клик → "Show PlantUML Diagram"

## 📁 Рекомендуемая структура проекта

```
zhilyego/
├── docs/
│   ├── architecture/
│   │   ├── c4/
│   │   │   ├── c4-contaxt-diagram.puml
│   │   │   ├── c4-containers-diagram.puml
│   │   │   ├── c4-components-diagram.puml
│   │   │   ├── c4-CreateBooking-diagram.puml
│   │   │   ├── c4-DomainModel-diagram.puml
│   │   │   ├── c4-Architecture-diagram.puml
│   │   │   ├── c4-deployment-diagram.puml
│   │   │   └── c4-architecture-decision-diagram.puml
│   │   │
│   │   ├── generated/           # Сгенерированные изображения
│   │   │   ├── *.png
│   │   │   └── *.svg
│   │   │
│   │   └── README.md            # Этот файл
│   │
│   ├── api/
│   │   └── openapi.yaml
│   │
│   └── ddd/
│       ├── bounded_contexts.md
│       └── ubiquitous_language.md
```

## 🔄 Автоматическая генерация в CI/CD

### GitHub Actions

```yaml
name: Generate Architecture Diagrams

on:
  push:
    paths:
      - 'docs/c4-architecture-diagram/c4/*.puml'

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup PlantUML
        run: |
          sudo apt-get update
          sudo apt-get install -y plantuml
      
      - name: Generate diagrams
        run: |
          cd docs/architecture/c4
          plantuml -tsvg *.puml
          plantuml -tpng *.puml
          mv *.svg *.png ../generated/
      
      - name: Commit generated files
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          git add docs/architecture/generated/
          git commit -m "Update architecture diagrams" || echo "No changes"
          git push
```

## 📚 Ссылки

### PlantUML
- [PlantUML Official](https://plantuml.com/)
- [PlantUML Language Reference](https://plantuml.com/guide)
- [C4-PlantUML](https://github.com/plantuml-stdlib/C4-PlantUML)

### C4 Model
- [C4 Model Official](https://c4model.com/)
- [C4 Model: Levels](https://c4model.com/#Levels)

### Архитектурные паттерны
- [DDD Reference](https://domainlanguage.com/ddd/reference/)
- [Architecture Patterns with Python](https://www.cosmicpython.com/)
- [Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/)

## 🎨 Легенда цветов

| Компонент | Цвет | Значение |
|-----------|------|----------|
| Domain Layer | 🟢 Зеленый | Бизнес-логика (чистая) |
| Application Layer | 🔵 Голубой | Use-cases, оркестрация |
| Infrastructure | 🟣 Фиолетовый | Адаптеры, интеграции |
| Read Model | 🟡 Желтый | CQRS Query Side |
| Message Bus | 🔴 Красный | Центральный оркестратор |
| External | ⚫ Серый | Внешние системы |

## ✅ Чеклист использования

- [ ] Все диаграммы в репозитории (`docs/architecture/c4/`)
- [ ] Настроена автогенерация в CI/CD
- [ ] Диаграммы обновляются при изменении архитектуры
- [ ] Добавлены в README.md проекта
- [ ] Используются в технических ревью
- [ ] Показываются новым членам команды при онбординге
- [ ] Синхронизированы с реальной реализацией

## 🔍 Валидация диаграмм

```bash
# Проверка синтаксиса всех файлов
plantuml -checkonly *.puml

# Генерация с детальными ошибками
plantuml -verbose *.puml
```

## 📝 Рекомендации по обновлению

1. **При добавлении нового Bounded Context:**
   - Обновите `domain_model.puml`
   - Добавьте компонент в `c4_component.puml`

2. **При изменении интеграции:**
   - Обновите `c4_container.puml`
   - Проверьте `layered_architecture.puml`

3. **При изменении деплоймента:**
   - Обновите `deployment.puml`

4. **При принятии архитектурного решения:**
   - Документируйте в `architectural_decisions.puml`
   - Создайте ADR (Architecture Decision Record)

## 🤝 Контрибьюция

При изменении архитектуры:
1. Обновите соответствующие `.puml` файлы
2. Сгенерируйте новые изображения
3. Создайте PR с пометкой `[ARCH]`
4. Добавьте объяснение изменений в description

---

**Версия:** 1.0  
**Дата обновления:** 2025-01-21  
**Автор:** Architecture Team
