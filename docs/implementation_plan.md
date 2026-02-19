# Implementation Plan (MVP)

## Phase 1: Foundation
1. DB bootstrap from `docs/schema_v1.sql`.
2. File scanner/indexer (incremental, background thread).
3. Events (`new/updated/removed`) logging.

## Phase 2: Catalog UX
Status: 3/3 complete (MVP).
1. [x] List with search, date filter, favorites, categories.
2. [x] Preview cache generation (thumb/cardsheet).
3. [x] Model card with metadata (MVP format: in-viewport overlay in 3D window).
3.1 UX format: overlay in 3D viewport, toggle by `F1`.
3.2 Overlay content: file name, object/material/submesh counts, vertex/triangle counts, UV count, texture candidate count, selected channel textures, alpha/projection/shadow state.
3.3 Data source: `payload.debug_info` + `submeshes` + current channel assignments from UI.
3.4 States: hidden by default; auto-refresh on model load and material/channel changes.
3.5 Performance: no blocking IO in render path; overlay text is prebuilt from current state.
3.6 Implementation:
3.6.1 `OpenGLWidget`: `overlay_visible`, `overlay_lines`.
3.6.2 `OpenGLWidget` API: `set_overlay_lines(lines)`, `set_overlay_visible(visible)`, `toggle_overlay()`.
3.6.3 `MainWindow`: `QShortcut(Qt.Key_F1, self)` for toggle.
3.6.4 `MainWindow`: `_refresh_overlay_data()` builds and pushes overlay text lines.
3.6.5 Overlay rendering path: UI-layer overlay widget above 3D viewport (no changes to shadow pipeline).
3.7 Acceptance:
3.7.1 Pressing `F1` toggles overlay instantly.
3.7.2 Overlay values update after model load and material reassignment.
3.7.3 Overlay values match debug info and selected textures.

## Phase 3: Pipelines + Validation
1. Parse rules from `docs/profiles.yaml`.
2. Coverage statuses per pipeline (`ready/partial/missing`).
3. Validation results panel and filters.

## Phase 4: Requests/Tasks
1. Analyst request cards + references.
2. Assignee/status workflow for modelers.
3. Link tasks to assets and pipeline targets.

## Phase 5: Export
1. Selected assets queue.
2. Export to folder / zip-per-model / single zip.
3. Manifest generation and screenshots.

## Phase 6: Integrations
1. Add optional YouTrack adapter.
2. Sync local request <-> external issue.


# План реализации (MVP)

## Этап 1: Основа
1. Инициализация базы данных из `docs/schema_v1.sql`.
2. Сканер/индексатор файлов (инкрементально, в фоновом потоке).
3. Логирование событий (`new/updated/removed`).

## Этап 2: UX каталога
Статус: 3/3 выполнено (MVP).
1. [x] Список с поиском, фильтром по дате, избранным и категориями.
2. [x] Генерация кэша предпросмотра (миниатюры/карточки).
3. [x] Карточка модели с метаданными (MVP-формат: оверлей в окне 3D).
3.1 Формат UX: оверлей в 3D viewport, переключение по `F1`.
3.2 Содержимое оверлея: имя файла, число объектов/материалов/сабмешей, число вершин/треугольников, UV count, число кандидатов текстур, выбранные текстуры по каналам, состояние alpha/projection/shadow.
3.3 Источник данных: `payload.debug_info` + `submeshes` + текущие назначения каналов из UI.
3.4 Состояния: по умолчанию скрыт; автообновление при загрузке модели и при смене материалов/каналов.
3.5 Производительность: без блокирующего IO в рендер-пути; текст оверлея формируется заранее из текущего состояния.
3.6 Реализация:
3.6.1 `OpenGLWidget`: `overlay_visible`, `overlay_lines`.
3.6.2 API `OpenGLWidget`: `set_overlay_lines(lines)`, `set_overlay_visible(visible)`, `toggle_overlay()`.
3.6.3 `MainWindow`: `QShortcut(Qt.Key_F1, self)` для переключения.
3.6.4 `MainWindow`: `_refresh_overlay_data()` собирает и отправляет строки оверлея.
3.6.5 Отрисовка оверлея: UI-слой поверх 3D viewport (без изменений shadow pipeline).
3.7 Критерии приемки:
3.7.1 Нажатие `F1` мгновенно переключает оверлей.
3.7.2 Значения оверлея обновляются после загрузки модели и смены материалов.
3.7.3 Значения оверлея совпадают с debug info и выбранными текстурами.

## Этап 3: Конвейеры и валидация
1. Разбор правил из `docs/profiles.yaml`.
2. Статусы покрытия по конвейерам (`ready/partial/missing`).
3. Панель результатов валидации и фильтры.

## Этап 4: Запросы/задачи
1. Карточки запросов аналитика + ссылки.
2. Workflow назначения исполнителей и статусов для моделлеров.
3. Привязка задач к ассетам и целям конвейера.

## Этап 5: Экспорт
1. Очередь выбранных ассетов.
2. Экспорт в папку / zip на модель / единый zip.
3. Генерация манифеста и скриншотов.

## Этап 6: Интеграции
1. Добавление опционального адаптера YouTrack.
2. Синхронизация локальных запросов с внешними задачами.
