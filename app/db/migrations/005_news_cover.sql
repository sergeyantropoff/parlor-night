ALTER TABLE news_posts
    ADD COLUMN cover VARCHAR(32)
    CHECK (cover IS NULL OR cover IN ('light-theme', 'uno-evening', 'welcome'));
