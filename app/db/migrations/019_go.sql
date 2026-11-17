ALTER TABLE games DROP CONSTRAINT IF EXISTS games_game_type_check;
ALTER TABLE games
    ADD CONSTRAINT games_game_type_check
    CHECK (game_type IN ('chess', 'checkers', 'poker', 'uno', 'durak', 'blackjack', 'preferans', 'go'));

ALTER TABLE user_settings DROP CONSTRAINT IF EXISTS user_settings_default_game_check;
ALTER TABLE user_settings
    ADD CONSTRAINT user_settings_default_game_check
    CHECK (default_game IN ('chess', 'checkers', 'uno', 'poker', 'durak', 'blackjack', 'preferans', 'go'));

ALTER TABLE site_settings
    ADD COLUMN IF NOT EXISTS go_open BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE news_posts DROP CONSTRAINT IF EXISTS news_posts_cover_check;
ALTER TABLE news_posts ADD CONSTRAINT news_posts_cover_check CHECK (
    cover IS NULL
    OR cover IN ('light-theme', 'uno-evening', 'welcome', 'card-games', 'go')
    OR cover ~ '^[0-9a-f]{32}\.(jpg|png|webp)$'
);
