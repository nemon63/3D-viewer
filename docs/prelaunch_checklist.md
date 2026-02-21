# Prelaunch Checklist for Major Expansion

Last update: 2026-02-21

## EN

### 1. Identity and lifecycle
1. Asset has stable identity beyond file path.
2. Asset and animation versioning model is defined.
3. Status transition rules are documented (`new -> in_review -> approved/rejected`).
4. Concurrency policy exists (optimistic lock/version field).

### 2. Access and permissions
1. Role matrix exists (Reader/Analyst/Animator/Lead/Admin).
2. Action-level permissions are mapped (`can_export`, `can_approve`, etc.).
3. User/session model is defined before audit-critical features.

### 3. Audit and accountability
1. Open/download/export/review actions are logged with user and timestamp.
2. Event payload includes result and error context.
3. Activity view exists for operational tracing.

### 4. Data and migration safety
1. Migration strategy from schema v1 to v2 exists.
2. Backup and rollback procedure is documented.
3. Compatibility checks for existing `catalog.db` are defined.

### 5. Performance and reliability
1. Search debounce and non-blocking filtering are implemented.
2. UI rebuild hotspots are removed.
3. Network storage scan behavior is throttled and resilient.
4. Cache policy (size/TTL/cleanup) is defined.

### 6. Delivery and packaging
1. Export job model is defined (job + items + status + logs).
2. Manifest format is fixed and reproducible.
3. Download/export events are traceable per user.

### 7. QA gate
1. Smoke tests cover startup, scan, filter, model load, preview batch, settings restore.
2. Regression test suite covers material overrides and validation.
3. Release checklist is approved by product and technical owners.

---

## RU

### 1. Идентичность и жизненный цикл
1. У ассета есть стабильная идентичность, не завязанная только на путь.
2. Определена модель версионирования ассетов и анимаций.
3. Описаны правила перехода статусов (`new -> in_review -> approved/rejected`).
4. Есть политика конкурентного редактирования (optimistic lock/version).

### 2. Доступ и права
1. Есть матрица ролей (Reader/Analyst/Animator/Lead/Admin).
2. Определены права на уровне действий (`can_export`, `can_approve` и т.д.).
3. Модель user/session определена до внедрения audit-критичных фич.

### 3. Аудит и ответственность
1. Операции open/download/export/review логируются с пользователем и временем.
2. Payload событий содержит результат и контекст ошибки.
3. Есть представление активности для операционного контроля.

### 4. Данные и безопасность миграций
1. Есть стратегия миграции схемы v1 -> v2.
2. Описаны backup и rollback процедуры.
3. Определены проверки совместимости для существующего `catalog.db`.

### 5. Производительность и надежность
1. Реализованы debounce поиска и неблокирующая фильтрация.
2. Убраны точки полного rebuild UI при фильтрах.
3. Сканирование сетевых папок устойчиво и ограничено по нагрузке.
4. Определена политика кэша (размер/TTL/очистка).

### 6. Выдача и упаковка
1. Определена модель export jobs (job + items + статус + логи).
2. Формат манифеста зафиксирован и воспроизводим.
3. События download/export трассируются по пользователю.

### 7. QA-гейт
1. Smoke-тесты покрывают запуск, scan, фильтр, загрузку, batch-превью, restore настроек.
2. Регрессия покрывает overrides материалов и валидацию.
3. Release-чеклист утвержден продуктовым и техническим владельцами.
