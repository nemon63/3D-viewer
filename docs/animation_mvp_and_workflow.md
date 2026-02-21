# Animation MVP and Animator Workflow

Last update: 2026-02-21

## EN

### 1. Goal
Add animation support to catalog workflows so analysts can review and approve character/simulation animation deliveries.

### 2. MVP scope
1. Input formats:
1.1 FBX with animation clips (phase 1).
1.2 GLTF/GLB with animation clips (phase 1 optional).
1.3 Alembic/simulation cache (phase 2).
2. Playback controls:
2.1 Clip selector.
2.2 Play/Pause.
2.3 Loop toggle.
2.4 Timeline scrub.
2.5 Speed multiplier (0.25x..2.0x).
3. Metadata in catalog:
3.1 Clip names/count.
3.2 Duration and fps.
3.3 Frame range.
3.4 Source file hash/mtime.
3.5 Author and task reference (if provided).

### 3. Team workflow (animator -> reviewer)
1. Animator exports animation into agreed folder structure.
2. Animator provides sidecar metadata (recommended):
`<asset_name>.anim.meta.json` with:
`author`, `task_id`, `notes`, `exported_at`, `source_dcc`.
3. Indexer detects new/updated animation files.
4. Catalog marks item as `new` and logs `animation_added`.
5. Analyst/reviewer opens item, plays clips, verifies quality.
6. Reviewer sets status:
`approved` or `rejected` (with comment).
7. System logs review event with user and timestamp.

### 4. Required DB additions (schema v2)
1. `animations`:
`id`, `asset_id`, `file_path`, `format`, `author`, `task_ref`, `status`, timestamps.
2. `animation_clips`:
`id`, `animation_id`, `clip_name`, `fps`, `start_frame`, `end_frame`, `duration_sec`.
3. `animation_reviews`:
`id`, `animation_id`, `reviewer`, `status`, `comment`, `created_at`.
4. Extend events with animation event types.

### 5. Event taxonomy
1. `animation_added`
2. `animation_updated`
3. `animation_opened`
4. `animation_reviewed`
5. `animation_approved`
6. `animation_rejected`

### 6. UX requirements
1. Animation badge in list/card (`new`, `approved`, etc.).
2. Quick filter: `Has animation`, `Needs review`, `Approved`.
3. Review panel with:
clip info, reviewer actions, comments history.

---

## RU

### 1. Цель
Добавить поддержку анимаций в каталог, чтобы аналитики могли просматривать и утверждать анимационные поставки.

### 2. Область MVP
1. Форматы:
1.1 FBX с клипами (этап 1).
1.2 GLTF/GLB с клипами (опционально этап 1).
1.3 Alembic/кэши симуляции (этап 2).
2. Контролы проигрывания:
2.1 Выбор клипа.
2.2 Play/Pause.
2.3 Loop.
2.4 Scrub по таймлайну.
2.5 Скорость (0.25x..2.0x).
3. Метаданные в каталоге:
3.1 Имена/количество клипов.
3.2 Длительность и fps.
3.3 Диапазон кадров.
3.4 Хэш/mtime исходного файла.
3.5 Автор и ссылка на задачу (если переданы).

### 3. Рабочий процесс (аниматор -> ревью)
1. Аниматор выкладывает анимацию в согласованную структуру папок.
2. Рекомендуется sidecar-мета:
`<asset_name>.anim.meta.json` с полями:
`author`, `task_id`, `notes`, `exported_at`, `source_dcc`.
3. Индексатор обнаруживает новые/обновленные файлы анимаций.
4. Каталог помечает элемент как `new` и логирует `animation_added`.
5. Аналитик/ревьюер открывает элемент и проверяет клипы.
6. Ревьюер выставляет статус:
`approved` или `rejected` (с комментарием).
7. Система пишет событие ревью с пользователем и временем.

### 4. Требуемые изменения БД (schema v2)
1. `animations`:
`id`, `asset_id`, `file_path`, `format`, `author`, `task_ref`, `status`, timestamps.
2. `animation_clips`:
`id`, `animation_id`, `clip_name`, `fps`, `start_frame`, `end_frame`, `duration_sec`.
3. `animation_reviews`:
`id`, `animation_id`, `reviewer`, `status`, `comment`, `created_at`.
4. Расширить типы событий в `events` для анимаций.

### 5. Таксономия событий
1. `animation_added`
2. `animation_updated`
3. `animation_opened`
4. `animation_reviewed`
5. `animation_approved`
6. `animation_rejected`

### 6. UX-требования
1. Бейдж состояния анимации в списке/карточке (`new`, `approved` и т.п.).
2. Быстрые фильтры: `Есть анимация`, `Нужно ревью`, `Утверждено`.
3. Панель ревью:
информация о клипе, действия ревьюера, история комментариев.
