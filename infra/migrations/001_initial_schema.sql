-- ---------------------------------------------------------------------------
-- Migration: 001_initial_schema.sql
-- Production schema for Voice Agent: Users, OAuth Tokens, Sessions, Conversations, Audit
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    name VARCHAR(255),
    preferences JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider VARCHAR(32) NOT NULL,
    encrypted_access_token TEXT NOT NULL,
    encrypted_refresh_token TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    scopes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_provider UNIQUE (user_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_oauth_tokens_user ON oauth_tokens(user_id);

CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(128) PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL,
    reconnect_token VARCHAR(256) UNIQUE,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP WITH TIME ZONE,
    state VARCHAR(32) DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_reconnect ON sessions(reconnect_token);

CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(128) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    user_id VARCHAR(64),
    turn_id VARCHAR(128),
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at);

CREATE TABLE IF NOT EXISTS tool_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(128),
    user_id VARCHAR(64),
    turn_id VARCHAR(128),
    tool_name VARCHAR(64) NOT NULL,
    parameters JSONB,
    status VARCHAR(32) NOT NULL,
    error_message TEXT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tool_audit_user ON tool_audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_tool_audit_session ON tool_audit_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_audit_tool ON tool_audit_logs(tool_name);

