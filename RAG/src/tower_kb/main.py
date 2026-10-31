import hmac
import json
import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from tower_kb.api.schemas import Chat, Feedback, Upload
from tower_kb.bootstrap import Container
from tower_kb.config import Settings
from tower_kb.domain.entities import Actor
from tower_kb.domain.errors import DomainError
from tower_kb.domain.policy import now


def create_app(settings=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.container = Container(settings or Settings.from_env())
        yield

    app = FastAPI(title="铁塔运维知识库（本地开发版）",version="0.1.0",lifespan=lifespan)

    def container(request:Request):
        return request.app.state.container

    def actor(request:Request, c=Depends(container)):
        auth = request.headers.get("Authorization", "")
        if not hmac.compare_digest(auth,"Bearer "+c.settings.token):
            raise DomainError("unauthorized","需要有效的开发 Bearer Token",401)
        # Fixed local identity. Never trust roles/org/user supplied by the client.
        return Actor("demo-user","demo-org",("admin","engineer"),("demo-region",))

    @app.middleware("http")
    async def request_id(request,call_next):
        request.state.request_id = uuid.uuid4().hex
        # Bound requests before JSON parsing, including clients without Content-Length.
        if request.method in ("POST","PUT","PATCH"):
            body = bytearray()
            async for part in request.stream():
                body.extend(part)
                if len(body)>4_000_000:
                    return JSONResponse(status_code=413,content={"request_id":request.state.request_id,"error":{"code":"payload_too_large","message":"请求体超过 4MB","retryable":False}})
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    def envelope(request,code,message,status,retryable=False):
        return JSONResponse(status_code=status,content={"request_id":getattr(request.state,"request_id",uuid.uuid4().hex),"error":{"code":code,"message":message,"retryable":retryable}})

    @app.exception_handler(DomainError)
    async def domain_error(request,exc):
        return envelope(request,exc.code,exc.message,exc.status,exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        # Do not echo potentially sensitive document bodies or tokens.
        return envelope(request,"validation_error","请求格式或字段不合法",422)

    @app.exception_handler(HTTPException)
    async def http_error(request,exc):
        return envelope(request,"http_error",str(exc.detail),exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request,exc):
        logging.getLogger("tower_kb").error("dependency_error request_id=%s type=%s",getattr(request.state,"request_id",""),type(exc).__name__)
        return envelope(request,"dependency_error","依赖服务异常，请稍后重试",503,True)

    @app.get("/health/live")
    def live(): return {"status":"ok"}

    @app.get("/health/ready")
    def ready(c=Depends(container)):
        with c.db.connect() as db: db.execute("SELECT 1").fetchone()
        return {"status":"ready","mode":"local","generation":"extractive","worker":"run separately"}

    @app.post("/api/v1/documents",status_code=202)
    def upload(req:Upload,a=Depends(actor),c=Depends(container)):
        return c.documents.upload(req,a)

    @app.post("/api/v1/documents/{doc_id}/versions",status_code=202)
    def version(doc_id:str,req:Upload,a=Depends(actor),c=Depends(container)):
        return c.documents.upload(req,a,doc_id)

    @app.post("/api/v1/documents/{doc_id}/versions/{version}/publish")
    def publish(doc_id:str,version:int,a=Depends(actor),c=Depends(container)):
        return c.documents.publish(doc_id,version,a)

    @app.delete("/api/v1/documents/{doc_id}")
    def revoke(doc_id:str,a=Depends(actor),c=Depends(container)):
        return c.documents.revoke(doc_id,a)

    @app.get("/api/v1/jobs/{job_id}")
    def job(job_id:str,a=Depends(actor),c=Depends(container)):
        with c.db.connect() as db:
            row = db.execute("SELECT j.id,j.doc_id,j.version,j.state,j.attempts,j.error FROM jobs j JOIN documents d ON d.id=j.doc_id WHERE j.id=? AND d.org_id=?",(job_id,a.org_id)).fetchone()
            if not row: raise DomainError("not_found","任务不存在",404)
            return dict(row)

    @app.post("/api/v1/chat")
    def chat(req:Chat,a=Depends(actor),c=Depends(container)):
        return c.rag.answer(req,a)

    @app.post("/api/v1/chat/stream")
    async def stream(req:Chat,a=Depends(actor),c=Depends(container)):
        # Finish validation before opening SSE, preserving normal HTTP error semantics.
        result = await run_in_threadpool(c.rag.answer,req,a)
        async def events():
            yield 'event: stage\ndata: {"stage":"validated"}\n\n'
            yield "event: answer\ndata: "+json.dumps(result,ensure_ascii=False)+"\n\n"
        return StreamingResponse(events(),media_type="text/event-stream",headers={"Cache-Control":"no-cache"})

    @app.get("/api/v1/sessions/{session_id}")
    def session(session_id:str,a=Depends(actor),c=Depends(container)):
        with c.db.connect() as db:
            c.rag.session(db,session_id,a)
            # Never replay old evidence after a revoke/expiry/version switch.
            current = c.rag.visible(db,a)
            turns=[]
            for row in db.execute("SELECT * FROM messages WHERE session_id=? ORDER BY rowid",(session_id,)):
                response=json.loads(row["response"])
                if any((r["doc_id"],r["version"]) not in current for r in response["reference"]):
                    turns.append({"request_id":row["id"],"status":"evidence_revoked"})
                else: turns.append(response)
            return {"session_id":session_id,"messages":turns}

    @app.post("/api/v1/feedback",status_code=201)
    def feedback(req:Feedback,a=Depends(actor),c=Depends(container)):
        with c.db.connect() as db:
            row=db.execute("SELECT m.id FROM messages m JOIN sessions s ON s.id=m.session_id WHERE m.id=? AND s.user_id=? AND s.org_id=?",(req.request_id,a.user_id,a.org_id)).fetchone()
            if not row: raise DomainError("not_found","问答不存在",404)
            fid=uuid.uuid4().hex
            db.execute("INSERT INTO feedback VALUES(?,?,?,?,?)",(fid,req.request_id,a.user_id,req.comment,now()))
            return {"feedback_id":fid,"status":"pending_review"}
    return app

app = create_app()
