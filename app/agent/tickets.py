"""Support ticket goal interpretation. A different workflow on the same worker runtime."""
from __future__ import annotations
import re
from app.agent.interpret import UnsupportedTask


def understand_ticket(instruction: str) -> dict:
    if len(instruction)>600:
        raise UnsupportedTask('Task text is too long')
    if re.search(r'\b(delete|erase|refund|email|send|close|resolve|transfer|pay|wire)\b', instruction, re.I):
        raise UnsupportedTask('This sandbox can triage or check tickets, not send, refund, resolve, or delete')
    match=re.search(r'\bTKT-\d{3,5}\b',instruction,re.I)
    number=match.group(0).upper() if match else None
    check=bool(re.search(r'\b(check|whether|status|already|verify)\b',instruction,re.I))
    triage=bool(re.search(r'\b(triage|assign|route|create|process|handle|record|log)\b',instruction,re.I))
    return {'workflow':'support_ticket','operation':'check' if check and not triage else 'triage',
            'ticket_number':number,'selection':'specific' if number else 'latest',
            'interpretation':'bounded multi-workflow goal interpreter'}
