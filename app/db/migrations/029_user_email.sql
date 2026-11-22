ALTER TABLE users
    ADD COLUMN email TEXT;

CREATE UNIQUE INDEX users_email_lower ON users (lower(email))
    WHERE email IS NOT NULL AND email <> '';
