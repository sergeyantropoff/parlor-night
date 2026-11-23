ALTER TABLE site_settings
    ADD COLUMN mail_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN mail_host TEXT NOT NULL DEFAULT '',
    ADD COLUMN mail_port INTEGER NOT NULL DEFAULT 587,
    ADD COLUMN mail_security TEXT NOT NULL DEFAULT 'starttls',
    ADD COLUMN mail_username TEXT NOT NULL DEFAULT '',
    ADD COLUMN mail_password TEXT NOT NULL DEFAULT '',
    ADD COLUMN mail_from_name TEXT NOT NULL DEFAULT '',
    ADD COLUMN mail_from TEXT NOT NULL DEFAULT '';

ALTER TABLE site_settings
    ADD CONSTRAINT site_settings_mail_port_check CHECK (mail_port BETWEEN 1 AND 65535),
    ADD CONSTRAINT site_settings_mail_security_check CHECK (mail_security IN ('none', 'starttls', 'ssl')),
    ADD CONSTRAINT site_settings_mail_host_check CHECK (char_length(mail_host) <= 253),
    ADD CONSTRAINT site_settings_mail_username_check CHECK (char_length(mail_username) <= 200),
    ADD CONSTRAINT site_settings_mail_password_check CHECK (char_length(mail_password) <= 200),
    ADD CONSTRAINT site_settings_mail_from_name_check CHECK (char_length(mail_from_name) <= 80),
    ADD CONSTRAINT site_settings_mail_from_check CHECK (char_length(mail_from) <= 200);
