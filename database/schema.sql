-- Roman Coin Atlas stores BCE dates as negative integers and CE dates as
-- positive integers. Year zero is invalid in the historical convention.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS coin_types (
    id INTEGER PRIMARY KEY,
    external_id TEXT NOT NULL UNIQUE,
    reference_label TEXT NOT NULL,
    authority TEXT NOT NULL,
    mint TEXT,
    denomination TEXT,
    material TEXT NOT NULL,
    date_start INTEGER NOT NULL CHECK (date_start <> 0),
    date_end INTEGER NOT NULL CHECK (date_end <> 0 AND date_start <= date_end),
    obverse_legend TEXT,
    reverse_legend TEXT,
    obverse_description TEXT,
    reverse_description TEXT,
    source_url TEXT NOT NULL,
    obverse_image_url TEXT,
    reverse_image_url TEXT,
    image_attribution TEXT,
    image_license TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS found_coins (
    id INTEGER PRIMARY KEY,
    inventory_number TEXT NOT NULL UNIQUE,
    documented_title TEXT NOT NULL,
    coin_type_id INTEGER,
    material TEXT,
    weight_grams REAL CHECK (weight_grams IS NULL OR weight_grams > 0),
    diameter_mm REAL CHECK (diameter_mm IS NULL OR diameter_mm > 0),
    notes TEXT NOT NULL DEFAULT '',
    documented_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (coin_type_id) REFERENCES coin_types(id) ON UPDATE RESTRICT ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS coin_images (
    id INTEGER PRIMARY KEY,
    found_coin_id INTEGER NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('obverse', 'reverse')),
    file_path TEXT NOT NULL,
    caption TEXT,
    rights_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (found_coin_id) REFERENCES found_coins(id) ON DELETE CASCADE,
    UNIQUE (found_coin_id, file_path)
);

CREATE INDEX IF NOT EXISTS idx_coin_types_authority_mint
    ON coin_types (authority, mint);
CREATE INDEX IF NOT EXISTS idx_coin_types_date_range
    ON coin_types (date_start, date_end);
CREATE INDEX IF NOT EXISTS idx_found_coins_coin_type_id
    ON found_coins (coin_type_id);
CREATE INDEX IF NOT EXISTS idx_found_coins_documented_at
    ON found_coins (documented_at);
CREATE INDEX IF NOT EXISTS idx_coin_images_found_coin_side
    ON coin_images (found_coin_id, side);
