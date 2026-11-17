ALTER TABLE news_posts DROP CONSTRAINT IF EXISTS news_posts_cover_check;
ALTER TABLE news_posts ALTER COLUMN cover TYPE VARCHAR(64);
ALTER TABLE news_posts ADD CONSTRAINT news_posts_cover_check CHECK (
    cover IS NULL
    OR cover IN ('light-theme', 'uno-evening', 'welcome')
    OR cover ~ '^[0-9a-f]{32}\.(jpg|png|webp)$'
);
