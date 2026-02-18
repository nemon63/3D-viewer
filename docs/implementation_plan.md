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
