CREATE TABLE site_broadcast (
    id BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    body TEXT NOT NULL DEFAULT '',
    tone TEXT NOT NULL DEFAULT 'info',
    revision UUID NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (char_length(body) <= 500),
    CHECK (tone IN ('info', 'warning', 'ok', 'error'))
);

INSERT INTO site_broadcast (id, body, tone, revision)
VALUES (TRUE, '', 'info', '00000000-0000-0000-0000-000000000000');

CREATE TABLE broadcast_seen (
    user_id UUID PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    revision UUID NOT NULL
);
