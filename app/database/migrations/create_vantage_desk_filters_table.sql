CREATE TABLE vantage_desk_filters (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,

    -- canonical user identifier:  local:<username>  or  <provider>:<email>
    user_key             TEXT    NOT NULL,

    -- optional: tie the preset to one feed group (NULL means “all groups”)
    group_id             INTEGER,

    -- filter parameters (1-to-1 with currentFilters)
    source_type          TEXT,
    sort_by              TEXT       DEFAULT 'publication_date',
    limit_count          INTEGER    DEFAULT 50,
    search_term          TEXT,
    date_range           TEXT,
    author_filter        TEXT,
    min_engagement       INTEGER,
    starred_filter       TEXT,
    include_hidden       BOOLEAN    DEFAULT 0,
    layout_mode          TEXT       DEFAULT 'cards',
    topic_filter         TEXT,

    -- new single JSON field for combinations
    source_date_combinations TEXT   -- JSON array of objects
);

CREATE INDEX idx_vdf_user
    ON vantage_desk_filters (user_key);

CREATE INDEX idx_vdf_user_group
    ON vantage_desk_filters (user_key, group_id);
