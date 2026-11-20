-- Initial schema from contracts/storage.md. Applied by the postgres image on first start
-- (/docker-entrypoint-initdb.d). Every statement is idempotent so a manual re-run is safe.
-- jsonb columns hold the contract model of the same name; enum-like columns are text with CHECKs
-- so a contract value added later needs only a new migration that relaxes the CHECK.

BEGIN;

CREATE TABLE IF NOT EXISTS config_documents (
    kind        text        NOT NULL,
    id          text        NOT NULL,
    team        text,
    document    jsonb       NOT NULL,
    yaml        text        NOT NULL,
    version     int         NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    updated_by  jsonb,
    PRIMARY KEY (kind, id)
);
CREATE INDEX IF NOT EXISTS config_documents_team_idx ON config_documents (kind, team);

CREATE TABLE IF NOT EXISTS alerts (
    id                 uuid        PRIMARY KEY,
    rule_id            text        NOT NULL,
    team               text        NOT NULL,
    schema_profile_id  text        NOT NULL,
    source_id          text        NOT NULL,
    fingerprint        text        NOT NULL,
    group_key          text,
    is_group_summary   bool        NOT NULL DEFAULT false,
    group_members      jsonb       NOT NULL DEFAULT '[]'::jsonb,
    severity           text        NOT NULL
        CHECK (severity IN ('debug', 'info', 'warning', 'error', 'critical')),
    title              text        NOT NULL,
    body               text        NOT NULL DEFAULT '',
    fields             jsonb       NOT NULL DEFAULT '[]'::jsonb,
    color              text        NOT NULL DEFAULT 'orange',
    count              int         NOT NULL DEFAULT 1 CHECK (count >= 1),
    first_seen         timestamptz NOT NULL,
    last_seen          timestamptz NOT NULL,
    status             text        NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'acknowledged', 'resolved')),
    runbook_id         text,
    last_event         jsonb       NOT NULL,
    acknowledged_by    jsonb,
    acknowledged_at    timestamptz,
    resolved_by        jsonb,
    resolved_at        timestamptz,
    resolution_reason  text
        CHECK (resolution_reason IN ('manual', 'source_resolved', 'silence')),
    updated_at         timestamptz NOT NULL DEFAULT now()
);
-- Live feed: one team, filtered by status, newest activity first.
CREATE INDEX IF NOT EXISTS alerts_team_status_last_seen_idx
    ON alerts (team, status, last_seen DESC);
-- Dedup fallback and auto-resolve look up the open alert of a rule + fingerprint; resolved
-- alerts are the vast majority over time, so keep them out of the index.
CREATE INDEX IF NOT EXISTS alerts_open_rule_fingerprint_idx
    ON alerts (rule_id, fingerprint) WHERE status <> 'resolved';
-- Rule preview / fix proposals list recent alerts of a rule.
CREATE INDEX IF NOT EXISTS alerts_rule_last_seen_idx ON alerts (rule_id, last_seen DESC);

CREATE TABLE IF NOT EXISTS outbox (
    id          bigserial   PRIMARY KEY,
    kind        text        NOT NULL CHECK (kind IN ('delivery', 'runbook_job')),
    alert_id    uuid        NOT NULL,
    payload     jsonb       NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    relayed_at  timestamptz
);
-- The relay scans only unrelayed rows (FOR UPDATE SKIP LOCKED ORDER BY id LIMIT 500); the
-- partial index stays tiny no matter how large the relayed history grows.
CREATE INDEX IF NOT EXISTS outbox_unrelayed_idx ON outbox (id) WHERE relayed_at IS NULL;

CREATE TABLE IF NOT EXISTS deliveries (
    id            bigint      PRIMARY KEY,  -- = outbox.id, the delivery idempotency key
    alert_id      uuid        NOT NULL,
    team          text        NOT NULL,
    recipient_id  text,                     -- null for the team-wide ui channel
    channel_id    text        NOT NULL,
    channel_type  text        NOT NULL
        CHECK (channel_type IN ('ui', 'email', 'sms', 'phone', 'webhook')),
    purpose       text        NOT NULL
        CHECK (purpose IN ('alert', 'approval_request', 'group_summary')),
    status        text        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'failed', 'delivered', 'dead_lettered', 'suppressed')),
    attempt       int         NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    last_error    text,
    is_fallback   bool        NOT NULL DEFAULT false,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    delivered_at  timestamptz
);
CREATE INDEX IF NOT EXISTS deliveries_alert_idx ON deliveries (alert_id);
-- Load-test "lost == 0" check and ops views look for deliveries that never finished.
CREATE INDEX IF NOT EXISTS deliveries_unfinished_idx ON deliveries (status, created_at)
    WHERE status IN ('pending', 'sent', 'failed');

