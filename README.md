# Selectel MCP Server

MVP MCP-сервера для получения балансов Selectel через сервисного пользователя.

## Возможности

- Подключение аккаунта Selectel один раз через `.env`, REST API или MCP tool
- Автоматическое обновление токена Selectel (24 часа) без участия пользователя
- MCP tools `connect_selectel_account`, `get_balance` и `get_balance_prediction`
- Audit log всех вызовов MCP tools

## Стек

- Python 3.12+
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Pydantic Settings
- httpx
- MCP (Streamable HTTP transport)
- Docker / Docker Compose

## Структура проекта

```
app/
├── main.py                 # FastAPI + MCP mount
├── config.py               # Настройки из env
├── db.py                   # SQLAlchemy engine/session
├── models.py               # ORM-модели
├── schemas.py              # Pydantic-схемы API
├── selectel_client.py      # Клиент Selectel API
├── mcp_tools.py            # MCP tools
├── api/
│   └── users.py            # REST API подключения аккаунта
├── services/
│   ├── balance_formatter.py
│   └── credentials_service.py
└── tests/
    └── test_balance_formatter.py

alembic/                    # Миграции БД
Dockerfile
docker-compose.yml
requirements.txt
```

## Быстрый старт

### 1. Создайте `.env`

```bash
cp .env.example .env
```

Заполните учётные данные Selectel (один раз):

```env
DEFAULT_USER_ID=default
SELECTEL_ACCOUNT_ID=12345
SELECTEL_SERVICE_USER_NAME=svc-user
SELECTEL_SERVICE_USER_PASSWORD=your-password
```

При старте сервис сохранит их в БД. Дальше авторизация и обновление токена выполняются автоматически.

### 2. Запуск через Docker Compose

```bash
docker compose up --build
```

Сервисы:

- `app` — http://localhost:8000
- `postgres` — localhost:5432

Миграции применяются автоматически при старте контейнера `app`.

### 3. Локальный запуск (без Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# PostgreSQL должен быть доступен
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/selectel_mcp

alembic upgrade head
uvicorn app.main:app --reload
```

## Одноразовая настройка и автоматическая авторизация

Вы передаёте `account_id`, `service_user_name` и `service_user_password` **один раз**. Сервер:

1. Сохраняет credentials в PostgreSQL
2. Получает токен Selectel (живёт ~24 часа)
3. Кеширует токен в БД
4. Автоматически обновляет токен по логину/паролю из БД, когда он истекает
5. При `401` сбрасывает токен и запрашивает новый без вашего участия

### Способ 1: через `.env` (рекомендуется для одного аккаунта)

```env
DEFAULT_USER_ID=default
SELECTEL_ACCOUNT_ID=12345
SELECTEL_SERVICE_USER_NAME=svc-user
SELECTEL_SERVICE_USER_PASSWORD=your-password
```

### Способ 2: через MCP tool `connect_selectel_account`

```json
{
  "account_id": "12345",
  "service_user_name": "svc-user",
  "service_user_password": "your-password"
}
```

`user_id` опционален, если задан `DEFAULT_USER_ID` в `.env`.

### Способ 3: через REST API

```bash
curl -X POST http://localhost:8000/users/demo-user/selectel-credentials \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "12345",
    "service_user_name": "svc-user",
    "service_user_password": "password"
  }'
```

После любого из способов достаточно вызывать `get_balance` — без повторной передачи пароля.

## Подключение пользователя (REST API)

```bash
curl -X POST http://localhost:8000/users/demo-user/selectel-credentials \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "12345",
    "service_user_name": "svc-user",
    "service_user_password": "password"
  }'
```

Логика endpoint:

1. Получает токен Selectel по логину и паролю сервисного пользователя
2. Выполняет тестовый запрос баланса
3. При успехе сохраняет credentials в БД

Возможные ошибки:

- `400` — неверный логин или пароль
- `403` — нет доступа к балансу
- `502` — проблемы с Selectel API

## Подключение в Cursor

1. Запустите сервис: `docker compose up --build`
2. Настройте credentials в `.env` или вызовите `connect_selectel_account` один раз
3. В проекте уже есть `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "selectel": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

