# Task 01: Гигиена инвариантов в chess

## Overview

Аудит соответствия chess инвариантам `meta/INVARIANTS.md`
(2026-04-22). chess — компактный game-backend, нарушений немного,
но они характерные: logic-слой работает с `dict[str, Any]` при том,
что HTTP-границе типизирована через SDK.

## Мотивация

- Контракт на границе (HTTP) типизирован (`StartRequest`,
  `ActionRequest` из SDK), но сразу за границей превращается в
  `dict[str, Any]` — инвариант #6 нарушен внутри процесса.
- Регистрация в core делается через прямой `httpx.AsyncClient` прямо
  в `main.py` — инвариант #10 нарушен.
- `payload.get("from", "")` в `main.py` — молчаливый дефолт (#5).

## Scope

### #6 — dict[str, Any] в logic.py

- `logic.py:70` — `start_game(players: list[dict[str, Any]]) ->
  dict[str, Any]`: принимать `list[Player]` (из SDK), возвращать
  Pydantic-модель `ChessState` (новая).
- `logic.py:95-101` — `handle_action(..., payload: dict[str, Any], ...)
  -> dict[str, Any] | None`: `payload: MovePayload`, возврат `ChessState
  | None`.
- `main.py:120` — убрать `[p.model_dump() for p in body.players]`,
  передавать `body.players` как есть.

### #5 — Молчаливые дефолты

- `main.py:131-132` — `move_from = body.payload.get("from", "")`,
  `move_to = body.payload.get("to", "")` → валидировать через
  Pydantic-модель `MovePayload` с обязательными полями. Отсутствие →
  422 (ClientError).

### #10 — Регистрация в core через httpx в main.py

- `main.py:43-44` — `async with httpx.AsyncClient(timeout=5) as
  client: resp = await client.post(...)` → вынести в
  `chess/core_registrar.py` (или использовать shared helper из SDK
  если появится). main.py должен вызывать `await
  register_with_core(...)` из клиентского модуля.

### #19 — Длинная функция

- `logic.py:95-167` — `handle_action` (73 строки) — разбить по
  action-типу: `_apply_move`, `_apply_resign`, `_apply_draw_offer`.

### #14 / #27 — /health и версия контракта

- `main.py:111-113` — `/health` возвращает `{"status": "ok"}`.
  Согласно инварианту #14, game-backend объявляет версию контракта
  в health. Вернуть `HealthResponse` из SDK с полем
  `contract_version` (если такое есть в SDK; если нет — добавить в
  SDK первым шагом).
- Добавить `/healthz/live` и `/healthz/ready` (инвариант #27), либо
  задокументировать почему одного `/health` достаточно.

## Acceptance criteria

- `scripts/test.sh chess` — зелёный.
- `scripts/remote.sh chess uv run ruff check .` — чисто.
- `scripts/remote.sh chess uv run ty check .` — без errors.
- `grep -n "dict\[str, Any\]" logic.py main.py` — пусто (либо с
  комментарием «внешний JSON, не схематизируем»).
- `httpx` не импортируется в `main.py` напрямую — только из
  `core_registrar.py`.
- `/health` возвращает версию контракта.
- `payload.get("from", "")` заменено на Pydantic-валидацию.

## Разбивка на коммиты

1. `#6`: `ChessState`, `MovePayload` Pydantic-модели; миграция
   `logic.py` и `main.py`.
2. `#5` + `#19`: декомпозиция `handle_action`.
3. `#10`: `core_registrar.py`.
4. `#14`/`#27`: версия контракта в health + live/ready разделение
   (если SDK поддерживает).

## Не в scope

- #11, #13, #22–#29 — архитектурные, отдельной задачей.
- #16 уже выполнен на границе; дотягивается этой задачей внутрь
  процесса.

## Links

- `meta/INVARIANTS.md` (#5, #6, #10, #14, #19, #27)
- `sdk/python/mimigames_sdk/protocol.py`
