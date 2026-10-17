/* The web UI displays agent state and permits explicit human actions.
 * Decision-making and browser work execute independently on the server. */
let selectedTask=null;
let interval=null;
const $=(id)=>document.getElementById(id);
const safeText=(value)=>String(value??'');
function el(tag,cls,text){const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=safeText(text);return node;}
async function api(url,opts={}){let response=await fetch(url,{headers:{'Content-Type':'application/json'},...opts});let data=await response.json();if(!response.ok)throw Error(data.detail||'Request failed');return data;}
async function startTask(instruction){
  $('submit-message').textContent='Starting...';$('start-task').disabled=true;
  try{let r=await api('/api/tasks',{method:'POST',body:JSON.stringify({instruction})});selectedTask=r.task_id;await loadTask();startPolling();}
  catch(e){$('submit-message').textContent=e.message;}
  finally{$('start-task').disabled=false;}
}
function startPolling(){if(interval)clearInterval(interval);interval=setInterval(loadTask,1200);}
async function loadTask(){if(!selectedTask)return;
 try{let task=await api('/api/tasks/'+selectedTask);renderTask(task);
   if(['completed','failed','rejected','needs_input','awaiting_approval'].includes(task.status)){clearInterval(interval);interval=null;refreshRecent();refreshCounters();}
 }catch(e){$('submit-message').textContent=e.message;}
}
function renderTask(task){
 $('submit-message').textContent='Task '+task.id.slice(0,8);
 const state=$('task-state');state.textContent=task.status.replaceAll('_',' ').toUpperCase();state.className='state '+task.status;
 const summary=$('task-summary');summary.replaceChildren();summary.append(el('strong','',task.instruction));
 if(task.report){summary.append(el('p','',`Outcome: ${task.report.outcome}${task.report.entry_id?' · Ledger entry #'+task.report.entry_id:''}`));
 if(task.report.evidence_url){const link=el('a','small-link','View verification evidence ↗');link.href=task.report.evidence_url;link.target='_blank';summary.append(link);}}
 if(task.report?.browser_video_url){const video=el('a','small-link','Watch actual Chromium execution ↗');video.href=task.report.browser_video_url;video.target='_blank';summary.append(el('p','', ''));summary.append(video);}
 if(task.error)summary.append(el('p','',task.error));
 const actions=$('task-actions');actions.replaceChildren();
 if(task.status==='awaiting_approval'){
   const div=el('div','approval-panel');div.append(el('p','',task.approval.reason));
   const yes=el('button','primary','Approve recording');const no=el('button','secondary','Reject');
   yes.onclick=()=>decision(task.id,'approve');no.onclick=()=>decision(task.id,'reject');div.append(yes,no);actions.append(div);
 }
 if(task.status==='needs_input'){
   const div=el('div','approval-panel');div.append(el('p','',task.error));
   const field=el('input');field.style.width='100%';field.value=task.instruction;div.append(field);
   const btn=el('button','primary','Submit clarification');btn.style.marginTop='10px';btn.onclick=async()=>{try{await api(`/api/tasks/${task.id}/clarify`,{method:'POST',body:JSON.stringify({instruction:field.value})});startPolling();loadTask();}catch(e){alert(e.message);}};
   div.append(btn);actions.append(div);
 }
 const planBox=$('task-plan');planBox.replaceChildren();
 const planEvent=task.events.find(e=>e.tool==='gemma_task_decomposition');
 if(planEvent){
   planBox.append(el('strong','',`Action plan · ${planEvent.detail.source}`));
   const items=el('ol');
   for(const step of planEvent.detail.steps||[]){const item=el('li','',step.replaceAll('_',' '));items.append(item);}
   planBox.append(items);
 }
 const trace=$('trace');trace.replaceChildren();
 for(const event of task.events){
   const row=el('div','trace-row');row.append(el('span','trace-marker',event.kind==='verification'?'✓':event.kind==='retry'?'↻':'·'));
   const content=el('div','trace-content');content.append(el('strong','',event.kind.toUpperCase()+' · '+(event.tool||'')));
   content.append(el('small','',event.created_at.slice(11,19)+' UTC'));
   const pre=el('pre','',JSON.stringify(event.detail,null,2));content.append(pre);row.append(content);trace.append(row);
 }
}
async function decision(id,kind){try{await api(`/api/tasks/${id}/${kind}`,{method:'POST'});startPolling();loadTask();}catch(e){alert(e.message);}}
async function refreshCounters(){
  try{
    const [ledger,cases]=await Promise.all([api('/api/ledger'),api('/api/cases')]);
    if($('recorded-invoices-count'))$('recorded-invoices-count').textContent=ledger.length;
    if($('support-cases-count'))$('support-cases-count').textContent=cases.length;
  }catch(error){console.error('Could not refresh sandbox counters',error);}
}
async function refreshRecent(){try{let rows=await api('/api/tasks');const parent=$('recent-tasks');parent.replaceChildren();
 for(const task of rows){let b=el('button','recent-task');b.dataset.taskId=task.id;b.append(el('span','mini-state',task.status),el('span','',task.instruction.slice(0,70)));b.onclick=()=>{selectedTask=task.id;loadTask();startPolling();};parent.append(b);}}
 catch(e){console.error(e);}}
$('task-form').addEventListener('submit',ev=>{ev.preventDefault();startTask($('instruction').value);});
document.querySelectorAll('[data-example]').forEach(b=>{b.addEventListener('click',()=>{$('instruction').value=b.dataset.example;});});
$('inject-failure').addEventListener('click',async()=>{try{let out=await api('/api/demo/fail-next-write',{method:'POST'});$('fault-feedback').textContent=out.message;}catch(e){$('fault-feedback').textContent=e.message;}});
$('inject-case-failure').addEventListener('click',async()=>{try{let out=await api('/api/demo/fail-next-case-write',{method:'POST'});$('fault-feedback').textContent=out.message;}catch(e){$('fault-feedback').textContent=e.message;}});
document.querySelectorAll('[data-task-id]').forEach(b=>b.onclick=()=>{selectedTask=b.dataset.taskId;loadTask();startPolling();});
