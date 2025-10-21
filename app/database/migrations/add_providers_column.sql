-- Migration: Add providers column for multi-collector support
-- Date: 2025-10-21
-- Description: Adds providers JSON array column to support multiple news collectors

-- Add new providers column with default JSON array
ALTER TABLE keyword_monitor_settings
ADD COLUMN providers TEXT DEFAULT '["newsapi"]';

-- Migrate existing provider value to providers array
-- This ensures backward compatibility
UPDATE keyword_monitor_settings
SET providers = json_array(provider)
WHERE provider IS NOT NULL AND providers IS NULL;

-- For PostgreSQL compatibility, we keep the old provider column
-- Applications should read from providers, but fall back to provider if needed
