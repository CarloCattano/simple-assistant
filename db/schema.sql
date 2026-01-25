-- Conversation history table for Telegram bot
CREATE TABLE IF NOT EXISTS conversation_history (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    user_id BIGINT,
    role VARCHAR(32) NOT NULL,  -- 'user', 'assistant', 'tool', etc.
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
