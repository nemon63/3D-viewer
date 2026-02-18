# 3D Asset Catalog Specification (v1)

## EN

### 1. Purpose
Build a production-ready 3D asset catalog for analysts and modelers with fast browse, validation, requests/tasks, and export workflows.

### 2. Roles
- Analyst: browse, filter, pick assets, create requests.
- Modeler: process requests, complete missing pipeline variants.
- Lead: track gaps and status.

### 3. Requirements
- Network storage support (UNC paths).
- Preview-first UX (no heavy mesh load by default).
- Pipeline coverage statuses per asset:
  - `ready`
  - `partial`
  - `missing`
- Validation profiles for:
  - Unity URP
  - Unity Standard
  - Unity HDRP
  - Unreal
  - Offline/Production
- Support scenarios:
  - diffuse-only assets,
  - many models sharing one texture,
  - one model with many texture sets,
  - UDIM.

### 4. Main Modules
1. Indexer
- Incremental scan by `path + mtime + size (+ optional hash)`.
- Detect events: `new`, `updated`, `removed`.

2. Catalog DB (SQLite)
- Asset metadata index, variants, channels, validation results, tasks.

3. Preview Service
- Generate thumbnails/cardsheets.
- Cache in local folder.

4. Validation Engine
- Rule-based checks from `profiles.yaml`.

5. Requests/Tasks
- Analyst creates requirement card with references.
- Modelers see queue and status.

6. Export
- Export selected assets to folder or archives.
- Include screenshot(s), manifest, used textures.

### 5. UX Flow
1. Open app.
2. See updates/new assets without loading heavy geometry.
3. Filter/search by name, date, category, pipeline status.
4. Open asset in 3D on demand.
5. Add to selected/export list.

### 6. Performance Rules
- All heavy operations are background jobs.
- Viewer keeps Fast/Quality mode.
- No blocking UI for scanning/loading.

### 7. Integrations
- Local task cards first.
- Optional YouTrack sync later via adapter.

---

## RU (дублирование)

### 1. Назначение
Сделать промышленный каталог 3D-ассетов для аналитиков и моделлеров: быстрый просмотр, валидация, карточки потребностей/задач и экспорт.

### 2. Роли
- Аналитик: ищет, фильтрует, отбирает модели, создаёт потребности.
- Моделлер: обрабатывает задачи, закрывает недостающие пайплайны.
- Руководитель: контролирует пробелы и статусы.

### 3. Требования
- Поддержка сетевого хранилища (UNC пути).
- UX через превью (без тяжёлой загрузки модели по умолчанию).
- Матрица покрытия пайплайнов по каждой модели:
  - `ready`
  - `partial`
  - `missing`
- Профили валидации для:
  - Unity URP
  - Unity Standard
  - Unity HDRP
  - Unreal
  - Offline/Production
- Поддержка кейсов:
  - только diffuse,
  - много моделей на одну текстуру,
  - одна модель с несколькими texture set,
  - UDIM.

### 4. Основные модули
1. Индексатор
- Инкрементальный скан по `path + mtime + size (+ опционально hash)`.
- Детект событий: `new`, `updated`, `removed`.

2. Каталожная БД (SQLite)
- Индекс метаданных ассетов, вариантов, каналов, валидации, задач.

3. Сервис превью
- Генерация thumbnails/cardsheets.
- Кэш в локальной папке.

4. Движок валидации
- Проверки по правилам из `profiles.yaml`.

5. Потребности/задачи
- Аналитик создаёт карточку с описанием и референсами.
- Моделлер видит очередь и статусы.

6. Экспорт
- Экспорт выбранных ассетов в папку или архивы.
- Добавлять скриншоты, manifest и реально используемые текстуры.

### 5. UX-поток
1. Запуск приложения.
2. Просмотр новых/изменённых ассетов без тяжёлой загрузки геометрии.
3. Фильтрация/поиск по имени, дате, категории, статусу пайплайна.
4. Открытие 3D только по запросу.
5. Добавление в выбранные и экспорт.

### 6. Правила производительности
- Все тяжёлые операции выполнять в фоне.
- В viewer оставить Fast/Quality режим.
- Не блокировать UI при сканировании/загрузке.

### 7. Интеграции
- Сначала локальные карточки задач.
- Потом адаптер синхронизации с YouTrack.
