DO $$
DECLARE
    name text;
BEGIN
    SELECT con.conname INTO name
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    WHERE rel.relname = 'site_settings'
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) ILIKE '%password_min%';
    IF name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE site_settings DROP CONSTRAINT %I', name);
    END IF;
END $$;

ALTER TABLE site_settings ALTER COLUMN password_min SET DEFAULT 8;
UPDATE site_settings SET password_min = 8;
ALTER TABLE site_settings ADD CONSTRAINT site_settings_password_min_check CHECK (password_min BETWEEN 8 AND 64);
