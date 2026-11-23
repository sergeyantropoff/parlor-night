ALTER TABLE messages ADD COLUMN kind VARCHAR(16) NOT NULL DEFAULT 'chat';
ALTER TABLE messages ADD CONSTRAINT messages_kind_check CHECK (kind IN ('chat', 'feedback'));

DO $$
DECLARE
  cname text;
BEGIN
  SELECT con.conname INTO cname
  FROM pg_constraint AS con
  WHERE con.conrelid = 'messages'::regclass
    AND con.contype = 'c'
    AND pg_get_constraintdef(con.oid) ILIKE '%char_length(body)%';
  IF cname IS NOT NULL THEN
    EXECUTE format('ALTER TABLE messages DROP CONSTRAINT %I', cname);
  END IF;
END $$;

ALTER TABLE messages
  ADD CONSTRAINT messages_body_len CHECK (char_length(body) BETWEEN 1 AND 4500);

INSERT INTO users (id, username, password_hash, role, is_active, referral_code, full_name)
VALUES (
  'c0ffee00-0000-4000-8000-0000000000f1',
  'contact.desk',
  '!',
  'user',
  FALSE,
  'contactdesk',
  'Обратная связь'
)
ON CONFLICT (id) DO NOTHING;
