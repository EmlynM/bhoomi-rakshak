-- schema.sql
PRAGMA foreign_keys = ON;

CREATE TABLE crops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE cultivators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE survey_numbers (
    survey_no TEXT PRIMARY KEY,
    village TEXT NOT NULL,
    extent REAL NOT NULL,
    crop_id INTEGER NOT NULL,
    cultivator_id INTEGER NOT NULL,
    FOREIGN KEY (crop_id) REFERENCES crops(id),
    FOREIGN KEY (cultivator_id) REFERENCES cultivators(id)
);

CREATE TABLE claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_no TEXT NOT NULL,
    cultivator_name TEXT NOT NULL,
    claimed_crop TEXT NOT NULL,
    claimed_extent REAL NOT NULL,
    status TEXT DEFAULT 'PENDING',
    locked_by TEXT,
    locked_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    matched_claim_id INTEGER,
    confidence REAL,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE,
    FOREIGN KEY (matched_claim_id) REFERENCES claims(id) ON DELETE CASCADE
);

CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL UNIQUE,
    officer_name TEXT NOT NULL,
    verdict TEXT NOT NULL,
    remark TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);
