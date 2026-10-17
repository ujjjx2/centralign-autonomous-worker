"""Browser/HTML transport for two approved local company workflows.

EXECUTION_MODE=browser uses the v4 adaptive visual Chromium implementation.
EXECUTION_MODE=http is an explicit non-browser HTML fallback for tests.
"""
from __future__ import annotations
import re
from pathlib import Path
from urllib.parse import quote
from app.config import Settings


class ToolError(RuntimeError):
    pass


class RetryableToolError(ToolError):
    pass


class HttpTools:
    """HTML-over-HTTP fallback for environments where Chromium cannot start.

    It still reads rendered server HTML, submits the same company form, and
    verifies against a fresh response; it never directly accesses Store.
    """
    def __init__(self,base_url: str,settings: Settings):
        import httpx
        self.http=httpx.Client(base_url=base_url,follow_redirects=True,timeout=10)
        self.url=base_url.rstrip("/")
        self.settings=settings

    def __enter__(self):
        self.http.get("/health").raise_for_status()
        return self

    def __exit__(self,*args):
        self.http.close()

    @staticmethod
    def soup(response):
        from bs4 import BeautifulSoup
        if response.status_code>=400:
            raise ToolError(f"Company page returned HTTP {response.status_code}")
        return BeautifulSoup(response.text,"html.parser")

    def search_tickets(self, number: str=''):
        page=self.soup(self.http.get('/workspace/tickets',params={'search':number}))
        return [{'id':int(r['data-ticket-id']),
                 'number':r.select_one('.number').get_text(strip=True),
                 'subject':r.select_one('.subject').get_text(strip=True),
                 'arrived_at':r.select_one('.arrived').get_text(strip=True)}
                for r in page.select('tr[data-ticket-id]')]

    def read_ticket(self,ticket_id: int):
        response=self.http.get(f'/workspace/tickets/{ticket_id}')
        page=self.soup(response)
        elem=page.select_one('#ticket-document')
        if not elem:
            raise ToolError('Ticket document not available')
        return {'number':elem['data-number'],'requester':elem['data-requester'],
                'subject':elem['data-subject'],
                'description':elem.select_one('#ticket-description').get_text(strip=True),
                'url':str(response.url)}

    def find_case(self,number: str):
        page=self.soup(self.http.get('/workspace/cases',params={'search':number}))
        for row in page.select('tr[data-case-id]'):
            if row['data-number']==number:
                return int(row['data-case-id'])
        return None

    def refresh_form(self, kind: str):
        if kind not in {'invoice','ticket'}:raise ToolError('Unknown form type')
        route='/workspace/ledger/new' if kind=='invoice' else '/workspace/cases/new'
        self.soup(self.http.get(route))
        return {'action':'refresh_form','page':self.url+route}

    def write_case(self,ticket_id: int,facts: dict,task_id: str):
        self.soup(self.http.get('/workspace/cases/new'))
        response=self.http.post('/workspace/cases/new',data={
            'source_ticket_id':ticket_id,'task_id':task_id,
            **{k:facts[k] for k in ('number','requester','subject','category','priority','assigned_team')}})
        match=re.search(r'/workspace/cases/(\d+)$',str(response.url))
        if response.status_code==200 and match:
            return int(match.group(1))
        from bs4 import BeautifulSoup
        page=BeautifulSoup(response.text,'html.parser')
        alert=page.select_one('.form-error')
        message=alert.get_text(strip=True) if alert else 'Helpdesk form submission failed'
        if response.status_code>=500 or 'Temporary' in message or 'unavailable' in message:
            raise RetryableToolError(message)
        raise ToolError(message)

    def verify_case(self,case_id: int,expected: dict,evidence_path=None):
        import json
        response=self.http.get(f'/workspace/cases/{case_id}')
        page=self.soup(response)
        node=page.select_one('#verified-support-case')
        if not node:
            raise ToolError('Missing persisted support case details')
        observed={key:node['data-'+key.replace('_','-')]
                  for key in ('number','requester','subject','category','priority','assigned_team')}
        matched=all(observed[k]==expected[k] for k in observed)
        if evidence_path:
            evidence_path=evidence_path.with_name('verification.json')
            evidence_path.parent.mkdir(parents=True,exist_ok=True)
            evidence_path.write_text(json.dumps({'source':'fresh HTML readback','page':str(response.url),
                'expected':expected,'observed':observed,'matched':matched},indent=2))
        return {'matched':matched,'observed':observed,'case_id':case_id,'page':str(response.url),
                'evidence_type':'html_readback_json'}

    def search_invoices(self,vendor):
        page=self.soup(self.http.get("/workspace/invoices",params={"vendor":vendor}))
        result=[]
        for tr in page.select("tr[data-invoice-id]"):
            result.append({"id":int(tr["data-invoice-id"]),
                           "vendor":tr.select_one(".vendor").get_text(strip=True),
                           "number":tr.select_one(".number").get_text(strip=True),
                           "arrived_at":tr.select_one(".arrived").get_text(strip=True)})
        return result

    def read_invoice(self,invoice_id):
        response=self.http.get(f"/workspace/invoices/{invoice_id}")
        page=self.soup(response)
        doc=page.select_one(".invoice-document")
        if not doc:
            raise ToolError("No invoice document on source page")
        return {"text":doc.get_text("\n",strip=True),"url":str(response.url)}

    def find_ledger_entry(self,number,vendor):
        page=self.soup(self.http.get("/workspace/ledger",params={"search":number}))
        for row in page.select("tr[data-entry-id]"):
            if row.get("data-number")==number and row.get("data-vendor")==vendor:
                return int(row["data-entry-id"])
        return None

    def write_ledger_entry(self,invoice_id,invoice,task_id):
        vendor_page=self.soup(self.http.get("/workspace/ledger/new"))
        vendor_id=None
        for option in vendor_page.select("#vendor-id option"):
            if option.get_text(strip=True)==invoice["vendor"]:
                vendor_id=option.get("value")
        if not vendor_id:
            raise ToolError("Cannot select vendor in company form")
        response=self.http.post("/workspace/ledger/new",data={
            "vendor_id":vendor_id,"invoice_number":invoice["number"],
            "amount":f'{invoice["amount_cents"]/100:.2f}',
            "due_date":invoice["due_date"],"source_invoice_id":invoice_id,"task_id":task_id})
        match=re.search(r"/workspace/ledger/(\d+)$",str(response.url))
        if response.status_code==200 and match:
            return int(match.group(1))
        from bs4 import BeautifulSoup
        page=BeautifulSoup(response.text,"html.parser")
        alert=page.select_one(".form-error")
        msg=alert.get_text(strip=True) if alert else f"Write failed with HTTP {response.status_code}"
        if response.status_code>=500 or "Temporary" in msg:
            raise RetryableToolError(msg)
        raise ToolError(msg)

    def verify_entry(self,entry_id,expected,evidence_path=None):
        import json
        response=self.http.get(f"/workspace/ledger/{entry_id}")
        page=self.soup(response)
        node=page.select_one("#verified-ledger-entry")
        if not node:
            raise ToolError("Ledger detail page does not contain read-back facts")
        observed={"vendor":node["data-vendor"],"number":node["data-number"],
                  "amount_cents":int(node["data-amount-cents"]),
                  "due_date":node["data-due-date"],"currency":node["data-currency"]}
        matched=all(observed[k]==expected[k] for k in observed)
        if evidence_path:
            evidence_path=evidence_path.with_name("verification.json")
            evidence_path.parent.mkdir(parents=True,exist_ok=True)
            evidence_path.write_text(json.dumps({"source":"fresh HTML readback","page":str(response.url),
                                                "expected":expected,"observed":observed,"matched":matched},indent=2))
        return {"matched":matched,"observed":observed,"entry_id":entry_id,"page":str(response.url),
                "evidence_type":"html_readback_json"}


