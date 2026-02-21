# Model, Material, and Texture Requirements (aligned)

Last update: 2026-02-21

## EN

### 1. Geometry and material assignment
1. Mesh must preserve polygon-to-material assignment in source files.
2. Each polygon must map to a valid material index or explicit fallback.
3. Material names inside one asset should be stable and unique.
4. Avoid one shared material for unrelated surfaces with different map sets.

### 2. Texture naming conventions
1. Use one prefix per material set:
`wood1_dif`, `wood1_met`, `wood1_rough`, `wood1_nml`.
2. Different materials must use different prefixes.
3. Recommended channel suffixes:
3.1 BaseColor: `dif`, `diff`, `diffuse`, `albedo`, `basecolor`.
3.2 Metal: `met`, `metal`, `metallic`.
3.3 Roughness: `rough`, `rgh`, `roughness`.
3.4 Normal: `nml`, `nrm`, `normal`.
4. Avoid ambiguous names like `tex_01.png`.

### 3. Multi-material rules in current viewer
1. Per-material overrides are supported and should be preferred.
2. Global override is for deliberate preview/debug only.
3. Validation readiness is per required channel coverage, not only “any texture exists”.

### 4. Alpha and surface behavior
1. If alpha is used for cutout/blend, BaseColor alpha must be intentional and clean.
2. Two-sided should be enabled only for assets that need it (foliage, cards, thin shells).
3. Normal map space should be explicitly validated for Unity/Unreal conventions.

### 5. Import checklist
1. Every material has at least BaseColor or documented reason why not.
2. Material-to-texture mapping is deterministic and non-overlapping.
3. Exported file preserves material count and names from DCC.
4. Texture paths remain valid after moving project root.

---

## RU

### 1. Геометрия и назначение материалов
1. Меш должен сохранять назначение полигонов на материалы.
2. Каждый полигон должен иметь валидный индекс материала или fallback.
3. Имена материалов в ассете должны быть стабильными и уникальными.
4. Не использовать один материал для разных логических поверхностей.

### 2. Нейминг текстур
1. Для одного material set использовать общий префикс:
`wood1_dif`, `wood1_met`, `wood1_rough`, `wood1_nml`.
2. Для разных материалов использовать разные префиксы.
3. Рекомендуемые суффиксы каналов:
3.1 BaseColor: `dif`, `diff`, `diffuse`, `albedo`, `basecolor`.
3.2 Metal: `met`, `metal`, `metallic`.
3.3 Roughness: `rough`, `rgh`, `roughness`.
3.4 Normal: `nml`, `nrm`, `normal`.
4. Избегать неоднозначных имён типа `tex_01.png`.

### 3. Правила для multi-material в текущем viewer
1. Предпочтительно назначение по выбранному материалу.
2. Глобальный override использовать осознанно для предпросмотра/отладки.
3. Готовность валидации оценивается по покрытию обязательных каналов.

### 4. Alpha и поверхность
1. Если alpha используется для cutout/blend, alpha в BaseColor должна быть корректной.
2. Two-sided включать только там, где это действительно нужно.
3. Normal map space проверять явно для Unity/Unreal.

### 5. Чек-лист перед импортом
1. У каждого материала есть минимум BaseColor или понятная причина отсутствия.
2. Сопоставление материал -> текстуры детерминировано и не пересекается.
3. После экспорта сохраняются число и имена материалов из DCC.
4. Пути к текстурам остаются валидными после переноса корня проекта.
