# Implementation Plan (MVP)

## Phase 1: Foundation
1. DB bootstrap from `docs/schema_v1.sql`.
2. File scanner/indexer (incremental, background thread).
3. Events (`new/updated/removed`) logging.

## Phase 2: Catalog UX
1. List with search, date filter, favorites, categories.
2. Preview cache generation (thumb/cardsheet).
3. Model card with metadata (polycount, UV, textures).

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

## Этап 1: Основа
1. Инициализация базы данных из файла `docs/schema_v1.sql`.
2. Сканер/индексатор файлов (постепенная обработка в фоновом потоке).
3. Логирование событий (`создание/обновление/удаление`).

## Этап 2: Пользовательский интерфейс каталога
1. Список с поиском, фильтром по дате, избранным элементам и категориям.
2. Генерация кэша предпросмотра (миниатюры/карточки).
3. Карточка модели с метаданными (количество полигонов, UV‑развёртка, текстуры).

## Этап 3: Конвейеры + валидация
1. Разбор правил из файла `docs/profiles.yaml`.
2. Статусы покрытия для каждого конвейера (`готово/частично/отсутствует`).
3. Панель результатов валидации и фильтры.

## Этап 4: Запросы/задачи
1. Карточки запросов аналитика + ссылки.
2. Рабочий процесс назначения исполнителей и статусов для моделлеров.
3. Привязка задач к ресурсам и целям конвейера.

## Этап 5: Экспорт
1. Очередь выбранных ресурсов.
2. Экспорт в папку / ZIP‑архив для каждой модели / единый ZIP‑архив.
3. Генерация манифеста и скриншотов.

## Этап 6: Интеграции
1. Добавление опционального адаптера для YouTrack.
2. Синхронизация локальных запросов с внешними задачами.