import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from psycopg.types.json import Jsonb
from .config import settings
from .db import transaction

class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code, self.message, self.status = code, message, status

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def route(scene):
    if scene["route"] != "auto":
        return scene["route"]
    return "motion" if scene["motion"] <= 1 else "standard" if scene["motion"] == 2 else "hero"

def _idempotent(cur, endpoint, key, payload):
    cur.execute("INSERT INTO app_idempotency(endpoint,key,request_hash) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (endpoint, key, digest(payload)))
    cur.execute("SELECT * FROM app_idempotency WHERE endpoint=%s AND key=%s FOR UPDATE", (endpoint, key))
    entry = cur.fetchone()
    if entry["request_hash"] != digest(payload):
        raise DomainError("IDEMPOTENCY_CONFLICT", "Idempotency key đã được dùng với nội dung khác.")
    return entry["response"]

def _save_response(cur, endpoint, key, result):
    cur.execute("UPDATE app_idempotency SET response=%s WHERE endpoint=%s AND key=%s", (Jsonb(result), endpoint, key))

def _account(cur, account_id, limit):
    cur.execute("INSERT INTO app_accounts(id,limit_micro) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING id", (account_id, limit))
    if cur.fetchone():
        cur.execute("INSERT INTO app_ledger(id,account_id,kind,spent_delta,held_delta,limit_delta,dedup_key) VALUES (%s,%s,'ADJUST_LIMIT',0,0,%s,'initial')", (uuid4(),account_id,limit))

def save_project(data, key):
    payload = data.model_dump()
    if sum(s["duration"] for s in payload["scenes"]) > 180:
        raise DomainError("DURATION_EXCEEDED", "Video V1.1 tối đa 180 giây.", 422)
    ids = [s["client_id"] for s in payload["scenes"]]
    if len(ids) != len(set(ids)):
        raise DomainError("DUPLICATE_SCENE", "Scene IDs phải khác nhau.", 422)
    endpoint = "/projects"
    with transaction() as cur:
        cached = _idempotent(cur, endpoint, key, payload)
        if cached is not None:
            return cached
        # Serialize same client project even before its first INSERT.
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (payload["client_id"],))
        cur.execute("SELECT * FROM app_projects WHERE client_id=%s FOR UPDATE", (payload["client_id"],))
        existing = cur.fetchone()
        project_id = existing["id"] if existing else uuid4()
        if existing:
            cur.execute("SELECT 1 FROM app_runs WHERE project_id=%s AND state IN ('queued','rendering','needs_reconciliation') LIMIT 1", (project_id,))
            if cur.fetchone():
                raise DomainError("PROJECT_BUSY", "Dự án đang chạy; không thể cập nhật.")
        account_id = f"project:{project_id}"
        _account(cur, account_id, payload["budget_micro_usd"])
        cur.execute("SELECT * FROM app_accounts WHERE id=%s FOR UPDATE", (account_id,))
        account = cur.fetchone()
        if payload["budget_micro_usd"] < account["spent_micro"] + account["held_micro"]:
            raise DomainError("BUDGET_LOCKED", "Không thể hạ ngân sách dưới phần đã chi và đang giữ.")
        change = payload["budget_micro_usd"]-account["limit_micro"]
        if change:
            cur.execute("UPDATE app_accounts SET limit_micro=%s WHERE id=%s", (payload["budget_micro_usd"], account_id))
            cur.execute("INSERT INTO app_ledger(id,account_id,kind,spent_delta,held_delta,limit_delta,dedup_key) VALUES (%s,%s,'ADJUST_LIMIT',0,0,%s,%s)", (uuid4(),account_id,change,f"project:{key}"))
        revision = (existing["revision"]+1) if existing else 1
        cur.execute("INSERT INTO app_projects(id,client_id,title,revision,document) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(client_id) DO UPDATE SET title=excluded.title,revision=excluded.revision,document=excluded.document,updated_at=now()", (project_id,payload["client_id"],payload["title"],revision,Jsonb(payload)))
        result = {"project_id":str(project_id),"revision":revision}
        _save_response(cur,endpoint,key,result)
        return result

