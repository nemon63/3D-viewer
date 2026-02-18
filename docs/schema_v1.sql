-- 3D Asset Catalog schema v1
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER NULL,
    UNIQUE(name, parent_id),
    FOREIGN KEY(parent_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    source_path TEXT NOT NULL UNIQUE,
    favorite INTEGER NOT NULL DEFAULT 0,
    category_id INTEGER NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    FOREIGN KEY(category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS geometries (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    format TEXT NOT NULL,
    polycount INTEGER NULL,
    uv_sets INTEGER NULL,
    bbox_json TEXT NULL,
    size_bytes INTEGER NULL,
    mtime REAL NULL,
    hash_fast TEXT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS texture_files (
    id INTEGER PRIMARY KEY,
    file_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    width INTEGER NULL,
    height INTEGER NULL,
    colorspace TEXT NULL,
    size_bytes INTEGER NULL,
    mtime REAL NULL,
    hash_fast TEXT NULL,
    is_udim INTEGER NOT NULL DEFAULT 0,
    udim_tile INTEGER NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS material_slots (
    id INTEGER PRIMARY KEY,
    geometry_id INTEGER NOT NULL,
    slot_name TEXT NOT NULL,
    source_material_name TEXT NULL,
    FOREIGN KEY(geometry_id) REFERENCES geometries(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pipelines (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS variants (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    pipeline_id INTEGER NOT NULL,
    status TEXT NOT NULL, -- ready | partial | missing
    version TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(asset_id, pipeline_id),
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY(pipeline_id) REFERENCES pipelines(id)
);

CREATE TABLE IF NOT EXISTS channel_bindings (
    id INTEGER PRIMARY KEY,
    variant_id INTEGER NOT NULL,
    material_slot_id INTEGER NULL,
    channel TEXT NOT NULL,
    texture_file_id INTEGER NULL,
    packed_schema TEXT NULL,
    colorspace TEXT NULL,
    FOREIGN KEY(variant_id) REFERENCES variants(id) ON DELETE CASCADE,
    FOREIGN KEY(material_slot_id) REFERENCES material_slots(id) ON DELETE CASCADE,
    FOREIGN KEY(texture_file_id) REFERENCES texture_files(id)
);

CREATE TABLE IF NOT EXISTS binding_udim_tiles (
    id INTEGER PRIMARY KEY,
    binding_id INTEGER NOT NULL,
    udim_tile INTEGER NOT NULL,
    texture_file_id INTEGER NOT NULL,
    UNIQUE(binding_id, udim_tile),
    FOREIGN KEY(binding_id) REFERENCES channel_bindings(id) ON DELETE CASCADE,
    FOREIGN KEY(texture_file_id) REFERENCES texture_files(id)
);

CREATE TABLE IF NOT EXISTS previews (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    kind TEXT NOT NULL, -- thumb | cardsheet | custom
    file_path TEXT NOT NULL,
    width INTEGER NULL,
    height INTEGER NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS validation_results (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    pipeline_id INTEGER NULL,
    severity TEXT NOT NULL, -- info | warn | error
    rule_code TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE,
    FOREIGN KEY(pipeline_id) REFERENCES pipelines(id)
);

CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NULL,
    project TEXT NULL,
    priority TEXT NOT NULL DEFAULT 'normal',
    deadline TEXT NULL,
    status TEXT NOT NULL DEFAULT 'new', -- new | in_progress | review | done | rejected
    created_by TEXT NULL,
    assignee TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    external_issue_id TEXT NULL
);

CREATE TABLE IF NOT EXISTS request_references (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL,
    ref_type TEXT NOT NULL, -- url | file | image
    ref_value TEXT NOT NULL,
    FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS request_pipeline_targets (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL,
    pipeline_id INTEGER NOT NULL,
    FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE,
    FOREIGN KEY(pipeline_id) REFERENCES pipelines(id)
);

CREATE TABLE IF NOT EXISTS request_asset_links (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    role TEXT NOT NULL DEFAULT 'candidate', -- candidate | selected | delivered
    UNIQUE(request_id, asset_id),
    FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NULL,
    event_type TEXT NOT NULL, -- new_asset | updated_asset | removed_asset | validated | exported | request_created
    payload_json TEXT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_assets_name ON assets(name);
CREATE INDEX IF NOT EXISTS idx_assets_updated_at ON assets(updated_at);
CREATE INDEX IF NOT EXISTS idx_assets_favorite ON assets(favorite);
CREATE INDEX IF NOT EXISTS idx_geometries_asset_id ON geometries(asset_id);
CREATE INDEX IF NOT EXISTS idx_textures_filename ON texture_files(filename);
CREATE INDEX IF NOT EXISTS idx_variants_asset_pipeline ON variants(asset_id, pipeline_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_deadline ON requests(deadline);

INSERT OR IGNORE INTO pipelines(code, title) VALUES
('unity_urp', 'Unity URP'),
('unity_standard', 'Unity Standard'),
('unity_hdrp', 'Unity HDRP'),
('unreal', 'Unreal Engine'),
('offline', 'Offline / Production');