class BrowserTools:
    """Auto-select real browser; fall back to HTML transport in locked-down CI.

    EXECUTION_MODE=browser refuses fallback, ensuring a strict browser-only demo.
    """
    def __init__(self,base_url: str,settings: Settings, task_id=None, on_step=None):
        self.url=base_url
        self.settings=settings
        self.task_id=task_id
        self.on_step=on_step
        self.backend=None
        self.backend_name=None
        self.fallback_reason=None

    def __enter__(self):
        mode=self.settings.execution_mode
        if mode not in {"auto","browser","http"}:
            raise ToolError("EXECUTION_MODE must be auto, browser or http")
        if mode!="http":
            from app.agent.browser_v4 import VisualBrowserTools
            candidate=VisualBrowserTools(self.url,self.settings,self.task_id,self.on_step)
            try:
                candidate.__enter__()
                # Visual adapter already navigated to the dashboard and verified the page.
                self.backend=candidate
                self.backend_name="playwright_chromium"
                return self
            except Exception as exc:
                self.fallback_reason=f"{type(exc).__name__}: {exc}"[:200]
                try:
                    if hasattr(candidate,"browser"):
                        candidate.__exit__(None,None,None)
                except Exception:
                    pass
                if mode=="browser":
                    raise ToolError("Real browser unavailable: "+self.fallback_reason)
        self.backend=HttpTools(self.url,self.settings)
        self.backend.__enter__()
        self.backend_name="http_html_automation"
        return self

    def __exit__(self,*args):
        return self.backend.__exit__(*args)

    def __getattr__(self,name):
        allowed={"search_invoices","read_invoice","find_ledger_entry","write_ledger_entry","verify_entry",
                 "search_tickets","read_ticket","find_case","write_case","verify_case","refresh_form"}
        if name not in allowed:
            raise AttributeError(name)
        if self.backend_name!='playwright_chromium':
            return getattr(self.backend,name)

        def observed_call(*args,**kwargs):
            from playwright.sync_api import Error as PlaywrightError
            try:
                return getattr(self.backend,name)(*args,**kwargs)
            except PlaywrightError as exc:
                # Recover ONLY when the browser/page disappeared. Ordinary
                # locator/timeouts should remain errors, not trigger a restart.
                message=str(exc).lower()
                disconnected=(('closed' in message or 'disconnected' in message or
                               'crashed' in message or 'targetclosederror' in message)
                              and ('page' in message or 'browser' in message or
                                   'context' in message or 'target' in message))
                if not disconnected:
                    raise
                self.backend._log('browser_session_lost',method=name,error=str(exc)[:350])
                self.backend.restart_session()
                # A crashed browser may have submitted a form before dying.
                # NEVER blindly repeat a write. Read the target first.
                if name=='write_ledger_entry':
                    invoice=args[1] if len(args)>1 else kwargs['invoice']
                    existing=self.backend.find_ledger_entry(invoice['number'],invoice['vendor'])
                    if existing is not None:
                        self.backend._log('write_recovered_from_readback',method=name,entry_id=existing)
                        return existing
                elif name=='write_case':
                    facts=args[1] if len(args)>1 else kwargs['facts']
                    existing=self.backend.find_case(facts['number'])
                    if existing is not None:
                        self.backend._log('write_recovered_from_readback',method=name,entry_id=existing)
                        return existing
                self.backend._log('retry_after_browser_restart',method=name)
                return getattr(self.backend,name)(*args,**kwargs)
        return observed_call
