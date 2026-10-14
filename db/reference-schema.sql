-- AI Animation Studio V1.1 foundation migration
-- PostgreSQL 17 compatible. Run in an empty schema through migration tooling.
-- Service transactions, RLS policies and grants must be added before production.
BEGIN;
CREATE TABLE workspaces (id uuid PRIMARY KEY, name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE memberships (
 workspace_id uuid NOT NULL REFERENCES workspaces(id), user_id uuid NOT NULL,
 role text NOT NULL CHECK(role IN ('owner','editor','reviewer','viewer')),
 PRIMARY KEY(workspace_id,user_id)
);
CREATE TABLE projects (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
 title text NOT NULL, revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
 config jsonb NOT NULL DEFAULT '{}', stop_dispatch boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(workspace_id,id)
);
CREATE TABLE scenes (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, project_id uuid NOT NULL,
 position integer NOT NULL CHECK(position>=0), current_revision integer NOT NULL DEFAULT 1,
 UNIQUE(workspace_id,id), UNIQUE(project_id,position),
 FOREIGN KEY(workspace_id,project_id) REFERENCES projects(workspace_id,id)
);
CREATE TABLE scene_revisions (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, scene_id uuid NOT NULL,
 revision integer NOT NULL CHECK(revision>0), duration_ms integer NOT NULL CHECK(duration_ms>0),
 script text NOT NULL, features jsonb NOT NULL, input_hash text NOT NULL,
 approved_by uuid, approved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(scene_id,revision), UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,scene_id) REFERENCES scenes(workspace_id,id)
);
CREATE TABLE assets (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id), project_id uuid NOT NULL,
 kind text NOT NULL, object_key text NOT NULL UNIQUE, content_hash text NOT NULL,
 fingerprint text, metadata jsonb NOT NULL DEFAULT '{}',
 state text NOT NULL CHECK(state IN ('uploading','quarantined','ready','rejected','deleted')),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,project_id) REFERENCES projects(workspace_id,id)
);
CREATE INDEX asset_reuse ON assets(workspace_id,fingerprint) WHERE state='ready';
CREATE TABLE model_versions (
 id uuid PRIMARY KEY, provider text NOT NULL, model_name text NOT NULL, version text NOT NULL,
 capabilities jsonb NOT NULL, active boolean NOT NULL DEFAULT false,
 UNIQUE(provider,model_name,version)
);
CREATE TABLE price_versions (
 id uuid PRIMARY KEY, model_version_id uuid NOT NULL REFERENCES model_versions(id),
 currency char(3) NOT NULL, billing_rule jsonb NOT NULL, source_url text NOT NULL,
 verified_at timestamptz NOT NULL, valid_from timestamptz NOT NULL, valid_until timestamptz NOT NULL,
 CHECK(valid_until>valid_from)
);
CREATE TABLE quotes (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, project_id uuid NOT NULL,
 phase text NOT NULL CHECK(phase IN ('storyboard','video','export','retry')),
 project_revision integer NOT NULL, input_hash text NOT NULL, snapshot jsonb NOT NULL,
 base_micro_usd bigint NOT NULL CHECK(base_micro_usd>=0),
 expected_micro_usd bigint NOT NULL CHECK(expected_micro_usd>=0),
 ceiling_micro_usd bigint NOT NULL CHECK(ceiling_micro_usd>=base_micro_usd),
 expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,id,project_id),
 FOREIGN KEY(workspace_id,project_id) REFERENCES projects(workspace_id,id)
);
CREATE TABLE quote_lines (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, quote_id uuid NOT NULL,
 scene_revision_id uuid, operation_kind text NOT NULL, route_plan jsonb NOT NULL,
 model_version_id uuid REFERENCES model_versions(id), price_version_id uuid REFERENCES price_versions(id),
 max_attempts integer NOT NULL CHECK(max_attempts>0),
 ceiling_micro_usd bigint NOT NULL CHECK(ceiling_micro_usd>=0),
 FOREIGN KEY(workspace_id,quote_id) REFERENCES quotes(workspace_id,id),
 FOREIGN KEY(workspace_id,scene_revision_id) REFERENCES scene_revisions(workspace_id,id)
);
CREATE TABLE budget_accounts (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
 scope_type text NOT NULL CHECK(scope_type IN ('workspace_period','project','run','scene')),
 scope_id uuid NOT NULL, period_start timestamptz NOT NULL, period_end timestamptz,
 limit_micro_usd bigint NOT NULL CHECK(limit_micro_usd>=0),
 spent_micro_usd bigint NOT NULL DEFAULT 0 CHECK(spent_micro_usd>=0),
 held_micro_usd bigint NOT NULL DEFAULT 0 CHECK(held_micro_usd>=0),
 stop_dispatch boolean NOT NULL DEFAULT false, version bigint NOT NULL DEFAULT 0,
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,scope_type,scope_id,period_start),
 CHECK(period_end IS NULL OR period_end>period_start)
 -- Do not CHECK spent+held<=limit: real provider overruns must still be recorded.
);
CREATE TABLE runs (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, project_id uuid NOT NULL, quote_id uuid NOT NULL UNIQUE,
 state text NOT NULL DEFAULT 'queued', snapshot jsonb NOT NULL,
 ceiling_micro_usd bigint NOT NULL CHECK(ceiling_micro_usd>=0),
 stop_dispatch boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,quote_id,project_id) REFERENCES quotes(workspace_id,id,project_id)
);
CREATE TABLE reservations (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, run_id uuid NOT NULL UNIQUE,
 original_micro_usd bigint NOT NULL CHECK(original_micro_usd>=0),
 remaining_micro_usd bigint NOT NULL CHECK(remaining_micro_usd>=0),
 state text NOT NULL CHECK(state IN ('held','partially_settled','closed','reconciliation_pending')),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,id,run_id),
 FOREIGN KEY(workspace_id,run_id) REFERENCES runs(workspace_id,id)
);
CREATE TABLE reservation_accounts (
 workspace_id uuid NOT NULL, reservation_id uuid NOT NULL, account_id uuid NOT NULL,
 PRIMARY KEY(reservation_id,account_id),
 FOREIGN KEY(workspace_id,reservation_id) REFERENCES reservations(workspace_id,id),
 FOREIGN KEY(workspace_id,account_id) REFERENCES budget_accounts(workspace_id,id)
);
CREATE TABLE operations (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, run_id uuid NOT NULL,
 scene_revision_id uuid, reservation_id uuid NOT NULL,
 logical_key text NOT NULL, kind text NOT NULL, attempt_no integer NOT NULL CHECK(attempt_no>0),
 state text NOT NULL DEFAULT 'pending', qc_status text NOT NULL DEFAULT 'pending',
 provider text, provider_request_key text NOT NULL UNIQUE, provider_job_id text,
 allocation_micro_usd bigint NOT NULL CHECK(allocation_micro_usd>=0),
 request_snapshot jsonb NOT NULL, result jsonb, error_code text,
 cancel_requested boolean NOT NULL DEFAULT false, lease_owner text, lease_until timestamptz,
 version bigint NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(workspace_id,id), UNIQUE(run_id,logical_key,attempt_no),
 FOREIGN KEY(workspace_id,run_id) REFERENCES runs(workspace_id,id),
 FOREIGN KEY(workspace_id,reservation_id,run_id) REFERENCES reservations(workspace_id,id,run_id),
 FOREIGN KEY(workspace_id,scene_revision_id) REFERENCES scene_revisions(workspace_id,id)
);
CREATE UNIQUE INDEX operation_provider_job ON operations(provider,provider_job_id) WHERE provider_job_id IS NOT NULL;
CREATE INDEX operation_claim ON operations(state,lease_until);
CREATE TABLE operation_settlements (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, operation_id uuid NOT NULL UNIQUE,
 actual_micro_usd bigint NOT NULL CHECK(actual_micro_usd>=0), provider text NOT NULL,
 external_reference text NOT NULL, usage_snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(provider,external_reference),
 FOREIGN KEY(workspace_id,operation_id) REFERENCES operations(workspace_id,id)
);
CREATE TABLE budget_ledger (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, account_id uuid NOT NULL,
 reservation_id uuid, operation_id uuid, entry_type text NOT NULL
 CHECK(entry_type IN ('HOLD','SETTLE','RELEASE','CREDIT','ADJUST_LIMIT')),
 spent_delta_micro_usd bigint NOT NULL DEFAULT 0, held_delta_micro_usd bigint NOT NULL DEFAULT 0,
 limit_delta_micro_usd bigint NOT NULL DEFAULT 0, dedup_key text NOT NULL,
 metadata jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(account_id,dedup_key),
 FOREIGN KEY(workspace_id,account_id) REFERENCES budget_accounts(workspace_id,id),
 FOREIGN KEY(workspace_id,reservation_id) REFERENCES reservations(workspace_id,id),
 FOREIGN KEY(workspace_id,operation_id) REFERENCES operations(workspace_id,id)
);
CREATE INDEX ledger_account_time ON budget_ledger(account_id,created_at);
CREATE TABLE provider_events (
 id uuid PRIMARY KEY, provider text NOT NULL, external_event_id text NOT NULL,
 payload jsonb NOT NULL, received_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz,
 UNIQUE(provider,external_event_id)
);
CREATE TABLE outbox (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
 aggregate_id uuid NOT NULL, topic text NOT NULL, payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), delivered_at timestamptz,
 attempts integer NOT NULL DEFAULT 0, next_attempt_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX outbox_pending ON outbox(next_attempt_at) WHERE delivered_at IS NULL;
CREATE TABLE idempotency_keys (
 workspace_id uuid NOT NULL REFERENCES workspaces(id), endpoint text NOT NULL, key text NOT NULL,
 request_hash text NOT NULL, response_status integer, response_body jsonb,
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 PRIMARY KEY(workspace_id,endpoint,key)
);
CREATE TABLE audit_events (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
 actor_id uuid, action text NOT NULL, resource_id uuid, details jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now()
);
-- Initial balances and every limit change require ADJUST_LIMIT ledger entries.
-- Closing/re-reserving at period rollover is a domain transaction, not a cron reset.
-- Scope polymorphism requires service validation of scope_id ownership.
COMMIT;
