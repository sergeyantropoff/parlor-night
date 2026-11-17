CREATE TABLE api_clients (
    id TEXT PRIMARY KEY CHECK (id ~ '^[a-z][a-z0-9-]{1,62}$'),
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('first_party', 'third_party')),
    secret_hash CHAR(64),
    redirect_uris TEXT[] NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE api_grants (
    id UUID PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES api_clients (id),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    code_hash CHAR(64) NOT NULL UNIQUE,
    redirect_uri TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE api_tokens (
    id UUID PRIMARY KEY,
    family_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    client_id TEXT NOT NULL REFERENCES api_clients (id),
    kind TEXT NOT NULL CHECK (kind IN ('access', 'refresh')),
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    replaced_by UUID,
    user_agent TEXT,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX api_tokens_family ON api_tokens (family_id);
CREATE INDEX api_tokens_user ON api_tokens (user_id);

INSERT INTO api_clients (id, name, kind)
VALUES
    ('parlor-ios', 'Parlor Night для iOS', 'first_party'),
    ('parlor-android', 'Parlor Night для Android', 'first_party');
