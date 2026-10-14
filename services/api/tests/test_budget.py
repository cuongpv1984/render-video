import os
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg

os.environ.setdefault("STUDIO_OWNER_TOKEN","test-only-owner-token-32-characters-long")
os.environ.setdefault("WORKSPACE_BUDGET_MICRO_USD","20000")
from app.config import settings
from app.domain import save_project,create_quote,accept_quote,settle,cancel,DomainError
from app.models import ProjectInput,QuoteInput,RunInput
from app.db import transaction

@pytest.fixture(autouse=True)
def database():
    if not settings.database_url:pytest.skip("DATABASE_URL is required for real PostgreSQL tests")
    with psycopg.connect(settings.database_url,autocommit=True) as conn:
        conn.execute((Path(__file__).parents[3]/"db"/"001_app.sql").read_text())
        conn.execute("TRUNCATE app_idempotency,app_outbox,app_ledger,app_run_accounts,app_runs,app_quotes,app_accounts,app_projects CASCADE")

def project(client=None,budget=1_000_000,route="motion"):
    p=ProjectInput(client_id=client or str(uuid4()),title="Mây",ratio="16:9",budget_micro_usd=budget,scenes=[dict(client_id="scene1",title="Cảnh 1",script="Xin chào",duration=2,motion=1,route=route,approved=True,art="dawn")])
    return save_project(p,str(uuid4()))

def quote(p,retry=False):return create_quote(QuoteInput(project_id=p["project_id"],retry=retry),str(uuid4()))
def accept(q,key=None):return accept_quote(q["quote_id"],RunInput(accepted_ceiling_micro_usd=q["ceiling_micro_usd"],input_hash=q["input_hash"]),key or str(uuid4()))

def test_fifty_concurrent_runs_cannot_spend_same_workspace_budget():
    quotes=[quote(project()) for _ in range(50)]
    def attempt(q):
        try:return accept(q)
        except DomainError as exc:return exc.code
    with ThreadPoolExecutor(max_workers=50) as pool:results=list(pool.map(attempt,quotes))
    assert sum(isinstance(r,dict) for r in results)==1
    assert results.count("BUDGET_EXCEEDED")==49
    with transaction() as cur:
        cur.execute("SELECT * FROM app_accounts WHERE id LIKE 'workspace:%%'")
        account=cur.fetchone()
        assert account["held_micro"]==20000
        cur.execute("SELECT count(*) AS n FROM app_outbox")
        assert cur.fetchone()["n"]==1

def test_concurrent_idempotency_returns_same_run():
    q=quote(project());k=str(uuid4())
    with ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(lambda _:accept(q,k),range(10)))
    assert len({r["run_id"] for r in results})==1
    with transaction() as cur:
        cur.execute("SELECT count(*) AS n FROM app_ledger WHERE kind='HOLD'")
        assert cur.fetchone()["n"]==2

def test_same_key_different_payload_rejects():
    q=quote(project());k=str(uuid4());accept(q,k)
    with pytest.raises(DomainError) as err:
        accept_quote(q["quote_id"],RunInput(accepted_ceiling_micro_usd=0,input_hash=q["input_hash"]),k)
    assert err.value.code=="IDEMPOTENCY_CONFLICT"

def test_stale_quote_and_expiry():
    p=project("repeat");q=quote(p);project("repeat")
    with pytest.raises(DomainError) as err:accept(q)
    assert err.value.code=="QUOTE_CHANGED"
    q=quote(project())
    with transaction() as cur:cur.execute("UPDATE app_quotes SET expires_at=now()-interval '1 second' WHERE id=%s",(q["quote_id"],))
    with pytest.raises(DomainError) as err:accept(q)
    assert err.value.code=="QUOTE_EXPIRED"

def test_ai_not_configured_never_holds_or_dispatches():
    q=quote(project(route="hero"),True)
    with pytest.raises(DomainError) as err:accept(q)
    assert err.value.code=="PROVIDER_NOT_CONFIGURED"
    with transaction() as cur:
        cur.execute("SELECT count(*) AS n FROM app_runs")
        assert cur.fetchone()["n"]==0

