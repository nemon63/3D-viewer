# 3D Asset Catalog Specification (v2, aligned)

Last update: 2026-02-21

## EN

### 1. Product mission
Build a practical desktop-first asset browser for 3D teams, analysts, and developers:
1. Browse very large model libraries quickly.
2. Validate pipeline readiness.
3. Track changes and operational history.
4. Package selected assets for downstream usage.

### 2. Primary users
1. Analyst: find, compare, shortlist, request assets.
2. Modeler: check compliance, fix missing maps, prepare variants.
3. Developer/Integrator: get approved assets with predictable texture sets.
4. Team lead: monitor coverage gaps and asset lifecycle.

### 3. Current implementation baseline
1. Desktop app with OpenGL viewport and floating docks.
2. Directory scanning and SQLite index (`catalog.db`).
3. Preview cache and batch preview generation.
4. Category/favorite/search filters.
5. Material overrides, texture-set matching, per-pipeline validation panel.
6. Fast/Quality render modes, alpha handling, shadows, two-sided toggle.
7. Events for indexing/favorites/texture override operations.

### 4. Gaps to target system
1. Search performance degrades on large lists due to full UI rebuild per keystroke.
2. No first-class user identity and session model in audit records.
3. No explicit download/export history per user.
4. Request/task flow exists in schema but is not integrated in UI workflows.
5. Packaging/export UX is not yet production-ready.

### 5. Required capabilities (target)
1. Preview-first catalog mode with responsive search at scale.
2. Asset lifecycle history:
`created`, `updated`, `removed`, `opened`, `downloaded`, `exported`, `validated`.
3. User-aware audit trail:
`who`, `when`, `what`, `where`, `result`.
4. Pipeline readiness matrix:
Unity URP, Unity Standard, Unity HDRP, Unreal, Offline.
5. Selection and delivery flow:
shortlist -> package -> manifest -> handoff.
6. Animation review flow:
new animation detected -> preview/playback -> review -> approve/reject.

### 6. Data and architecture direction
1. Keep SQLite for local/offline MVP.
2. Add schema v2 for user/session/access events.
3. Keep business logic in controllers/services, minimize UI business code.
4. Prepare optional server mode later (shared DB/API) without rewriting viewer.
5. Extend data model for animation entities and review states.

### 6.1 Animation scope (new)
1. Supported domains:
1.1 Character skeletal animations (FBX/GLTF).
1.2 Simulation caches (phase 2, Alembic/point cache).
2. Catalog must store:
2.1 Animation file path and source character/asset link.
2.2 Clip metadata (name, duration, fps, frame range).
2.3 Author/source metadata (who exported, when, from which task).
2.4 Review status (`new`, `in_review`, `approved`, `rejected`) and reviewer comments.
3. Viewer must support:
3.1 Play/pause/loop/scrub.
3.2 Clip selection.
3.3 Basic speed control.

### 7. Non-functional constraints
1. Non-blocking UI for scan, load, preview, validation.
2. Stable behavior on network/shared folders.
3. Deterministic material assignment and validation outputs.
4. Backward compatibility for existing `catalog.db` where possible.
5. Animation ingestion should not block regular model browsing.

---

## RU

### 1. Миссия продукта
Сделать практичный каталог ассетов для 3D-команды, аналитиков и разработчиков:
1. Быстрый просмотр больших библиотек моделей.
2. Проверка готовности под пайплайны.
3. Учет изменений и операционной истории.
4. Передача выбранных моделей в работу через упаковку.

### 2. Основные роли
1. Аналитик: ищет, сравнивает, отбирает, формирует потребности.
2. Моделлер: проверяет соответствие требованиям, закрывает недостающие карты.
3. Разработчик/интегратор: получает согласованные ассеты.
4. Руководитель: контролирует покрытие и жизненный цикл ассетов.

### 3. Текущее состояние реализации
1. Desktop-приложение с OpenGL viewport и плавающими доками.
2. Сканирование директорий и индекс в SQLite (`catalog.db`).
3. Кэш превью и batch-генерация превью.
4. Фильтры по категориям/избранному/поиску.
5. Overrides материалов, сопоставление texture set, панель валидации.
6. Режимы рендера Fast/Quality, alpha, тени, two-sided.
7. События по индексации/избранному/override.

### 4. Разрывы до целевой системы
1. Поиск тормозит на больших списках из-за полного rebuild UI на каждый символ.
2. Нет полноценных сущностей пользователя и сессии в аудит-данных.
3. Нет явной истории скачиваний/экспортов по пользователям.
4. Поток заявок/задач есть в схеме, но слабо интегрирован в UI.
5. UX упаковки/экспорта не доведен до production.

### 5. Обязательные возможности (цель)
1. Режим каталога на превью с быстрым поиском на больших объемах.
2. История жизненного цикла ассета:
`created`, `updated`, `removed`, `opened`, `downloaded`, `exported`, `validated`.
3. Пользовательский аудит:
`кто`, `когда`, `что`, `где`, `результат`.
4. Матрица готовности под пайплайны:
Unity URP, Unity Standard, Unity HDRP, Unreal, Offline.
5. Поток передачи ассетов:
отбор -> пакет -> манифест -> передача.
6. Поток анимаций:
обнаружение -> просмотр/проигрывание -> ревью -> утверждение/отклонение.

### 6. Вектор архитектуры
1. SQLite сохраняется для локального/offline MVP.
2. Добавляется schema v2 для пользователей/сессий/access events.
3. Бизнес-логика в controllers/services, разгрузка UI.
4. Подготовка к опциональному серверному режиму без переписывания viewer.
5. Расширение модели данных сущностями анимаций и статусов ревью.

### 6.1 Область анимации (новое)
1. Поддерживаемые направления:
1.1 Скелетные анимации персонажей (FBX/GLTF).
1.2 Кэши симуляций (этап 2, Alembic/point cache).
2. В каталоге хранить:
2.1 Путь к анимации и связь с персонажем/ассетом.
2.2 Метаданные клипа (имя, длительность, fps, диапазон кадров).
2.3 Авторские данные (кто экспортировал, когда, из какой задачи).
2.4 Статус ревью (`new`, `in_review`, `approved`, `rejected`) и комментарии.
3. Во viewer поддержать:
3.1 Play/pause/loop/scrub.
3.2 Выбор клипа.
3.3 Базовый контроль скорости.

### 7. Нефункциональные требования
1. UI не должен блокироваться при scan/load/preview/validation.
2. Стабильная работа с сетевыми/общими папками.
3. Детерминированное назначение материалов и валидация.
4. Максимальная совместимость с существующим `catalog.db`.
5. Импорт/индексация анимаций не должны блокировать просмотр обычных моделей.