CREATE TABLE IF NOT EXISTS audit_entries (
    id        bigserial   PRIMARY KEY,
    alert_id  uuid        NOT NULL,
    at        timestamptz NOT NULL DEFAULT now(),
    actor     jsonb       NOT NULL,
    verb      text        NOT NULL,
    outcome   text        NOT NULL DEFAULT 'ok' CHECK (outcome IN ('ok', 'error', 'pending')),
    detail    jsonb       NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS audit_entries_alert_idx ON audit_entries (alert_id, id);

CREATE TABLE IF NOT EXISTS action_runs (
    id            uuid        PRIMARY KEY,
    alert_id      uuid        NOT NULL,
    runbook_id    text        NOT NULL,
    step_index    int         NOT NULL CHECK (step_index >= 0),
    action_id     text        NOT NULL,
    params        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    status        text        NOT NULL
        CHECK (status IN ('pending_approval', 'approved', 'rejected', 'running',
                          'succeeded', 'failed', 'skipped')),
    attempt       int         NOT NULL DEFAULT 1 CHECK (attempt >= 1),
    result        jsonb,
    error         text,
    requested_by  jsonb       NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS action_runs_alert_idx ON action_runs (alert_id, step_index);

CREATE TABLE IF NOT EXISTS approval_requests (
    id             uuid        PRIMARY KEY,
    action_run_id  uuid        NOT NULL,
    alert_id       uuid        NOT NULL,
    team           text        NOT NULL,
    runbook_id     text        NOT NULL,
    step_index     int         NOT NULL CHECK (step_index >= 0),
    action_id      text        NOT NULL,
    params         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    summary        text        NOT NULL,
    approval_code  char(4)     NOT NULL CHECK (approval_code ~ '^[0-9]{4}$'),
    requested_at   timestamptz NOT NULL DEFAULT now(),
    decision       text        CHECK (decision IN ('approve', 'reject')),
    decided_by     jsonb,
    decided_via    text        CHECK (decided_via IN ('ui', 'sms', 'phone')),
    decided_at     timestamptz,
    comment        text
);
-- 'APPROVE 4821' from the phone simulator must resolve to exactly one request, so a code is
-- unique among pending requests only; decided requests free their code for reuse.
CREATE UNIQUE INDEX IF NOT EXISTS approval_requests_pending_code_idx
    ON approval_requests (approval_code) WHERE decision IS NULL;
CREATE INDEX IF NOT EXISTS approval_requests_alert_idx ON approval_requests (alert_id);
CREATE INDEX IF NOT EXISTS approval_requests_pending_team_idx
    ON approval_requests (team, requested_at) WHERE decision IS NULL;

CREATE TABLE IF NOT EXISTS fix_proposals (
    id                     uuid        PRIMARY KEY,
    alert_id               uuid        NOT NULL,
    rule_id                text        NOT NULL,
    runbook_id             text,
    owner_team             text        NOT NULL,
    kind                   text        NOT NULL
        CHECK (kind IN ('threshold', 'fields', 'dedup_window', 'runbook_step', 'other')),
    description            text        NOT NULL,
    proposed_rule          jsonb,
    proposed_runbook_step  jsonb,
    proposed_by            jsonb       NOT NULL,
    status                 text        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected')),
    decided_by             jsonb,
    decided_at             timestamptz,
    decision_comment       text,
    created_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS fix_proposals_owner_status_idx
    ON fix_proposals (owner_team, status, created_at DESC);
CREATE INDEX IF NOT EXISTS fix_proposals_alert_idx ON fix_proposals (alert_id);

CREATE TABLE IF NOT EXISTS runbook_revision_proposals (
    id                  uuid        PRIMARY KEY,
    runbook_id          text        NOT NULL,
    based_on_alert_ids  uuid[]      NOT NULL,
    summary             text        NOT NULL,
    proposed_steps      jsonb       NOT NULL,
    status              text        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'rejected')),
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS runbook_revision_proposals_runbook_idx
    ON runbook_revision_proposals (runbook_id, status);

CREATE TABLE IF NOT EXISTS unknown_schema_samples (
    shape_hash    text        PRIMARY KEY,
    source_id     text        NOT NULL,
    key_paths     text[]      NOT NULL,
    sample_event  jsonb       NOT NULL,
    event_count   int         NOT NULL DEFAULT 1 CHECK (event_count >= 1),
    first_seen    timestamptz NOT NULL DEFAULT now(),
    last_seen     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS unknown_schema_samples_last_seen_idx
    ON unknown_schema_samples (last_seen DESC);

CREATE TABLE IF NOT EXISTS phone_messages (
    id             uuid        PRIMARY KEY,
    recipient_id   text        NOT NULL,
    channel_type   text        NOT NULL CHECK (channel_type IN ('sms', 'phone')),
    "to"           text        NOT NULL,
    text           text        NOT NULL,
    alert_id       uuid        NOT NULL,
    delivery_id    bigint      NOT NULL,
    approval_code  char(4),
    at             timestamptz NOT NULL DEFAULT now()
);
-- A redelivered sms/phone job must not show the message twice in the simulator.
CREATE UNIQUE INDEX IF NOT EXISTS phone_messages_delivery_idx ON phone_messages (delivery_id);
CREATE INDEX IF NOT EXISTS phone_messages_recipient_at_idx ON phone_messages (recipient_id, at DESC);

COMMIT;
