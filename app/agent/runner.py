"""Goal -> Plan -> Act -> Observe -> Adapt -> Verify -> Report.

The autonomous controller can retry, stop safely, ask for clarification, and
resume after human approval. No task is declared complete on a submit alone.
"""
from __future__ import annotations

import time
import re
from pathlib import Path

from app.agent.browser import BrowserTools, ToolError, RetryableToolError
from app.agent.extract import extract_invoice, ExtractionError
from app.agent.interpret import understand, NeedClarification, UnsupportedTask
from app.agent.tickets import understand_ticket
from app.agent.policy import DecisionPolicy
from app.config import Settings
from app.agent.gemma import ModelUnavailable, GemmaClient
from app.db import Store


class Worker:
    def __init__(self, store: Store, settings: Settings, base_url: str):
        self.db=store
        self.settings=settings
        self.base_url=base_url
        self.policy=DecisionPolicy(settings)

    def event(self, task_id, kind, tool, **detail):
        self.db.add_event(task_id,kind,tool,detail)

    def complete(self, task_id, outcome, **detail):
        report={"outcome":outcome,**detail}
        self.db.update_task(task_id,status="completed",report=report,context={"result":outcome})
        self.event(task_id,"completed","final_report",**report)

    def run(self, task_id: str):
        task=self.db.task(task_id)
        if task is None:
            return
        if task["status"] not in {"queued","awaiting_approval"}:
            return
        self.db.update_task(task_id,status="running")
        self.event(task_id,"started","goal",instruction=task["instruction"])
        if self.settings.model_backend == 'gemma':
            info = self.policy.model.available()
            if not info['available']:
                self.db.update_task(task_id,status='failed',error=info['reason'])
                self.event(task_id,'failed','gemma_preflight',message=info['reason'])
                return
        try:
            self._perform(task_id,task)
        except NeedClarification as exc:
            self.db.update_task(task_id,status="needs_input",error=str(exc))
            self.event(task_id,"needs_input","ask_human",message=str(exc))
        except (ToolError,ExtractionError,UnsupportedTask,ValueError,ModelUnavailable) as exc:
            self.db.update_task(task_id,status="failed",error=str(exc))
            self.event(task_id,"failed","recovery",message=str(exc))
        except Exception as exc:
            # Useful failure classification; don't conceal unhandled exceptions.
            message=f"{type(exc).__name__}: {exc}"
            self.db.update_task(task_id,status="failed",error=message)
            self.event(task_id,"failed","unexpected_error",message=message)

    def _perform(self, task_id, task):
        from app.agent.reactive import execute_invoice, execute_ticket
        if re.search(r'\b(ticket|support request|helpdesk|customer issue|support case)\b',
                     task['instruction'],re.I):
            return execute_ticket(self,task_id,task)
        return execute_invoice(self,task_id,task)
