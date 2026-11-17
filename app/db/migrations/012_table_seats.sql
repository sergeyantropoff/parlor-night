CREATE TABLE game_seats (
    game_id UUID NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    seat_key VARCHAR(8) NOT NULL,
    kind VARCHAR(16) NOT NULL CHECK (kind IN ('human', 'computer')),
    user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    PRIMARY KEY (game_id, seat_key)
);

CREATE INDEX game_seats_user ON game_seats (user_id) WHERE user_id IS NOT NULL;

DO $$
DECLARE
    name text;
BEGIN
    SELECT con.conname INTO name
    FROM pg_constraint AS con
    JOIN pg_class AS rel ON rel.oid = con.conrelid
    WHERE rel.relname = 'games'
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%white_win%';
    IF name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE games DROP CONSTRAINT %I', name);
    END IF;
END $$;

ALTER TABLE games ADD CONSTRAINT games_result_check CHECK (
    result IS NULL
    OR result IN ('white_win', 'black_win', 'draw')
    OR result ~ '^p[0-5]_win$'
);
