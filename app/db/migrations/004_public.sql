ALTER TABLE users ADD COLUMN referral_code TEXT;
ALTER TABLE users ADD COLUMN referred_by UUID REFERENCES users (id);

UPDATE users
SET referral_code = substr(replace(id::text, '-', ''), 1, 8)
WHERE referral_code IS NULL;

ALTER TABLE users ALTER COLUMN referral_code SET NOT NULL;
ALTER TABLE users ADD CONSTRAINT users_referral_code UNIQUE (referral_code);

ALTER TABLE site_settings
    ADD COLUMN referral_chips INTEGER NOT NULL DEFAULT 100
    CHECK (referral_chips BETWEEN 0 AND 100000);

CREATE TABLE news_posts (
    id UUID PRIMARY KEY,
    title VARCHAR(120) NOT NULL,
    summary TEXT NOT NULL CHECK (char_length(summary) BETWEEN 1 AND 400),
    body TEXT NOT NULL CHECK (char_length(body) BETWEEN 1 AND 4000),
    kind VARCHAR(16) NOT NULL CHECK (kind IN ('update', 'event', 'announce')),
    published_on DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX news_posts_published ON news_posts (published_on DESC, created_at DESC);
