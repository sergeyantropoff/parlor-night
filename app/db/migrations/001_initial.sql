CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(32) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(16) NOT NULL CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    token_hash CHAR(64) NOT NULL UNIQUE,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    csrf_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    user_agent TEXT,
    ip_address TEXT
);

CREATE INDEX sessions_user_id ON sessions (user_id);

CREATE TABLE games (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    opponent_id UUID REFERENCES users (id) ON DELETE SET NULL,
    join_code VARCHAR(32) UNIQUE,
    game_type VARCHAR(16) NOT NULL CHECK (game_type IN ('chess', 'checkers')),
    variant VARCHAR(32) NOT NULL,
    mode VARCHAR(32) NOT NULL CHECK (mode IN ('vs_computer', 'free', 'analysis', 'lesson', 'online')),
    player_side VARCHAR(8) NOT NULL CHECK (player_side IN ('white', 'black')),
    status VARCHAR(16) NOT NULL CHECK (status IN ('waiting', 'active', 'finished')),
    initial_position TEXT NOT NULL,
    current_position TEXT NOT NULL,
    result VARCHAR(32) CHECK (result IN ('white_win', 'black_win', 'draw') OR result IS NULL),
    result_reason VARCHAR(64),
    engine_level INTEGER NOT NULL DEFAULT 3 CHECK (engine_level BETWEEN 1 AND 5),
    engine_time_ms INTEGER NOT NULL DEFAULT 1000 CHECK (engine_time_ms BETWEEN 100 AND 10000),
    position_version INTEGER NOT NULL DEFAULT 1,
    creator_flipped BOOLEAN NOT NULL DEFAULT FALSE,
    opponent_flipped BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (opponent_id IS NULL OR opponent_id <> user_id)
);

CREATE INDEX games_user_updated ON games (user_id, updated_at DESC);
CREATE INDEX games_opponent_updated ON games (opponent_id, updated_at DESC);
CREATE INDEX games_user_active ON games (user_id, updated_at DESC) WHERE status IN ('active', 'waiting');

CREATE TABLE game_moves (
    id UUID PRIMARY KEY,
    game_id UUID NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    ply INTEGER NOT NULL CHECK (ply > 0),
    notation TEXT NOT NULL,
    move_payload JSONB NOT NULL,
    position_before TEXT NOT NULL,
    position_after TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (game_id, ply)
);

CREATE TABLE analysis_cache (
    id UUID PRIMARY KEY,
    game_type VARCHAR(16) NOT NULL,
    variant VARCHAR(32) NOT NULL,
    position_hash CHAR(64) NOT NULL,
    engine_name VARCHAR(64) NOT NULL,
    engine_version VARCHAR(128) NOT NULL,
    engine_settings_hash CHAR(64) NOT NULL,
    best_move JSONB NOT NULL,
    evaluation JSONB NOT NULL,
    principal_variation JSONB,
    depth INTEGER,
    nodes INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (
        game_type,
        variant,
        position_hash,
        engine_name,
        engine_version,
        engine_settings_hash
    )
);

CREATE TABLE user_settings (
    user_id UUID PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    theme VARCHAR(16) NOT NULL DEFAULT 'system' CHECK (theme IN ('system', 'light', 'dark')),
    board_style VARCHAR(32) NOT NULL DEFAULT 'classic' CHECK (board_style IN ('classic', 'contrast')),
    default_game VARCHAR(16) NOT NULL DEFAULT 'chess' CHECK (default_game IN ('chess', 'checkers')),
    default_side VARCHAR(8) NOT NULL DEFAULT 'white' CHECK (default_side IN ('white', 'black')),
    analysis_preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE login_attempts (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL,
    ip_address VARCHAR(64) NOT NULL,
    success BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX login_attempts_lookup ON login_attempts (username, ip_address, created_at DESC);

CREATE TABLE rate_events (
    id BIGSERIAL PRIMARY KEY,
    bucket VARCHAR(80) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX rate_events_bucket ON rate_events (bucket, created_at DESC);
