# Pipeline Export Requirements (aligned)

Last update: 2026-02-21

## EN

### 1. Goal
Provide a reliable packaging/export flow from selected catalog assets into target pipelines:
`unreal`, `unity_urp`, `unity_standard`, `unity_hdrp`, `offline`.

### 2. Input channels
Minimum expected source channels:
1. `basecolor`
2. `normal`
3. `metal` or `metallic`
4. `roughness`
5. `ao` or `occlusion`
6. `smoothness`
7. `orm`

### 3. ORM packing rule
Generated `ORM` layout:
1. `R = AO`
2. `G = Roughness` or `1 - Smoothness`
3. `B = Metallic`
4. `A = 255`

If existing `*_orm` texture is valid, reuse it instead of repacking.

### 4. Normal map convention
1. Unity and Unreal differ by normal `Y` direction.
2. Conversion rule:
`unity <-> unreal` requires green channel inversion.
3. Auto detection by filename tokens is allowed, explicit override preferred.

### 5. Required operational logging
Every export action must emit event records:
1. Who exported (user/session).
2. What was exported (asset list, pipeline, output mode).
3. When and result (success/failure + error message).

### 6. Current implementation status
Implemented backend helpers in `viewer/services/pipeline_export.py`:
1. `detect_existing_orm_path`
2. `build_orm_map`
3. `convert_normal_map_space`
4. `derive_orm_sources_from_material`

Missing yet:
1. End-user export basket workflow in UI.
2. Full package manifest and archive orchestration.
3. Download/export audit UI.

---

## RU

### 1. Цель
Сделать надежный поток упаковки/экспорта выбранных ассетов под целевые пайплайны:
`unreal`, `unity_urp`, `unity_standard`, `unity_hdrp`, `offline`.

### 2. Входные каналы
Минимально ожидаемые каналы:
1. `basecolor`
2. `normal`
3. `metal` или `metallic`
4. `roughness`
5. `ao` или `occlusion`
6. `smoothness`
7. `orm`

### 3. Правило упаковки ORM
Схема `ORM`:
1. `R = AO`
2. `G = Roughness` или `1 - Smoothness`
3. `B = Metallic`
4. `A = 255`

Если есть валидная `*_orm`, использовать её без повторной упаковки.

### 4. Конвенция normal map
1. Unity и Unreal отличаются направлением `Y` в normal.
2. Для конвертации `unity <-> unreal` инвертировать green-канал.
3. Авто-определение по имени допустимо, но явное указание предпочтительнее.

### 5. Обязательное логирование операций
Каждый экспорт должен логироваться:
1. Кто выгрузил (user/session).
2. Что выгружено (список ассетов, пайплайн, формат выдачи).
3. Когда и с каким результатом (успех/ошибка + текст ошибки).

### 6. Текущее состояние реализации
Реализованы backend-функции в `viewer/services/pipeline_export.py`:
1. `detect_existing_orm_path`
2. `build_orm_map`
3. `convert_normal_map_space`
4. `derive_orm_sources_from_material`

Пока отсутствует:
1. Полноценный UI-контур корзины экспорта.
2. Полная упаковка манифеста и архивов.
3. UI для просмотра истории download/export.

