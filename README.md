# mimigames-chess

Шахматная игра для платформы [MimiGames](https://github.com/mimigames-org/mimigames). Реализует стандартный HTTP-контракт платформы — может использоваться как пример для написания собственной игры.

**Стек:** Python 3.12 · FastAPI · python-chess · uv

---

## Быстрый старт (Docker)

```bash
git clone https://github.com/mimigames-org/chess.git
cd chess

# Запустить игру (без подключения к платформе — для тестирования)
docker compose up --build
```

Игра будет доступна на `http://localhost:8001`.  
UI: `http://localhost:8001/ui`  
Health: `http://localhost:8001/health`

### Подключить к платформе

```bash
# Скопировать пример и заполнить переменные
cp .env.example .env

# Запустить
docker compose up --build
```

При старте игра автоматически зарегистрируется в core и появится в каталоге.

---

## Локальная разработка

```bash
uv sync
uv run uvicorn main:app --reload --port 8001
```

---

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `MIMI_SECRET` | Shared secret — должен совпадать с `MIMI_INTERNAL_SECRET` core | `dev-mimi-secret` |
| `CORE_URL` | URL платформы для авторегистрации, напр. `http://localhost:8000` | — |
| `SELF_BACKEND_URL` | Публичный URL этого бэкенда (core будет слать сюда запросы) | — |
| `SELF_FRONTEND_URL` | URL UI для встраивания в iframe | — |
| `SELF_NAME` | Отображаемое название в каталоге | `Шахматы` |

Если `CORE_URL`, `SELF_BACKEND_URL` или `SELF_FRONTEND_URL` не заданы — авторегистрация пропускается. Удобно для локальной разработки без core.

---

## Тесты

```bash
uv run pytest
```

---

## Поддерживаемые действия

| `action` | `payload` | Описание |
|---|---|---|
| `move` | `{"from": "e2", "to": "e4"}` | Ход фигурой |
| `set_host` | `{"new_host_id": "..."}` | Системное: смена хоста (no-op, возвращает пустую дельту) |

Действие `move` валидируется через python-chess. Невалидный ход → `400 Bad Request`.

---

## Архитектура

```
main.py       — FastAPI app; авторегистрация; /start /action /tick /view /health
logic.py      — чистые функции без состояния; вся игровая логика
ui/           — фронтенд (chess.min.js + MimiSDK)
tests/        — pytest; тесты логики без FastAPI
```

Бэкенд **stateless**: платформа передаёт полное состояние игры в каждом запросе.
