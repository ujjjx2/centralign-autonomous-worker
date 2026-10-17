"""Sandbox company UI + task service, served locally by one FastAPI application."""
from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Literal

from app.config import Settings
from app.db import Store
from app.agent.runner import Worker
from app.agent.gemma import GemmaClient, ModelUnavailable, InvalidModelResponse

ROOT=Path(__file__).resolve().parent
TEMPLATES=Jinja2Templates(directory=str(ROOT/"templates"))


class TaskRequest(BaseModel):
    instruction: str = Field(min_length=8,max_length=600)


class ClarifyRequest(BaseModel):
    instruction: str = Field(min_length=8,max_length=600)


class LocalPredictionRequest(BaseModel):
    task: Literal['ticket_category','ticket_priority','invoice_operation','action']
    text: str = Field(min_length=4, max_length=600)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings=settings or Settings()
    store=Store(settings.database_path)
    store._threshold=settings.approval_threshold_cents
    app=FastAPI(title="CentrAlign Autonomous Task Worker",version="6.2.0",
                description="Gemma 4 E2B via local Ollama; browser task worker with safe actions and verification")
    app.state.settings=settings
    app.state.store=store
    TEMPLATES.env.globals["ui_variant"] = os.getenv("UI_VARIANT", "normal") == "shifted"
    app.mount("/static",StaticFiles(directory=str(ROOT/"static")),name="static")

    def public_task(task_id: str):
        record=store.task(task_id)
        if not record:
            raise HTTPException(404,"Task not found")
        return record

    def worker(task_id: str,base_url: str):
        Worker(store,settings,base_url).run(task_id)

    @app.get("/",response_class=HTMLResponse)
    def dashboard(request: Request):
        return TEMPLATES.TemplateResponse(request,"index.html",{
            "vendors":store.vendors(),"tasks":store.recent_tasks(),"ledger":store.ledger(),"cases":store.cases(),
            "threshold":settings.approval_threshold_cents/100,
            "model_info":GemmaClient(settings.ollama_url).available() if settings.model_backend=='gemma' else {'available':False,'backend':'rules','reason':'Rules-only test mode'},
        })

    @app.get("/health")
    def health():
        return {"ok":True,"mode":settings.execution_mode,"sandbox":True}

    @app.get("/api/model")
    def model_info():
        """Local Ollama availability and Gemma E2B model status."""
        return GemmaClient(settings.ollama_url).available() if settings.model_backend=='gemma' else {"available":False,"backend":"rules","reason":"Rules-only mode"}

    @app.post('/api/model/predict')
    def predict_model(body: LocalPredictionRequest):
        """Test local Gemma's restricted JSON classification; never executes a tool."""
        if settings.model_backend!='gemma':
            raise HTTPException(503,'Gemma is disabled')
        try:
            gateway=GemmaClient(settings.ollama_url,settings.ollama_timeout)
            if body.task=='action':
                return gateway.decide('action', {'text':body.text}, ['ask_human','create_ledger_entry'])
            if body.task=='ticket_category' or body.task=='ticket_priority':
                classification=gateway.decide('ticket_classification',{'text':body.text})
                return {'label':classification['category' if body.task=='ticket_category' else 'priority'],
                        'reason':classification['reason'],'model':'gemma4:e2b'}
            operation=gateway.decide('invoice_operation',{'text':body.text})
            return {'label':operation['operation'],'reason':operation['reason'],'model':'gemma4:e2b'}
        except ModelUnavailable as exc:
            raise HTTPException(503,str(exc)) from exc
        except InvalidModelResponse as exc:
            raise HTTPException(502,str(exc)) from exc

    @app.post("/api/tasks",status_code=202)
    def create_task(body: TaskRequest,request: Request, background_tasks: BackgroundTasks):
        task_id=store.create_task(body.instruction.strip())
        background_tasks.add_task(worker,task_id,str(request.base_url).rstrip("/"))
        return {"task_id":task_id,"status":"queued"}

    @app.get("/api/tasks")
    def get_tasks():
        return store.recent_tasks()

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str):
        return public_task(task_id)

    @app.post("/api/tasks/{task_id}/approve",status_code=202)
    def approve(task_id: str,request: Request,background_tasks: BackgroundTasks):
        record=public_task(task_id)
        if record["status"]!="awaiting_approval" or not store.decide_approval(task_id,"approved"):
            raise HTTPException(409,"Task is not awaiting approval")
        store.add_event(task_id,"human","approval_decision",{"decision":"approved"})
        background_tasks.add_task(worker,task_id,str(request.base_url).rstrip("/"))
        return {"task_id":task_id,"status":"resuming"}

    @app.post("/api/tasks/{task_id}/reject")
    def reject(task_id: str):
        record=public_task(task_id)
        if record["status"]!="awaiting_approval" or not store.decide_approval(task_id,"rejected"):
            raise HTTPException(409,"Task is not awaiting approval")
        store.update_task(task_id,status="rejected",report={"outcome":"not_recorded","reason":"Human rejected the write"})
        store.add_event(task_id,"human","approval_decision",{"decision":"rejected"})
        return {"task_id":task_id,"status":"rejected"}

    @app.post("/api/tasks/{task_id}/clarify",status_code=202)
    def clarify(task_id: str,body: ClarifyRequest,request: Request,background_tasks: BackgroundTasks):
        record=public_task(task_id)
        if record["status"]!="needs_input":
            raise HTTPException(409,"Task has no open clarification request")
        with store.connection() as db:
            db.execute("UPDATE tasks SET instruction=?,status='queued',error=NULL WHERE id=?",
                       (body.instruction.strip(),task_id))
        store.add_event(task_id,"human","clarification",{"instruction":body.instruction})
        background_tasks.add_task(worker,task_id,str(request.base_url).rstrip("/"))
        return {"task_id":task_id,"status":"queued"}

    @app.get("/api/tasks/{task_id}/evidence")
    def evidence(task_id: str):
        public_task(task_id)
        screenshot=settings.artifacts_dir/task_id/"verification.png"
        readback=settings.artifacts_dir/task_id/"verification.json"
        if screenshot.is_file():
            return FileResponse(screenshot,media_type="image/png",filename=f"verification-{task_id[:8]}.png")
        if readback.is_file():
            return FileResponse(readback,media_type="application/json",filename=f"verification-{task_id[:8]}.json")
        raise HTTPException(404,"Verification evidence not available")

    @app.get("/api/tasks/{task_id}/browser-video")
    def task_video(task_id: str):
        public_task(task_id)
        video=settings.artifacts_dir/task_id/"browser-recording.webm"
        if not video.is_file():
            raise HTTPException(404,"No recorded Chromium session for this task")
        return FileResponse(video,media_type="video/webm",filename=f"browser-{task_id[:8]}.webm")

    @app.get("/api/tasks/{task_id}/browser-trace")
    def task_browser_trace(task_id: str):
        public_task(task_id)
        trace=settings.artifacts_dir/task_id/"playwright-trace.zip"
        if not trace.is_file():
            raise HTTPException(404,"No Playwright trace for this task")
        return FileResponse(trace,media_type="application/zip",filename=f"trace-{task_id[:8]}.zip")

    @app.get("/api/invoices")
    def invoices():
        return store.invoices()

    @app.get('/api/tickets')
    def source_tickets():
        return store.tickets()

    @app.get('/api/cases')
    def support_cases():
        return store.cases()

    @app.get('/workspace/tickets',response_class=HTMLResponse)
    def ticket_inbox(request: Request,search: str=''):
        return TEMPLATES.TemplateResponse(request,'tickets.html',{'tickets':store.tickets(search),'search':search})

    @app.get('/workspace/tickets/{ticket_id}',response_class=HTMLResponse)
    def ticket_detail(request: Request,ticket_id: int):
        ticket=store.ticket(ticket_id)
        if not ticket:
            raise HTTPException(404,'Ticket not found')
        return TEMPLATES.TemplateResponse(request,'ticket.html',{'ticket':ticket})

    @app.get('/workspace/cases',response_class=HTMLResponse)
    def cases(request: Request,search: str=''):
        return TEMPLATES.TemplateResponse(request,'cases.html',{'cases':store.cases(search),'search':search})

    @app.get('/workspace/cases/new',response_class=HTMLResponse)
    def new_case(request: Request):
        return TEMPLATES.TemplateResponse(request,'case_form.html',{'error':None,'values':{}})

    @app.post('/workspace/cases/new',response_class=HTMLResponse)
    def submit_case(request: Request,source_ticket_id: int=Form(...),number: str=Form(...),
                    requester: str=Form(...),subject: str=Form(...),category: str=Form(...),
                    priority: str=Form(...),assigned_team: str=Form(...),task_id: str=Form('')):
        fields={'source_ticket_id':source_ticket_id,'number':number,'requester':requester,
                'subject':subject,'category':category,'priority':priority,
                'assigned_team':assigned_team,'task_id':task_id}
        case_id,error=store.add_case(ticket_id=source_ticket_id,number=number,requester=requester,subject=subject,category=category,priority=priority,assigned_team=assigned_team,task_id=task_id)
        if error and error!='already_exists':
            return TEMPLATES.TemplateResponse(request,'case_form.html',
                {'error':error,'values':fields},status_code=503 if 'Temporary' in error else 422)
        return RedirectResponse(f'/workspace/cases/{case_id}',status_code=303)

    @app.get('/workspace/cases/{case_id}',response_class=HTMLResponse)
    def case_detail(request: Request,case_id: int):
        record=store.case(case_id)
        if not record:
            raise HTTPException(404,'Case not found')
        return TEMPLATES.TemplateResponse(request,'case_detail.html',{'case':record})

    @app.post('/api/demo/fail-next-case-write')
    def inject_case_failure():
        """Inject a one-shot transient failure into the local support application."""
        store.fail_next_case_write()
        return {'message':'Next support form submission will fail once'}

    @app.get("/api/ledger")
    def ledger():
        return store.ledger()

    @app.post("/api/demo/fail-next-write")
    def inject_failure():
        """Educational test fixture exposed only in the local sandbox UI."""
        store.fail_next_write()
        return {"message":"Next ledger write will fail once (agent will retry)"}

    @app.get("/workspace/invoices",response_class=HTMLResponse)
    def invoice_inbox(request: Request,vendor: str=""):
        return TEMPLATES.TemplateResponse(request,"inbox.html",{
            "invoices":store.invoices(vendor),"vendor_filter":vendor})

    @app.get("/workspace/invoices/{invoice_id}",response_class=HTMLResponse)
    def invoice_detail(request: Request,invoice_id: int):
        inv=store.invoice(invoice_id)
        if not inv:
            raise HTTPException(404,"Invoice not found")
        return TEMPLATES.TemplateResponse(request,"invoice.html",{"invoice":inv,
            "amount":f'{inv["amount_cents"]/100:,.2f}'})

    @app.get("/workspace/ledger",response_class=HTMLResponse)
    def ledger_page(request: Request,search: str=""):
        return TEMPLATES.TemplateResponse(request,"ledger.html",{
            "entries":store.ledger(search),"search":search})

    @app.get("/workspace/ledger/new",response_class=HTMLResponse)
    def ledger_new(request: Request):
        return TEMPLATES.TemplateResponse(request,"ledger_form.html",{
            "vendors":store.vendors(),"error":None,"values":{}})

    @app.post("/workspace/ledger/new",response_class=HTMLResponse)
    def ledger_submit(request: Request,
                      vendor_id: int=Form(...),invoice_number: str=Form(...),
                      amount: str=Form(...),due_date: str=Form(...),
                      source_invoice_id: int=Form(...),task_id: str=Form("")):
        values={"vendor_id":vendor_id,"invoice_number":invoice_number,"amount":amount,
                "due_date":due_date,"source_invoice_id":source_invoice_id,"task_id":task_id}
        try:
            cents=int(Decimal(amount)*100)
            if Decimal(amount)*100 != cents or cents<=0:
                raise ValueError("Invalid amount")
        except (InvalidOperation,ValueError):
            cents=-1
        if cents<=0 or not re.fullmatch(r"\d{4}-\d\d-\d\d",due_date):
            entry_id,error=None,"Invalid amount or date"
        else:
            entry_id,error=store.add_entry(source_invoice_id,vendor_id,invoice_number,cents,due_date,"USD",task_id)
        if error and error!="already_exists":
            return TEMPLATES.TemplateResponse(request,"ledger_form.html",{
                "vendors":store.vendors(),"error":error,"values":values},status_code=503 if "Temporary" in error else 422)
        return RedirectResponse(f"/workspace/ledger/{entry_id}",status_code=303)

    @app.get("/workspace/ledger/{entry_id}",response_class=HTMLResponse)
    def ledger_detail(request: Request,entry_id: int):
        entry=store.entry(entry_id)
        if not entry:
            raise HTTPException(404,"Ledger entry not found")
        return TEMPLATES.TemplateResponse(request,"ledger_detail.html",{"entry":entry})

    return app


app=create_app()


def run_server():
    import uvicorn
    settings=Settings()
    uvicorn.run("app.main:app",host=settings.host,port=settings.port,reload=False)


if __name__=="__main__":
    run_server()
