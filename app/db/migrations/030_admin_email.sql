UPDATE users
SET email = 'admin@admin.local',
    updated_at = now()
WHERE username = 'admin'
  AND (email IS NULL OR btrim(email) = '');
