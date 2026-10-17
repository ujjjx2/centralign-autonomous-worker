"""Actual Chromium computer-use adapter with semantic UI planning and evidence.

Every navigation/form action uses Playwright's browser, not a database shortcut.
A locally hosted sandbox is the only allowed origin. The recording is captured
by Chromium itself and stored under the task's evidence directory.
"""
from __future__ import annotations
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse, urljoin
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from app.agent.browser import ToolError, RetryableToolError
from app.agent.ui_planner import find_live_locator, page_affordances


CURSOR_SCRIPT=r'''(() => {
 if(window.__centralignCursor) return;
 const make=()=>{
  if(document.getElementById('centralign-pointer')) return;
  const cursor=document.createElement('div');cursor.id='centralign-pointer';
  cursor.style.cssText='position:fixed;width:24px;height:24px;border:3px solid #00d4ff;border-radius:50%;background:#02b7e440;box-shadow:0 0 0 5px #005eff44,0 0 14px #00ddff;pointer-events:none;z-index:2147483647;left:30px;top:90px;transition:transform .1s ease';
  const text=document.createElement('div');text.id='centralign-cursor-label';text.innerText='AI CURSOR';
  text.style.cssText='position:fixed;left:58px;top:102px;padding:3px 7px;border-radius:6px;background:#04223c;color:#a8ffff;font:700 12px system-ui;pointer-events:none;z-index:2147483647';
  document.documentElement.append(cursor,text);
  document.addEventListener('mousemove',e=>{cursor.style.left=(e.clientX-12)+'px';cursor.style.top=(e.clientY-12)+'px';text.style.left=(e.clientX+15)+'px';text.style.top=(e.clientY+13)+'px';},true);
  document.addEventListener('click',e=>{cursor.style.background='#ffbf0066';setTimeout(()=>cursor.style.background='#02b7e440',220);},true);
 };
 document.addEventListener('DOMContentLoaded',make,{once:true});
 if(document.readyState!='loading')make();
 window.__centralignCursor=true;
})()'''


