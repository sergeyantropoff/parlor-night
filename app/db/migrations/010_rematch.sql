CREATE TABLE rematch_offers (
    game_id UUID PRIMARY KEY REFERENCES games (id) ON DELETE CASCADE,
    offered_by UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    status VARCHAR(16) NOT NULL CHECK (status IN ('pending', 'accepted', 'declined')),
    new_game_id UUID REFERENCES games (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
