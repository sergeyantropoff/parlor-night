ALTER TABLE games
    ADD COLUMN audience VARCHAR(8) NOT NULL DEFAULT 'closed'
    CHECK (audience IN ('open', 'closed'));

CREATE INDEX games_open_tables
    ON games (updated_at DESC)
    WHERE mode = 'online' AND audience = 'open' AND status IN ('waiting', 'active');
