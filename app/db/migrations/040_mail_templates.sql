CREATE TABLE mail_templates (
    key TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (char_length(subject) BETWEEN 1 AND 120),
    CHECK (char_length(body) BETWEEN 1 AND 4000)
);
