# Platform Gap Analysis and Next Architecture Steps

Last update: 2026-02-21

## EN

### 1. Objective
Capture blockers that will limit further development for a shared 3D asset service and define practical next steps.

### 2. Critical gaps
1. Search lag on large catalogs.
2. UI rebuild strategy is expensive for each filter keystroke.
3. Audit trail is event-based but not user/session-centric.
4. No explicit download/export history model.
5. Large business surface still concentrated in `MainWindow`.
6. No animation ingestion/playback/review flow yet.

### 3. Why this matters
1. Analysts lose speed during triage.
2. Team lead cannot answer “who took which assets and when”.
3. Cross-team handoff lacks operational traceability.
4. Scaling to network-shared, always-growing libraries becomes risky.

### 4. Required data additions (schema v2 direction)
1. `users`:
`id`, `username`, `display_name`, `role`, `is_active`, timestamps.
2. `sessions`:
`id`, `user_id`, `host`, `started_at`, `ended_at`, `app_version`.
3. `asset_access_events`:
`id`, `asset_id`, `session_id`, `action`, `result`, `payload_json`, `created_at`.
4. `export_jobs`:
job metadata, target pipeline, output mode, destination, status, duration.
5. `export_job_items`:
which assets were included in each export.

### 5. Required UX upgrades
1. Fast filter with debounce and incremental rendering.
2. Dedicated “Activity” panel:
recent opens/downloads/exports with user and timestamp.
3. Basket-based export flow:
select -> review -> export -> result report.
4. Request board:
analyst demand cards, assignment, status transitions.
5. Animation review flow:
new animation detection, playback, approve/reject, review history.

### 6. Suggested delivery sequence
1. Iteration 1:
search performance fix and single-source catalog list rendering.
2. Iteration 2:
schema v2 migration + user/session/event logging.
3. Iteration 3:
export basket with auditable jobs.
4. Iteration 4:
requests/tasks UI and optional tracker integration.

### 7. Stability-first release policy
1. No broad refactor and feature rollout in the same iteration.
2. Every stage starts with baseline smoke checks.
3. New capabilities are feature-flagged where possible.
4. Schema changes require migration scripts and rollback path.
5. Performance regressions are release blockers.

---

## RU

### 1. Цель
Зафиксировать ограничения текущей реализации и определить шаги для перехода к полноценному сервису каталога.

### 2. Критические разрывы
1. Лаги поиска на больших каталогах.
2. Дорогой полный rebuild UI на каждый символ фильтра.
3. События есть, но нет нормальной модели user/session.
4. Нет отдельной истории скачиваний/экспортов.
5. Слишком много бизнес-логики сосредоточено в `MainWindow`.

### 3. Почему это важно
1. Аналитики теряют скорость отбора.
2. Руководитель не может прозрачно ответить “кто и когда взял модель”.
3. Передача ассетов между отделами плохо трассируется.
4. Масштабирование на растущие сетевые библиотеки становится рискованным.

### 4. Нужные изменения данных (направление schema v2)
1. `users`:
`id`, `username`, `display_name`, `role`, `is_active`, timestamps.
2. `sessions`:
`id`, `user_id`, `host`, `started_at`, `ended_at`, `app_version`.
3. `asset_access_events`:
`id`, `asset_id`, `session_id`, `action`, `result`, `payload_json`, `created_at`.
4. `export_jobs`:
метаданные задачи экспорта, pipeline, режим выдачи, путь, статус, длительность.
5. `export_job_items`:
какие ассеты вошли в конкретный экспорт.

### 5. Нужные UX-улучшения
1. Быстрый фильтр с debounce и инкрементальной отрисовкой.
2. Панель “Активность”:
недавние открытия/скачивания/экспорты с пользователем и временем.
3. Поток экспорта через корзину:
отбор -> проверка -> экспорт -> отчет.
4. Доска заявок:
карточки потребностей аналитика, назначение, переходы статусов.

### 6. Рекомендуемая последовательность
1. Итерация 1:
ускорение поиска и единый источник рендеринга каталога.
2. Итерация 2:
миграция schema v2 + логирование user/session/event.
3. Итерация 3:
корзина экспорта с аудитом задач.
4. Итерация 4:
UI заявок/задач и опциональная интеграция с трекером.

### 7. Политика release “сначала стабильность”
1. Нельзя совмещать глубокий рефактор и массовый rollout фич в одной итерации.
2. Каждый этап начинается с smoke-проверки baseline.
3. Новые возможности по возможности включаются через feature flags.
4. Любые изменения схемы требуют миграций и сценария отката.
5. Регресс производительности является блокером релиза.
