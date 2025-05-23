-- Migration: Add OAuth user tables
-- This migration adds tables for OAuth user management

-- Create oauth_users table
CREATE TABLE IF NOT EXISTS oauth_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    name TEXT,
    provider TEXT NOT NULL,
    provider_id TEXT,
    avatar_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(email, provider)
);

-- Create oauth_sessions table for tracking active sessions
CREATE TABLE IF NOT EXISTS oauth_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    session_token TEXT UNIQUE,
    provider TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES oauth_users (id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_oauth_users_email_provider ON oauth_users (email, provider);
CREATE INDEX IF NOT EXISTS idx_oauth_users_provider ON oauth_users (provider);
CREATE INDEX IF NOT EXISTS idx_oauth_users_active ON oauth_users (is_active);
CREATE INDEX IF NOT EXISTS idx_oauth_sessions_user_id ON oauth_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_oauth_sessions_token ON oauth_sessions (session_token);
CREATE INDEX IF NOT EXISTS idx_oauth_sessions_expires ON oauth_sessions (expires_at);

-- Add sample OAuth admin user (optional - for testing)
-- INSERT OR IGNORE INTO oauth_users (email, name, provider, provider_id, is_active) 
-- VALUES ('admin@example.com', 'OAuth Admin', 'google', 'google_123456', 1);