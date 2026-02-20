# Pipeline Export Requirements

## 1. Цель

Дать пользователю возможность собрать выбранные модели в целевой пайплайн (`unreal`, `unity_urp`, `unity_standard` и т.д.) через экспортную корзину.

## 2. Источники каналов

Минимально поддерживаются входные каналы:

- `basecolor`
- `normal`
- `metal` / `metallic`
- `roughness`
- `ao` / `occlusion`
- `smoothness`
- `orm`

## 3. Правило упаковки ORM

При генерации `ORM` используется схема:

- `R = AO`
- `G = Roughness` (или `1 - Smoothness`, если roughness отсутствует)
- `B = Metallic`
- `A = 255` (по умолчанию)

Если в материале уже есть карта `*_ORM`, она должна использоваться как источник без повторной упаковки.

## 4. Normal Map Space

Unity и Unreal используют разные конвенции направления `Y` в normal map.

- `unity -> unreal`: инвертировать `G` канал
- `unreal -> unity`: инвертировать `G` канал
- `unity -> unity` или `unreal -> unreal`: без изменений

Режим `Auto` в просмотре определяет space по имени файла (`dx/unreal` vs `ogl/unity`), fallback: `unity`.

## 5. Экспортная корзина (следующий этап UI)

Минимальный сценарий:

1. Пользователь добавляет модели в корзину.
2. Выбирает целевой пайплайн.
3. Выбирает целевую папку экспорта.
4. Нажимает `Export`.
5. Программа копирует геометрию и подготавливает/конвертирует текстуры под выбранный пайплайн.

## 6. Реализованный backend (текущий этап)

Файл: `viewer/services/pipeline_export.py`

- `detect_existing_orm_path(texture_paths)`
- `build_orm_map(...)`
- `convert_normal_map_space(...)`
- `derive_orm_sources_from_material(texture_paths)`

UI корзины и массовый экспорт моделей — следующий этап.

