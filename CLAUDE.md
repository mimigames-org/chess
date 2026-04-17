# CLAUDE.md — mimigames-chess

## Команды

```bash
uv sync                                        # установить зависимости
uv run uvicorn main:app --reload --port 8001   # запустить
uv run pytest                                  # тесты
uv run ruff check .                            # линтинг
uv run ruff format .                           # форматирование
```

## Git Hooks

Проект использует кастомные githooks из `.githooks/`. **Обязательно** включи их перед началом работы:

```bash
git config core.hooksPath .githooks
```

### pre-commit
- `ruff check .` — линтинг
- `ty check .` — type checking

### pre-push
- `pytest` с coverage (≥75%)
- `pip-audit` — аудит зависимостей

**Все агенты обязаны включить githooks (`git config core.hooksPath .githooks`) при первом checkout.**

## CI

`.github/workflows/ci.yml`: lint → typecheck → audit → test (coverage ≥75%, diff-cover ≥80% на PR) → trigger e2e при merge в main.

## Архитектура

```
main.py    — FastAPI; авторегистрация в core; эндпоинты контракта
logic.py   — чистые функции (start_game, handle_action, get_view)
ui/        — статический фронтенд (chess.min.js + MimiSDK)
tests/     — pytest (тестируют только logic.py)
```

## Структура состояния

```json
{
  "board": {"e2": "wP", "e4": null, ...},
  "turn": "white",
  "players": {"white": "player_id_1", "black": "player_id_2"},
  "status": "active",
  "host_id": "player_id_1"
}
```

`status`: `active` | `check` | `checkmate` | `stalemate`

Коды фигур: `w`/`b` + символ (`P`, `N`, `B`, `R`, `Q`, `K`). Пример: `wP` — белая пешка, `bK` — чёрный король.

## Контракт с платформой

Игра реализует стандартный HTTP-контракт MimiGames:

- `POST /start` — инициализирует доску, случайно раздаёт цвета
- `POST /action` — обрабатывает `move` и `set_host`; невалидный ход → `400`
- `POST /tick` — всегда `204 No Content` (таймаут хода не реализован)
- `POST /view` — возвращает полный снапшот для игрока (или публичный для спектатора)
- `GET /health` — `{"status": "ok"}`

Все запросы валидируются по заголовку `X-Mimi-Secret`.

## Авторегистрация

При старте `_register_self()` запускается как фоновая задача и повторяет `POST {CORE_URL}/games` каждые 5 секунд до успеха. Если переменные окружения не заданы — пропускается.

## Зависимости

- `python-chess` — валидация ходов и представление доски
- `fastapi` + `uvicorn` — HTTP сервер
- `httpx` — async HTTP для авторегистрации
