ALTER TABLE news_posts DROP CONSTRAINT IF EXISTS news_posts_body_check;
ALTER TABLE news_posts ADD CONSTRAINT news_posts_body_check CHECK (char_length(body) BETWEEN 1 AND 20000);
