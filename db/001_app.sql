-- Runtime schema for the owner-only pilot. This is separate from the reference design.
BEGIN;
CREATE TABLE IF NOT EXISTS app_projects (
 id uuid PRIMARY KEY, client_id text NOT NULL UNIQUE, title text NOT NULL,
 revision integer NOT NULL DEFAULT 1, document jsonb NOT NULL,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS app_accounts (
 id text PRIMARY KEY, limit_micro bigint NOT NULL CHECK(limit_micro>=0),
 spent_micro bigint NOT NULL DEFAULT 0 CHECK(spent_micro>=0),
 held_micro bigint NOT NULL DEFAULT 0 CHECK(held_micro>=0), stop_dispatch boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS app_quotes (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES app_projects(id), revision integer NOT NULL,
 input_hash text NOT NULL, snapshot jsonb NOT NULL, base_micro bigint NOT NULL CHECK(base_micro>=0),
 ceiling_micro bigint NOT NULL CHECK(ceiling_micro>=base_micro), expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS app_runs (
 id uuid PRIMARY KEY, quote_id uuid NOT NULL UNIQUE REFERENCES app_quotes(id),
 project_id uuid NOT NULL REFERENCES app_projects(id), snapshot jsonb NOT NULL,
 state text NOT NULL CHECK(state IN ('queued','rendering','completed','failed','cancelled','needs_reconciliation')),
 held_micro bigint NOT NULL CHECK(held_micro>=0), spent_micro bigint NOT NULL DEFAULT 0 CHECK(spent_micro>=0),
 cancel_requested boolean NOT NULL DEFAULT false, output_key text, error_code text,
 lease_until timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS app_run_accounts (
 run_id uuid NOT NULL REFERENCES app_runs(id), account_id text NOT NULL REFERENCES app_accounts(id),
 PRIMARY KEY(run_id,account_id)
);
CREATE TABLE IF NOT EXISTS app_ledger (
 id uuid PRIMARY KEY, account_id text NOT NULL REFERENCES app_accounts(id), run_id uuid REFERENCES app_runs(id),
 kind text NOT NULL CHECK(kind IN ('HOLD','SETTLE','RELEASE','ADJUST_LIMIT')),
 spent_delta bigint NOT NULL, held_delta bigint NOT NULL, limit_delta bigint NOT NULL DEFAULT 0,
 dedup_key text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(account_id,dedup_key)
);
CREATE TABLE IF NOT EXISTS app_outbox (
 id uuid PRIMARY KEY, run_id uuid NOT NULL UNIQUE REFERENCES app_runs(id),
 delivered_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS app_idempotency (
 endpoint text NOT NULL, key text NOT NULL, request_hash text NOT NULL,
 response jsonb, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(endpoint,key)
);
CREATE INDEX IF NOT EXISTS app_runs_claim ON app_runs(state,created_at);
CREATE INDEX IF NOT EXISTS app_ledger_account ON app_ledger(account_id,created_at);
COMMIT;