4. Откройте этот проект в Cursor (или добавьте блок `selectel` в `~/.cursor/mcp.json` для всех проектов)
5. **Cursor Settings → Tools & MCP** — убедитесь, что сервер `selectel` в статусе connected (зелёный)
6. Если не подключается — перезапустите Cursor и проверьте `curl http://localhost:8000/health`

В чате можно спросить: «Проверь мой баланс в Selectel» — агент вызовет `get_balance` без передачи пароля.

> Нужен Cursor **0.48+** (поддержка Streamable HTTP).

## MCP tools

MCP endpoint: `http://localhost:8000/mcp`

> Открытие `/mcp` в браузере может не показать страницу — это нормально, MCP работает через POST (JSON-RPC), а не через обычный GET.

### `connect_selectel_account` (один раз)

```json
{
  "account_id": "12345",
  "service_user_name": "svc-user",
  "service_user_password": "password"
}
```

### `get_balance`

```json
{}
```

или с явным `user_id`:

```json
{
  "user_id": "demo-user"
}
```

Если задан `DEFAULT_USER_ID` в `.env`, `user_id` можно не передавать.

### `get_balance_prediction`

Оценка, на сколько хватит текущего баланса (в часах по категориям услуг). API: `GET /v2/billing/prediction` ([документация Selectel](https://docs.selectel.ru/api/balance/)).

```json
{}
```

Пример ответа:

```
Прогноз: на сколько хватит текущего баланса при текущем потреблении.

• Облачные серверы и основные услуги: 4 дн. 4 ч.
• Объектное хранилище: средств недостаточно
• VMware: 1 дн.
• VPC: 5 ч.
```

Возвращает человекочитаемый текст с балансами по `agreement_id`.

Пример ответа:

```
На аккаунте Selectel найдены балансы в валюте RUB.

ID договора: 263632, тип биллинга: primary

• Бонусный баланс: 36 614,64 ₽
• VK-баланс: 0 ₽
• Основной баланс: 5,14 ₽

Сумма балансов: 36 619,78 ₽
Задолженность: 0 ₽
Итоговый доступный баланс: 36 619,78 ₽

Режим оплаты: prepay
```

## Health check

```bash
curl http://localhost:8000/health
```

## Тесты

```bash
pytest
```

## Переменные окружения

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | URL PostgreSQL |
| `DEFAULT_USER_ID` | Пользователь по умолчанию для `get_balance` |
| `SELECTEL_ACCOUNT_ID` | ID аккаунта Selectel (одноразовая настройка через `.env`) |
| `SELECTEL_SERVICE_USER_NAME` | Логин сервисного пользователя |
| `SELECTEL_SERVICE_USER_PASSWORD` | Пароль сервисного пользователя |
| `SELECTEL_IDENTITY_URL` | URL авторизации Selectel |
| `SELECTEL_BALANCES_URL` | URL API балансов |
| `SELECTEL_BALANCE_PREDICTION_URL` | URL API прогноза баланса |
| `HTTP_TIMEOUT_SECONDS` | Таймаут HTTP-запросов |

## Безопасность

- Авторизация в Selectel выполняется по логину и паролю сервисного пользователя
- Пароли и токены не логируются
- API не возвращает пароль и токен

## Управление токенами Selectel

- Токен Selectel живёт ~24 часа — это ограничение API Selectel, не MCP-сервера
- Сервер кеширует токен в БД и обновляет его автоматически по сохранённому паролю
- Срок кеша: `now() + 23 hours` (запас 1 час до обновления)
- При `401 Unauthorized` токен сбрасывается и запрос повторяется автоматически
- Пользователю не нужно повторно передавать credentials после первоначальной настройки

## Дальнейшее расширение

Архитектура готова к добавлению:

- услуг
- счетов
- расходов
- отчётов
- аналитики
