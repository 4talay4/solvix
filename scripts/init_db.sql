CREATE TYPE user_status AS ENUM ('registrando', 'pendiente', 'autorizado', 'rechazado');
CREATE TYPE support_type AS ENUM ('mejora', 'incidencia');
CREATE TYPE support_status AS ENUM ('abierto', 'resuelto', 'cerrado');

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    telegram_username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    nombre VARCHAR(255),
    apellidos VARCHAR(255),
    status user_status NOT NULL DEFAULT 'registrando',
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    authorized_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    bot_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_telegram_id ON users(telegram_id);

CREATE TABLE questions_cache (
    id SERIAL PRIMARY KEY,
    question_text TEXT NOT NULL,
    question_normalized TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    sources_json JSONB NOT NULL DEFAULT '[]',
    embedding_json JSONB,
    hit_count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_questions_cache_normalized ON questions_cache(question_normalized);

CREATE TABLE activity_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    telegram_id BIGINT,
    action VARCHAR(100) NOT NULL,
    detail TEXT,
    metadata_json JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_activity_logs_created ON activity_logs(created_at DESC);
CREATE INDEX idx_activity_logs_user ON activity_logs(user_id);

CREATE TABLE support_tickets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    telegram_id BIGINT NOT NULL,
    telegram_username VARCHAR(255),
    user_display_name VARCHAR(512),
    ticket_type support_type NOT NULL,
    message TEXT NOT NULL,
    status support_status NOT NULL DEFAULT 'abierto',
    resolution_message TEXT,
    resolved_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ
);

CREATE INDEX idx_support_status ON support_tickets(status);

CREATE TABLE question_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    from_cache BOOLEAN NOT NULL DEFAULT FALSE,
    sources_json JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_question_history_user ON question_history(user_id);
CREATE INDEX idx_question_history_created ON question_history(created_at DESC);
