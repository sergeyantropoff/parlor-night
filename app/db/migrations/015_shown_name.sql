CREATE OR REPLACE FUNCTION shown_name(full_name text, username text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT COALESCE(
        NULLIF(
            btrim(regexp_replace(replace(COALESCE(full_name, ''), chr(31), ' '), '[[:space:]]+', ' ', 'g')),
            ''
        ),
        username
    );
$$;
