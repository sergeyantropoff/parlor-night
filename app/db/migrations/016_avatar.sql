ALTER TABLE users
    ADD COLUMN avatar TEXT;

ALTER TABLE users
    ADD CONSTRAINT users_avatar_name
    CHECK (avatar IS NULL OR avatar ~ '^[0-9a-f]{32}\.(jpg|png|webp)$');
