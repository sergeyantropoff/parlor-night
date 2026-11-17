ALTER TABLE users
    ADD COLUMN last_seen TIMESTAMPTZ,
    ADD COLUMN last_ip VARCHAR(64),
    ADD COLUMN last_country VARCHAR(80),
    ADD COLUMN last_user_agent TEXT,
    ADD COLUMN born_on DATE;

ALTER TABLE games DROP CONSTRAINT IF EXISTS games_game_type_check;
ALTER TABLE games
    ADD CONSTRAINT games_game_type_check
    CHECK (game_type IN ('chess', 'checkers', 'poker', 'uno'));

CREATE TABLE wallets (
    user_id UUID PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    balance INTEGER NOT NULL DEFAULT 500 CHECK (balance >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO wallets (user_id)
SELECT id FROM users
ON CONFLICT (user_id) DO NOTHING;

CREATE TABLE ledger (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    amount INTEGER NOT NULL,
    reason VARCHAR(64) NOT NULL,
    game_id UUID REFERENCES games (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ledger_user ON ledger (user_id, created_at DESC);
CREATE INDEX ledger_game ON ledger (game_id);

CREATE TABLE friendships (
    id UUID PRIMARY KEY,
    requester_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    addressee_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL CHECK (status IN ('pending', 'accepted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (requester_id <> addressee_id),
    UNIQUE (requester_id, addressee_id)
);

CREATE INDEX friendships_addressee ON friendships (addressee_id, status);

CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    sender_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    recipient_id UUID REFERENCES users (id) ON DELETE CASCADE,
    game_id UUID REFERENCES games (id) ON DELETE CASCADE,
    body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 1000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (recipient_id IS NOT NULL OR game_id IS NOT NULL)
);

CREATE INDEX messages_pair ON messages (sender_id, recipient_id, created_at DESC);
CREATE INDEX messages_game ON messages (game_id, created_at);

CREATE TABLE watchers (
    game_id UUID NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (game_id, user_id)
);

CREATE TABLE seekers (
    user_id UUID PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    game_type VARCHAR(16) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
