# Implementation Plan (v3, stability-first)

Last update: 2026-02-21

## EN

### A. Guiding principle
1. Keep the app operational at all times.
2. Expand functionality incrementally behind clear acceptance criteria.
3. Prioritize current business pain:
3.1 Search performance.
3.2 Animation playback and review flow.

### B. Sequential stages
1. Stage 0 (hardening baseline, mandatory before major changes).
1.1 Freeze and document current behavior.
1.2 Add smoke tests for startup, scan, load model, filter, preview batch.
1.3 Add rollback-safe branch and migration checkpoints.

2. Stage 1 (Search responsiveness, highest priority).
2.1 Add debounce to text filter (`200-300ms`).
2.2 Remove hidden duplicate list rebuild (single source for catalog rendering).
2.3 Keep preview map cache in memory during filtering.
2.4 Add incremental UI update path for filtered results.
Acceptance:
search remains interactive on large folders.

3. Stage 2 (Animation MVP, second highest priority).
3.1 Detect animated assets in scan/index.
3.2 Extract clip metadata (name, fps, duration, frame range).
3.3 Add playback controls (play/pause/loop/scrub/speed).
3.4 Add animation review statuses:
`new`, `in_review`, `approved`, `rejected`.
3.5 Add animation events:
`animation_added`, `animation_opened`, `animation_reviewed`, `animation_approved`, `animation_rejected`.
Acceptance:
new animations are visible and reviewable in app.

4. Stage 3 (Identity, access, accountability).
4.1 Add users and sessions model.
4.2 Implement role-based action permissions.
4.3 Log user-aware events for open/download/export/review.
Acceptance:
all key operations are attributable to user and timestamp.

5. Stage 4 (Delivery workflow).
5.1 Add shortlist basket.
5.2 Add package export wizard (folder / zip-per-asset / single zip).
5.3 Generate manifest and screenshots.
5.4 Record export/download jobs and results.

6. Stage 5 (Requests and integrations).
6.1 Activate request/task UI from schema entities.
6.2 Link requests to assets and pipeline targets.
6.3 Optional YouTrack adapter under feature flag.

### C. Cross-cutting constraints
1. Schema migrations must be explicit (v1 -> v2 -> ...).
2. No blocking operations on UI thread.
3. Keep backward compatibility with current catalog where feasible.
4. Continue moving business logic out of `MainWindow`.

---

## RU

### A. Базовый принцип
1. Программа должна оставаться рабочей на каждом этапе.
2. Расширение идет инкрементально, по четким критериям приемки.
3. Текущие главные боли:
3.1 Производительность поиска.
3.2 Проигрывание и ревью анимаций.

### B. Последовательные этапы
1. Этап 0 (укрепление базы, обязателен перед крупными изменениями).
1.1 Зафиксировать текущее поведение и baseline.
1.2 Добавить smoke-тесты: запуск, scan, загрузка модели, фильтр, batch-превью.
1.3 Подготовить безопасные точки отката и чекпоинты миграций.

2. Этап 1 (поиск и отзывчивость, высший приоритет).
2.1 Debounce для поиска (`200-300ms`).
2.2 Убрать rebuild скрытого дублирующего списка (единый источник каталога).
2.3 Держать preview map в памяти на время фильтрации.
2.4 Добавить инкрементальный путь обновления списка.
Критерий приемки:
поиск остается отзывчивым на больших каталогах.

3. Этап 2 (Animation MVP, второй приоритет).
3.1 Детект анимационных ассетов при scan/index.
3.2 Извлечение метаданных клипов (имя, fps, длительность, диапазон кадров).
3.3 Контролы проигрывания (play/pause/loop/scrub/скорость).
3.4 Статусы ревью:
`new`, `in_review`, `approved`, `rejected`.
3.5 События по анимациям:
`animation_added`, `animation_opened`, `animation_reviewed`, `animation_approved`, `animation_rejected`.
Критерий приемки:
новые анимации видны и проходят ревью в приложении.

4. Этап 3 (идентичность, доступ, ответственность).
4.1 Добавить модель пользователей и сессий.
4.2 Реализовать роли и права на действия.
4.3 Логировать пользовательские события open/download/export/review.
Критерий приемки:
каждая ключевая операция имеет автора и время.

5. Этап 4 (поток выдачи ассетов).
5.1 Добавить корзину отбора.
5.2 Добавить мастер экспорта (folder / zip-per-asset / single zip).
5.3 Генерировать манифест и скриншоты.
5.4 Логировать export/download jobs и результат.

6. Этап 5 (заявки и интеграции).
6.1 Подключить UI заявок/задач из сущностей схемы.
6.2 Связать заявки с ассетами и целевыми пайплайнами.
6.3 Опциональный адаптер YouTrack через feature flag.

### C. Сквозные ограничения
1. Миграции схемы должны быть явными (v1 -> v2 -> ...).
2. Никаких блокирующих операций в UI-потоке.
3. По возможности сохранять совместимость с текущим каталогом.
4. Продолжать разгружать `MainWindow` от бизнес-логики.
