CREATE TABLE chat_reads (
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    peer_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, peer_id)
);
