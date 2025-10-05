-- Add profile_id column to auspex_chats table
-- This allows chat sessions to be associated with organizational profiles

-- Add profile_id column if it doesn't exist
-- SQLite doesn't support IF NOT EXISTS for ADD COLUMN, so we handle errors gracefully
ALTER TABLE auspex_chats ADD COLUMN profile_id INTEGER;

-- Add index for performance on profile_id lookups
CREATE INDEX IF NOT EXISTS idx_auspex_chats_profile_id ON auspex_chats(profile_id);

-- Add composite index for user_id + profile_id queries
CREATE INDEX IF NOT EXISTS idx_auspex_chats_user_profile ON auspex_chats(user_id, profile_id);
