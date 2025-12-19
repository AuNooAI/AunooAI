-- Create auspex_saved_snippets table for saving chat text selections
-- Migration: create_auspex_saved_snippets
-- Date: 2024-12-18

CREATE TABLE IF NOT EXISTS auspex_saved_snippets (
    id SERIAL PRIMARY KEY,
    user_id TEXT,  -- Can be null for anonymous sessions
    chat_id INTEGER NOT NULL,
    message_id INTEGER,  -- Optional link to specific message
    selected_text TEXT NOT NULL,
    context_before TEXT,  -- ~100 chars before selection
    context_after TEXT,   -- ~100 chars after selection
    note TEXT,            -- User's optional note
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS ix_auspex_snippets_user_id ON auspex_saved_snippets(user_id);
CREATE INDEX IF NOT EXISTS ix_auspex_snippets_chat_id ON auspex_saved_snippets(chat_id);
CREATE INDEX IF NOT EXISTS ix_auspex_snippets_created_at ON auspex_saved_snippets(created_at);
