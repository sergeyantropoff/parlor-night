ALTER TABLE user_settings DROP CONSTRAINT user_settings_default_game_check;

ALTER TABLE user_settings
    ADD CONSTRAINT user_settings_default_game_check
    CHECK (default_game IN ('chess', 'checkers', 'uno', 'poker'));