def create_quote(data, key):
    endpoint = "/quotes"
    with transaction() as cur:
        cached = _idempotent(cur,endpoint,key,data.model_dump())
        if cached is not None:
            return cached
        cur.execute("SELECT * FROM app_projects WHERE id=%s FOR UPDATE", (data.project_id,))
        project = cur.fetchone()
        if not project:
            raise DomainError("NOT_FOUND","Không tìm thấy dự án.",404)
        scenes = project["document"]["scenes"]
        if any(not s["approved"] for s in scenes):
            raise DomainError("STORYBOARD_NOT_APPROVED","Duyệt tất cả storyboard trước khi dự toán.",422)
        lines = []
        for s in scenes:
            selected = route(s)
            # Internal render tariff; video AI rates remain illustrative and cannot be dispatched.
            cost = settings.render_tariff if selected == "motion" else s["duration"]*(80000 if selected=="standard" else 200000)
            lines.append({"scene_id":s["client_id"],"route":selected,"base_micro_usd":cost,"ceiling_micro_usd":cost*(2 if data.retry and selected!="motion" else 1)})
        quote_id = uuid4()
        snapshot = {"document":project["document"],"lines":lines,"retry":data.retry,"pricing_version":f"pilot-render-{settings.render_tariff}","ai_pricing":"illustrative"}
        base = sum(l["base_micro_usd"] for l in lines)
        ceiling = sum(l["ceiling_micro_usd"] for l in lines)
        expires = datetime.now(timezone.utc)+timedelta(minutes=15)
        input_hash = digest(project["document"])
        cur.execute("INSERT INTO app_quotes(id,project_id,revision,input_hash,snapshot,base_micro,ceiling_micro,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",(quote_id,project["id"],project["revision"],input_hash,Jsonb(snapshot),base,ceiling,expires))
        result = {"quote_id":str(quote_id),"input_hash":input_hash,"base_micro_usd":base,"ceiling_micro_usd":ceiling,"expires_at":expires.isoformat(),"lines":lines,"dispatch_ready":all(l["route"]=="motion" for l in lines),"billing_basis":"internal render tariff, not cloud invoice"}
        _save_response(cur,endpoint,key,result)
        return result

def _workspace_account():
    now = datetime.now(timezone.utc)
    return f"workspace:{now.strftime('%Y-%m')}"

def accept_quote(quote_id, data, key):
    endpoint = f"/quotes/{quote_id}/runs"
    with transaction() as cur:
        cached = _idempotent(cur,endpoint,key,data.model_dump())
        if cached is not None:
            return cached
        # All mutations use project -> sorted accounts -> run lock order.
        cur.execute("SELECT project_id FROM app_quotes WHERE id=%s", (quote_id,))
        row = cur.fetchone()
        if not row:
            raise DomainError("NOT_FOUND","Không tìm thấy dự toán.",404)
        cur.execute("SELECT * FROM app_projects WHERE id=%s FOR UPDATE",(row["project_id"],))
        project = cur.fetchone()
        cur.execute("SELECT * FROM app_quotes WHERE id=%s",(quote_id,))
        quote = cur.fetchone()
        cur.execute("SELECT * FROM app_runs WHERE quote_id=%s",(quote_id,))
        previous = cur.fetchone()
        if previous:
            result={"run_id":str(previous["id"]),"state":previous["state"]}
            _save_response(cur,endpoint,key,result)
            return result
        if quote["expires_at"]<=datetime.now(timezone.utc):
            raise DomainError("QUOTE_EXPIRED","Dự toán đã hết hạn.")
        if quote["revision"]!=project["revision"] or quote["input_hash"]!=digest(project["document"]):
            raise DomainError("QUOTE_CHANGED","Storyboard đã thay đổi; cần dự toán mới.")
        if data.input_hash!=quote["input_hash"] or data.accepted_ceiling_micro_usd!=quote["ceiling_micro"]:
            raise DomainError("QUOTE_MISMATCH","Mức trần hoặc input hash không khớp dự toán.")
        if quote["snapshot"]["pricing_version"]!=f"pilot-render-{settings.render_tariff}":
            raise DomainError("PRICE_CHANGED","Biểu phí đã thay đổi; cần dự toán mới.")
        if any(l["route"]!="motion" for l in quote["snapshot"]["lines"]):
            raise DomainError("PROVIDER_NOT_CONFIGURED","Chưa có provider video AI. Chọn Ảnh có chuyển động để xuất video thật.",503)
        account_ids = sorted([_workspace_account(),f"project:{project['id']}"])
        for account_id in account_ids:
            _account(cur,account_id,settings.workspace_limit if account_id.startswith("workspace:") else project["document"]["budget_micro_usd"])
        cur.execute("SELECT * FROM app_accounts WHERE id=ANY(%s) ORDER BY id FOR UPDATE",(account_ids,))
        accounts = cur.fetchall()
        ceiling = quote["ceiling_micro"]
        if any(a["stop_dispatch"] or a["limit_micro"]-a["spent_micro"]-a["held_micro"]<ceiling for a in accounts):
            raise DomainError("BUDGET_EXCEEDED","Không đủ ngân sách khả dụng trên tất cả scope.")
        run_id = uuid4()
        cur.execute("INSERT INTO app_runs(id,quote_id,project_id,snapshot,state,held_micro) VALUES (%s,%s,%s,%s,'queued',%s)",(run_id,quote_id,project["id"],Jsonb(quote["snapshot"]),ceiling))
        for account_id in account_ids:
            cur.execute("UPDATE app_accounts SET held_micro=held_micro+%s WHERE id=%s",(ceiling,account_id))
            cur.execute("INSERT INTO app_run_accounts(run_id,account_id) VALUES (%s,%s)",(run_id,account_id))
            cur.execute("INSERT INTO app_ledger(id,account_id,run_id,kind,spent_delta,held_delta,dedup_key) VALUES (%s,%s,%s,'HOLD',0,%s,%s)",(uuid4(),account_id,run_id,ceiling,f"hold:{run_id}"))
        cur.execute("INSERT INTO app_outbox(id,run_id) VALUES (%s,%s)",(uuid4(),run_id))
        result={"run_id":str(run_id),"state":"queued","held_micro_usd":ceiling}
        _save_response(cur,endpoint,key,result)
        return result