class VisualBrowserTools:
    def __init__(self, base_url: str, settings, task_id: str|None=None, on_step=None):
        self.url=base_url.rstrip('/')
        self.settings=settings
        self.task_id=task_id
        self.on_step=on_step
        self.step_counter=0
        self.artifacts=(settings.artifacts_dir/task_id if task_id else settings.artifacts_dir/'browser_smoke')
        self.slow=float(os.getenv('BROWSER_ACTION_DELAY','0.14'))
        self.restarts=0
        self.page=None
        self.ctx=None
        self.browser=None
        self.pw=None

    def __enter__(self):
        self.artifacts.mkdir(parents=True,exist_ok=True)
        self.pw=sync_playwright().start()
        kwargs={'headless':self.settings.headless,'args':['--no-sandbox','--disable-dev-shm-usage']}
        if self.settings.browser_executable:kwargs['executable_path']=self.settings.browser_executable
        try:
            self.browser=self.pw.chromium.launch(**kwargs)
            self.ctx=self.browser.new_context(viewport={'width':1280,'height':810},
                record_video_dir=str(self.artifacts/'recordings'),record_video_size={'width':1280,'height':810})
            self.ctx.add_init_script(CURSOR_SCRIPT)
            self.ctx.tracing.start(screenshots=True,snapshots=True,sources=False)
            self.page=self.ctx.new_page()
            self.page.set_default_timeout(7000)
            self._goto(self.url+'/')
            return self
        except Exception:
            # Clean up resources even if launching/navigation failed halfway.
            self._shutdown()
            raise

    def _shutdown(self):
        # Cleanup is best effort. Never hide the error that originally stopped
        # the task (notably TargetClosedError during unexpected browser exit).
        page=self.page
        ctx=self.ctx
        browser=self.browser
        pw=self.pw
        self.page=self.ctx=self.browser=self.pw=None
        if page is not None:
            try:
                if not page.is_closed():
                    self._snapshot('end',page=page,require_alive=False)
            except Exception:
                pass
        if ctx is not None:
            try:ctx.tracing.stop(path=str(self.artifacts/f'playwright-trace-{self.restarts}.zip'))
            except Exception:pass
            video=page.video if page is not None else None
            try:ctx.close()
            except Exception:pass
            if video is not None:
                try:
                    import shutil
                    video_path=video.path()
                    shutil.copy2(video_path,self.artifacts/f'browser-recording-{self.restarts}.webm')
                    if self.restarts==0:
                        shutil.copy2(video_path,self.artifacts/'browser-recording.webm')
                except Exception:pass
        if browser is not None:
            try:browser.close()
            except Exception:pass
        if pw is not None:
            try:pw.stop()
            except Exception:pass

    def __exit__(self, exc_type, exc_value, traceback):
        self._shutdown()
        # Preserve the original exception from the browser action.
        return False

    def restart_session(self):
        """One bounded, observable browser restart for a disconnected session."""
        if self.restarts>=1:
            raise ToolError('Chromium disconnected again after the single recovery attempt. '
                            'Check macOS memory pressure and Ollama GPU/RAM usage.')
        self._shutdown()
        self.restarts+=1
        self._log('browser_restart',reason='Previous Chromium page/context disconnected')
        return self.__enter__()

    def _log(self,action,**detail):
        try:url=self.page.url if self.page is not None else self.url
        except Exception:url=self.url
        payload={'action':action,'url':url,'step':self.step_counter,**detail}
        if self.on_step:
            try:self.on_step(payload)
            except Exception:pass

    def _snapshot(self,label,page=None,require_alive=True):
        page=page or self.page
        self.step_counter+=1
        if page is None or page.is_closed():
            self._log('browser_disconnected',label=label,reason='page already closed')
            if require_alive:
                raise PlaywrightError('Target page, context or browser has been closed while observing '+label)
            return
        if self.step_counter<=120:
            path=self.artifacts/f'{self.step_counter:03d}-{re.sub("[^a-z0-9-]","-",label.lower())[:35]}.png'
            try:page.screenshot(path=str(path),animations='disabled',timeout=5000)
            except PlaywrightError as exc:
                self._log('screenshot_unavailable',label=label,error=str(exc)[:250])
        try:
            self._log('observe',label=label,title=page.title(),
                      heading=page.locator('h1').first.inner_text() if page.locator('h1').count() else '',
                      visible_controls=len(page_affordances(page)))
        except PlaywrightError as exc:
            self._log('browser_disconnected',label=label,error=str(exc)[:250])
            if require_alive:raise

    def _guard(self,url):
        requested=urlparse(url); trusted=urlparse(self.url)
        if requested.scheme!=trusted.scheme or requested.netloc!=trusted.netloc:
            raise ToolError('Navigation outside approved sandbox origin forbidden')

    def _goto(self,url):
        self._guard(url)
        response=self.page.goto(url,wait_until='domcontentloaded')
        if not response or response.status>=400:
            raise ToolError(f'Browser navigation failed: {url} ({response.status if response else "none"})')
        self._snapshot('navigation')

    def _find(self,role,terms):
        try:
            node,meta=find_live_locator(self.page,role,terms)
            self._log('plan_action',role=role,target=terms,**meta)
            return node
        except LookupError as exc:
            self._log('replan',reason=str(exc)[:360])
            raise ToolError(f'No safe UI action available for {role}:{terms}') from exc

    def _point(self,element):
        element.scroll_into_view_if_needed()
        box=element.bounding_box()
        if not box:raise ToolError('UI element disappeared before action')
        x,y=box['x']+box['width']/2,box['y']+box['height']/2
        self.page.mouse.move(x,y,steps=9)
        time.sleep(self.slow)

    def _click(self,role,terms):
        target=self._find(role,terms)
        if role=='link':
            href=target.get_attribute('href') or ''
            self._guard(urljoin(self.page.url,href))
        self._point(target)
        target.click()
        self.page.wait_for_load_state('domcontentloaded')
        time.sleep(self.slow)
        self._snapshot('click-'+terms[0])

    def _fill(self,terms,value):
        target=self._find('input',terms)
        self._point(target)
        target.fill(str(value))
        time.sleep(self.slow)
        self._snapshot('fill-'+terms[0])

    def _select(self,terms,value):
        target=self._find('select',terms)
        self._point(target)
        target.select_option(label=value)
        time.sleep(self.slow)
        self._snapshot('select-'+terms[0])

    def _section(self,section):
        # Navigates from the currently observed page by reading the live nav.
        self._goto(self.url+'/') if self.page.url=='about:blank' else None
        self._click('link',[section])

    def search_invoices(self,vendor):
        self._section('Invoice inbox')
        self._fill(['Filter by vendor','vendor'],vendor)
        self._click('button',['Find invoices'])
        return [{'id':int(r.get_attribute('data-invoice-id')),
                 'vendor':r.locator('.vendor').inner_text().strip(),
                 'number':r.locator('.number').inner_text().strip(),
                 'arrived_at':r.locator('.arrived').inner_text().strip()}
                for r in self.page.locator('tr[data-invoice-id]').all()]

    def read_invoice(self,invoice_id):
        # Prefer the document hyperlink discovered in the actual search result.
        # Reaching the document by visible click makes the control path auditable.
        row=self.page.locator(f'tr[data-invoice-id="{int(invoice_id)}"]')
        if row.count() and row.locator('a').count():
            link=row.locator('a').first
            self._guard(urljoin(self.page.url,link.get_attribute('href') or ''))
            self._point(link)
            link.click()
            self.page.wait_for_load_state('domcontentloaded')
            self._snapshot('open-invoice-document')
        else:
            self._goto(self.url+f'/workspace/invoices/{invoice_id}')
        return {'text':self.page.locator('.invoice-document').inner_text(),'url':self.page.url}

    def find_ledger_entry(self,number,vendor):
        self._section('Accounts payable')
        self._fill(['Search vendor or invoice number','search'],number)
        self._click('button',['Search ledger'])
        for r in self.page.locator('tr[data-entry-id]').all():
            if r.get_attribute('data-number')==number and r.get_attribute('data-vendor')==vendor:
                return int(r.get_attribute('data-entry-id'))
        return None

    def refresh_form(self,kind):
        if kind not in {'invoice','ticket'}:raise ToolError('Unknown form type')
        self._section('Accounts payable' if kind=='invoice' else 'Support cases')
        self._click('link',['New entry'] if kind=='invoice' else ['New case'])
        return {'action':'refresh_form','page':self.page.url}

    def write_ledger_entry(self,invoice_id,invoice,task_id):
        self._section('Accounts payable')
        self._click('link',['New entry'])
        self._select(['Vendor'],invoice['vendor'])
        for label,value in [('Invoice number',invoice['number']),('Amount (USD)',f'{invoice["amount_cents"]/100:.2f}'),
                             ('Due date',invoice['due_date']),('Source invoice ID',invoice_id),('Authorized task ID',task_id)]:
            self._fill([label],value)
        self._click('button',['Record invoice'])
        match=re.search(r'/workspace/ledger/(\d+)$',self.page.url)
        if match:return int(match.group(1))
        error=self.page.locator('.form-error')
        msg=error.inner_text().strip() if error.count() else 'Form submitted without confirmation'
        if 'Temporary' in msg or 'unavailable' in msg:raise RetryableToolError(msg)
        raise ToolError(msg)

    def verify_entry(self,entry_id,expected,evidence_path=None):
        self._goto(self.url+f'/workspace/ledger/{entry_id}')
        node=self.page.locator('#verified-ledger-entry')
        observed={'vendor':node.get_attribute('data-vendor'),'number':node.get_attribute('data-number'),
                  'amount_cents':int(node.get_attribute('data-amount-cents')),
                  'due_date':node.get_attribute('data-due-date'),'currency':node.get_attribute('data-currency')}
        matched=all(observed[k]==expected[k] for k in observed)
        if evidence_path:
            evidence_path.parent.mkdir(parents=True,exist_ok=True)
            self.page.screenshot(path=str(evidence_path),full_page=True)
        return {'matched':matched,'observed':observed,'entry_id':entry_id,'page':self.page.url,
                'source':'fresh_browser_readback'}

    def search_tickets(self,number=''):
        self._section('Support inbox')
        if number:
            self._fill(['Search ticket or subject','search'],number)
            self._click('button',['Search tickets'])
        return [{'id':int(r.get_attribute('data-ticket-id')),
                 'number':r.locator('.number').inner_text().strip(),
                 'subject':r.locator('.subject').inner_text().strip(),
                 'arrived_at':r.locator('.arrived').inner_text().strip()}
                for r in self.page.locator('tr[data-ticket-id]').all()]

    def read_ticket(self,ticket_id):
        row=self.page.locator(f'tr[data-ticket-id="{int(ticket_id)}"]')
        if row.count() and row.locator('a').count():
            link=row.locator('a').first
            self._guard(urljoin(self.page.url,link.get_attribute('href') or ''))
            self._point(link)
            link.click()
            self.page.wait_for_load_state('domcontentloaded')
            self._snapshot('open-support-ticket')
        else:
            self._goto(self.url+f'/workspace/tickets/{ticket_id}')
        node=self.page.locator('#ticket-document')
        return {'number':node.get_attribute('data-number'),'requester':node.get_attribute('data-requester'),
                'subject':node.get_attribute('data-subject'),
                'description':self.page.locator('#ticket-description').inner_text(),'url':self.page.url}

    def find_case(self,number):
        self._section('Support cases')
        self._fill(['Ticket or subject','search'],number)
        self._click('button',['Find cases'])
        for r in self.page.locator('tr[data-case-id]').all():
            if r.get_attribute('data-number')==number:return int(r.get_attribute('data-case-id'))
        return None

    def write_case(self,ticket_id,facts,task_id):
        self._section('Support cases')
        self._click('link',['New case'])
        for label,value in [('Source ticket ID',ticket_id),('Ticket number',facts['number']),
                            ('Requester',facts['requester']),('Subject',facts['subject']),('Task ID',task_id)]:
            self._fill([label],value)
        for label,key in [('Category','category'),('Priority','priority'),('Assigned team','assigned_team')]:
            value=facts[key]
            # Lowercase selects: browser matches visible option labels.
            self._select([label],value)
        self._click('button',['Create assigned case'])
        match=re.search(r'/workspace/cases/(\d+)$',self.page.url)
        if match:return int(match.group(1))
        error=self.page.locator('.form-error')
        msg=error.inner_text().strip() if error.count() else 'Support case not confirmed'
        if 'Temporary' in msg or 'unavailable' in msg:raise RetryableToolError(msg)
        raise ToolError(msg)

    def verify_case(self,case_id,expected,evidence_path=None):
        self._goto(self.url+f'/workspace/cases/{case_id}')
        node=self.page.locator('#verified-support-case')
        observed={key:node.get_attribute('data-'+key.replace('_','-'))
                  for key in ('number','requester','subject','category','priority','assigned_team')}
        matched=all(observed[k]==expected[k] for k in observed)
        if evidence_path:
            evidence_path.parent.mkdir(parents=True,exist_ok=True)
            self.page.screenshot(path=str(evidence_path),full_page=True)
        return {'matched':matched,'observed':observed,'case_id':case_id,'page':self.page.url,
                'source':'fresh_browser_readback'}
