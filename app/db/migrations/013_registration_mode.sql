ALTER TABLE site_settings
    ADD COLUMN registration_mode TEXT NOT NULL DEFAULT 'closed'
    CHECK (registration_mode IN ('closed', 'referral', 'open'));

UPDATE site_settings
SET registration_mode = 'open'
WHERE registration_open = TRUE;