def test_settlement_exactly_once_and_ledger_matches_totals():
    run=accept(quote(project()))
    with ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(lambda _:settle(run["run_id"],15000,"completed"),range(10)))
    assert sum(results)==1
    with transaction() as cur:
        cur.execute("SELECT a.id,a.spent_micro,a.held_micro,sum(l.spent_delta) AS spent,sum(l.held_delta) AS held FROM app_accounts a JOIN app_ledger l ON l.account_id=a.id GROUP BY a.id")
        for row in cur.fetchall():assert (row["spent_micro"],row["held_micro"])==(row["spent"],row["held"])==(15000,0)

def test_provider_overrun_is_recorded_and_blocks_dispatch():
    run=accept(quote(project()));settle(run["run_id"],30000,"completed")
    with transaction() as cur:
        cur.execute("SELECT * FROM app_accounts WHERE id LIKE 'workspace:%%'")
        row=cur.fetchone();assert row["spent_micro"]==30000;assert row["stop_dispatch"]
    with pytest.raises(DomainError) as err:accept(quote(project()))
    assert err.value.code=="BUDGET_EXCEEDED"

def test_cancel_does_not_release_before_worker_confirmation():
    run=accept(quote(project()));cancel(run["run_id"])
    with transaction() as cur:
        cur.execute("SELECT held_micro FROM app_runs WHERE id=%s",(run["run_id"],));assert cur.fetchone()["held_micro"]==20000
    settle(run["run_id"],0,"cancelled")
    with transaction() as cur:
        cur.execute("SELECT held_micro FROM app_runs WHERE id=%s",(run["run_id"],));assert cur.fetchone()["held_micro"]==0

def test_project_budget_failure_rolls_back_all_scopes():
    with pytest.raises(DomainError) as err:accept(quote(project(budget=10000)))
    assert err.value.code=="BUDGET_EXCEEDED"
    with transaction() as cur:
        cur.execute("SELECT coalesce(sum(held_micro),0) AS h FROM app_accounts");assert cur.fetchone()["h"]==0

def test_owner_auth_and_integer_validation():
    from fastapi.testclient import TestClient
    from app.main import app
    client=TestClient(app)
    assert client.get("/api/v1/budget").status_code==401
    assert client.get("/api/v1/budget",headers={"Authorization":f"Bearer {settings.owner_token}"}).status_code==200
    assert client.post("/api/v1/projects",headers={"Authorization":f"Bearer {settings.owner_token}","Idempotency-Key":"test"},json={"client_id":"x","title":"x","budget_micro_usd":1.5,"scenes":[]}).status_code==422

def test_reference_schema_is_valid_postgresql():
    source=(Path(__file__).parents[3]/"db"/"reference-schema.sql").read_text()
    source=source.replace("BEGIN;","").replace("COMMIT;","")
    with psycopg.connect(settings.database_url) as conn:
        conn.execute("CREATE SCHEMA reference_spec_test")
        conn.execute("SET LOCAL search_path TO reference_spec_test")
        conn.execute(source)
        conn.rollback()

def test_worker_cancel_confirms_before_releasing():
    from app.worker import work_once
    run=accept(quote(project()));cancel(run["run_id"])
    assert work_once()
    with transaction() as cur:
        cur.execute("SELECT state,held_micro FROM app_runs WHERE id=%s",(run["run_id"],))
        row=cur.fetchone();assert row["state"]=="cancelled";assert row["held_micro"]==0

def test_expired_worker_lease_keeps_hold():
    from app.worker import claim
    run=accept(quote(project()))
    with transaction() as cur:
        cur.execute("UPDATE app_runs SET state='rendering',lease_until=now()-interval '1 second' WHERE id=%s",(run["run_id"],))
    assert claim() is None
    with transaction() as cur:
        cur.execute("SELECT state,held_micro FROM app_runs WHERE id=%s",(run["run_id"],))
        row=cur.fetchone();assert row["state"]=="needs_reconciliation";assert row["held_micro"]==20000

def test_render_real_mp4_if_ffmpeg_available(tmp_path):
    import shutil
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):pytest.skip("FFmpeg/FFprobe unavailable")
    from app.worker import work_once
    from app.storage import local_path
    run=accept(quote(project()));assert work_once()
    with transaction() as cur:
        cur.execute("SELECT state,held_micro,spent_micro,output_key FROM app_runs WHERE id=%s",(run["run_id"],))
        row=cur.fetchone()
    assert row["state"]=="completed"
    assert row["held_micro"]==0 and row["spent_micro"]==20000
    assert local_path(row["output_key"]).stat().st_size>1000
