ALTER TABLE news_posts
    ADD COLUMN IF NOT EXISTS cover_dark VARCHAR(64);

ALTER TABLE news_posts DROP CONSTRAINT IF EXISTS news_posts_cover_dark_check;
ALTER TABLE news_posts ADD CONSTRAINT news_posts_cover_dark_check CHECK (
    cover_dark IS NULL
    OR cover_dark ~ '^[0-9a-f]{32}\.(jpg|png|webp)$'
);
