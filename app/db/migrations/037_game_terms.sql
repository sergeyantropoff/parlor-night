CREATE TABLE game_terms (
    game_type VARCHAR(16) PRIMARY KEY,
    win_chips INTEGER NOT NULL CHECK (win_chips BETWEEN 0 AND 100000),
    draw_chips INTEGER NOT NULL CHECK (draw_chips BETWEEN 0 AND 100000),
    limits JSONB NOT NULL DEFAULT '{}'
);

INSERT INTO game_terms (game_type, win_chips, draw_chips, limits)
VALUES
    ('chess', 30, 10, '{}'),
    ('checkers', 30, 10, '{}'),
    ('go', 30, 10, '{}'),
    ('domino', 30, 10, '{}'),
    ('nardy', 30, 10, '{}'),
    ('yahtzy', 30, 10, '{}'),
    ('uno', 30, 10, '{}'),
    ('durak', 30, 10, '{"share": 20}'),
    ('bura', 30, 10, '{}'),
    ('poker', 0, 0, '{"stack": 1000, "small": 5, "big": 10}'),
    ('blackjack', 0, 0, '{"stack": 200, "bets": [10, 25, 50, 100]}'),
    ('preferans', 0, 0, '{"points": 100}')
ON CONFLICT (game_type) DO NOTHING;
