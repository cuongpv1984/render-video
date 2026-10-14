import hmac
from uuid import UUID, uuid4
from fastapi import FastAPI, Depends, Header, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .db import transaction
from .domain import DomainError,save_project,create_quote,accept_quote,cancel
from .models import ProjectInput,QuoteInput,RunInput
from .storage import local_path, signed_download

app=FastAPI(title="Frame Studio API",version="1.1.0",docs_url="/docs")
app.add_middleware(CORSMiddleware,allow_origins=[settings.cors_origin],allow_methods=["GET","POST"],allow_headers=["Authorization","Content-Type","Idempotency-Key"])

def owner(authorization: str = Header(default="")):
    if len(settings.owner_token)<32:
        raise DomainError("AUTH_NOT_CONFIGURED","Backend chưa cấu hình token chủ workspace.",503)
    if not hmac.compare_digest(authorization,f"Bearer {settings.owner_token}"):
        raise DomainError("UNAUTHORIZED","Thông tin xác thực không hợp lệ.",401)

def key(idempotency_key: str=Header(alias="Idempotency-Key")):
    if not 1<=len(idempotency_key)<=128:
        raise DomainError("INVALID_KEY","Idempotency key phải từ 1 đến 128 ký tự.",422)
    return idempotency_key

@app.exception_handler(DomainError)
async def domain_error(request:Request,exc:DomainError):
    return JSONResponse(status_code=exc.status,content={"code":exc.code,"message":exc.message,"request_id":str(uuid4())})

@app.get("/health")
def health():
    return {"status":"ok","mode":"owner-pilot","paid_ai_enabled":False}

@app.get("/ready",dependencies=[Depends(owner)])
def ready():
    with transaction() as cur:cur.execute("SELECT 1 FROM app_accounts LIMIT 1")
    return {"status":"ready"}

@app.post("/api/v1/projects",dependencies=[Depends(owner)])
def projects_create(data:ProjectInput,idempotency: str=Depends(key)):
    return save_project(data,idempotency)

@app.get("/api/v1/projects",dependencies=[Depends(owner)])
def projects_list():
    with transaction() as cur:
        cur.execute("SELECT id,title,revision,document,updated_at FROM app_projects ORDER BY updated_at DESC LIMIT 100")
        return cur.fetchall()

@app.post("/api/v1/quotes",dependencies=[Depends(owner)])
def quotes_create(data:QuoteInput,idempotency: str=Depends(key)):
    try:UUID(data.project_id)
    except ValueError:raise DomainError("INVALID_ID","Project ID không hợp lệ.",422)
    return create_quote(data,idempotency)

@app.post("/api/v1/quotes/{quote_id}/runs",status_code=202,dependencies=[Depends(owner)])
def runs_create(quote_id:UUID,data:RunInput,idempotency: str=Depends(key)):
    return accept_quote(str(quote_id),data,idempotency)

@app.get("/api/v1/runs",dependencies=[Depends(owner)])
def runs_list():
    with transaction() as cur:
        cur.execute("SELECT id,project_id,state,held_micro,spent_micro,error_code,created_at FROM app_runs ORDER BY created_at DESC LIMIT 50")
        return cur.fetchall()

@app.get("/api/v1/runs/{run_id}",dependencies=[Depends(owner)])
def runs_get(run_id:UUID):
    with transaction() as cur:
        cur.execute("SELECT id,project_id,state,held_micro,spent_micro,cancel_requested,output_key,error_code,created_at FROM app_runs WHERE id=%s",(run_id,))
        row=cur.fetchone()
        if not row:raise DomainError("NOT_FOUND","Run không tồn tại.",404)
        return row

@app.post("/api/v1/runs/{run_id}/cancel",dependencies=[Depends(owner)])
def runs_cancel(run_id:UUID):return cancel(str(run_id))

@app.get("/api/v1/runs/{run_id}/download",dependencies=[Depends(owner)])
def runs_download(run_id:UUID):
    with transaction() as cur:
        cur.execute("SELECT output_key,state FROM app_runs WHERE id=%s",(run_id,))
        row=cur.fetchone()
    if not row or row["state"]!="completed" or not row["output_key"]:
        raise DomainError("NOT_READY","Video chưa sẵn sàng.",404)
    if settings.s3_bucket:return {"url":signed_download(row["output_key"]),"expires_in":300}
    return FileResponse(local_path(row["output_key"]),media_type="video/mp4",filename=f"frame-{run_id}.mp4")

@app.get("/api/v1/budget",dependencies=[Depends(owner)])
def budgets_get():
    with transaction() as cur:
        cur.execute("SELECT *, limit_micro-spent_micro-held_micro AS available_micro FROM app_accounts ORDER BY id LIMIT 200")
        accounts=cur.fetchall()
        cur.execute("SELECT * FROM app_ledger ORDER BY created_at DESC LIMIT 100")
        return {"accounts":accounts,"ledger":cur.fetchall()}
