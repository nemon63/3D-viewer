# Implementation Plan (MVP)

## Phase 1: Foundation
1. DB bootstrap from `docs/schema_v1.sql`.
2. File scanner/indexer (incremental, background thread).
3. Events (`new/updated/removed`) logging.

## Phase 2: Catalog UX
Status: 2/3 complete.
1. [x] List with search, date filter, favorites, categories.
2. [x] Preview cache generation (thumb/cardsheet).
3. [ ] Model card with metadata (polycount, UV, textures).
3.1 UX format: in-viewport overlay in 3D window, toggle by `F`.
3.2 Overlay content: file name, object/material counts, poly/tri counts, vertex count, UV set count, UV coverage, texture channels and resolved paths.
3.3 Data source: `payload.debug_info` + `submeshes` + current channel assignments from UI.
3.4 States: hidden by default, visible after `F`, auto-refresh on model load/material override/render mode switch.
3.5 Performance: no blocking IO in paint loop; preformat text on model-load event; cached strings for overlay render.
3.6 Implementation:
3.6.1 Add `overlay_visible` and `overlay_text_lines` to `OpenGLWidget`.
3.6.2 Add `set_overlay_data(dict)` and `toggle_overlay()` API.
3.6.3 Add `QShortcut(Qt.Key_F, self)` in `MainWindow` and connect to `gl_widget.toggle_overlay`.
3.6.4 Build overlay payload in `_on_model_loaded` from model debug + texture bindings.
3.6.5 Draw overlay in `paintGL()` using `QPainter` after 3D pass.
3.7 Acceptance:
3.7.1 Pressing `F` toggles overlay instantly without frame hitch.
3.7.2 Large FBX shows metadata within 100 ms after model appears.
3.7.3 Overlay values match model debug log and selected textures in controls.

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
1. Инициализация базы данных из файла `docs/schema_v1.sql`.
2. Сканер/индексатор файлов (постепенная обработка в фоновом потоке).
3. Логирование событий (`создание/обновление/удаление`).

## Этап 2: Пользовательский интерфейс каталога
Статус: 2/3 выполнено.
1. [x] Список с поиском, фильтром по дате, избранным элементам и категориям.
2. [x] Генерация кэша предпросмотра (миниатюры/карточки).
3. [ ] Карточка модели с метаданными (количество полигонов, UV-развёртка, текстуры).
3.1 Формат UX: оверлей в окне 3D, переключение по клавише `F1`.
3.2 Содержимое оверлея: имя файла, число объектов/материалов, poly/tri count, число вершин, число UV-сетов, покрытие UV, каналы текстур и выбранные пути.
3.3 Источник данных: `payload.debug_info` + `submeshes` + текущие назначения каналов из UI.
3.4 Состояния: по умолчанию скрыт, после `F` показывается; автообновление при загрузке модели/смене текстур/смене режима рендера.
3.5 Производительность: без блокирующего IO в `paintGL`; форматирование текста на событии загрузки; кэшированные строки для рендера оверлея.
3.6 Реализация:
3.6.1 Добавить `overlay_visible` и `overlay_text_lines` в `OpenGLWidget`.
3.6.2 Добавить API `set_overlay_data(dict)` и `toggle_overlay()`.
3.6.3 Добавить `QShortcut(Qt.Key_F, self)` в `MainWindow` и связать с `gl_widget.toggle_overlay`.
3.6.4 Формировать payload оверлея в `_on_model_loaded` из debug-данных модели и текущих биндингов текстур.
3.6.5 Рисовать оверлей в `paintGL()` через `QPainter` после 3D-прохода.
3.7 Критерии приёмки:
3.7.1 Нажатие `F` мгновенно переключает оверлей без подтормаживания кадра.
3.7.2 Для больших FBX метаданные появляются не позднее 100 мс после появления модели.
3.7.3 Значения оверлея совпадают с debug-логом модели и выбранными текстурами в контролах.

## Этап 3: Конвейеры + валидация
1. Разбор правил из файла `docs/profiles.yaml`.
2. Статусы покрытия для каждого конвейера (`готово/частично/отсутствует`).
3. Панель результатов валидации и фильтры.

## Этап 4: Запросы/задачи
1. Карточки запросов аналитика + ссылки.
2. Рабочий процесс назначения исполнителей и статусов для моделлеров.
3. Привязка задач к ресурсам и целям конвейера.

## Этап 5: Экспорт
1. Очередь выбранных ресурсов.
2. Экспорт в папку / ZIP-архив для каждой модели / единый ZIP-архив.
3. Генерация манифеста и скриншотов.

## Этап 6: Интеграции
1. Добавление опционального адаптера для YouTrack.
2. Синхронизация локальных запросов с внешними задачами.
