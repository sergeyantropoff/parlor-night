ALTER TABLE games DROP CONSTRAINT IF EXISTS games_game_type_check;
ALTER TABLE games
    ADD CONSTRAINT games_game_type_check
    CHECK (game_type IN ('chess', 'checkers', 'poker', 'uno', 'durak', 'blackjack', 'preferans', 'go', 'domino', 'nardy', 'yahtzy'));

ALTER TABLE user_settings DROP CONSTRAINT IF EXISTS user_settings_default_game_check;
ALTER TABLE user_settings
    ADD CONSTRAINT user_settings_default_game_check
    CHECK (default_game IN ('chess', 'checkers', 'uno', 'poker', 'durak', 'blackjack', 'preferans', 'go', 'domino', 'nardy', 'yahtzy'));

ALTER TABLE site_settings
    ADD COLUMN IF NOT EXISTS yahtzy_open BOOLEAN NOT NULL DEFAULT TRUE;