def settle(run_id, actual, state, output_key=None, error_code=None):
    with transaction() as cur:
        cur.execute("SELECT project_id FROM app_runs WHERE id=%s",(run_id,))
        row=cur.fetchone()
        if not row:
            raise DomainError("NOT_FOUND","Run không tồn tại.",404)
        cur.execute("SELECT id FROM app_projects WHERE id=%s FOR UPDATE",(row["project_id"],))
        cur.execute("SELECT a.* FROM app_accounts a JOIN app_run_accounts r ON r.account_id=a.id WHERE r.run_id=%s ORDER BY a.id FOR UPDATE OF a",(run_id,))
        accounts=cur.fetchall()
        cur.execute("SELECT * FROM app_runs WHERE id=%s FOR UPDATE",(run_id,))
        run=cur.fetchone()
        if run["state"] in ("completed","failed","cancelled"):
            return False
        hold=run["held_micro"]
        if actual<0:
            raise ValueError("actual must be nonnegative")
        for a in accounts:
            cur.execute("UPDATE app_accounts SET held_micro=held_micro-%s,spent_micro=spent_micro+%s,stop_dispatch=stop_dispatch OR %s WHERE id=%s",(hold,actual,actual>hold,a["id"]))
            cur.execute("INSERT INTO app_ledger(id,account_id,run_id,kind,spent_delta,held_delta,dedup_key) VALUES (%s,%s,%s,'SETTLE',%s,%s,%s)",(uuid4(),a["id"],run_id,actual,-hold,f"settle:{run_id}"))
        cur.execute("UPDATE app_runs SET state=%s,held_micro=0,spent_micro=%s,output_key=%s,error_code=%s,lease_until=NULL WHERE id=%s",(state,actual,output_key,error_code,run_id))
        return True

def cancel(run_id):
    with transaction() as cur:
        cur.execute("UPDATE app_runs SET cancel_requested=true WHERE id=%s AND state IN ('queued','rendering') RETURNING state",(run_id,))
        row=cur.fetchone()
        if not row:
            cur.execute("SELECT state FROM app_runs WHERE id=%s",(run_id,))
            row=cur.fetchone()
            if not row:
                raise DomainError("NOT_FOUND","Run không tồn tại.",404)
        return {"run_id":str(run_id),"state":row["state"],"cancel_requested":True,"message":"Ngân sách chỉ giải phóng khi worker xác nhận đã dừng."}
