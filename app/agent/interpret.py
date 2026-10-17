"""Goal interpreter with Gemma 4 E2B proposals and authoritative safety checks."""
from __future__ import annotations
import re
from typing import Optional
from app.config import Settings
from app.agent.gemma import GemmaClient, InvalidModelResponse

class NeedClarification(Exception):pass
class UnsupportedTask(Exception):pass

def understand(instruction:str,vendor_names:list[str],settings:Settings)->dict:
    prompt=' '.join(instruction.split())
    if len(prompt)>600:raise UnsupportedTask('Instruction must be 600 characters or fewer')
    if not re.search(r'\binvoice(s)?\b',prompt,re.I):
        raise UnsupportedTask('This prototype supports invoice recording and verification only')
    if re.search(r'\b(delete|erase|remove|transfer|pay|wire|send money)\b',prompt,re.I):
        raise UnsupportedTask('Payment, deletion and transfer actions are not supported')
    explicit=[v for v in vendor_names if v.lower() in prompt.lower()]
    if len(explicit)>1:raise NeedClarification('Multiple vendors mentioned. Specify one vendor')
    if not explicit:
        candidates=[v for v in vendor_names if len(v.split()[0])>=4 and re.search(
            r'\b'+re.escape(v.split()[0])+r'\b',prompt,re.I)]
        if len(candidates)==1:explicit=candidates
    if not explicit:raise NeedClarification('Specify an existing vendor: '+', '.join(sorted(vendor_names)))
    match=re.search(r'\b(?:invoice\s*(?:#|no\.?|number)?\s*[:#]?\s*)?([A-Za-z]{1,5}-\d{2,4}(?:-\d{2,4})?)\b',prompt,re.I)
    invoice_number:Optional[str]=match.group(1) if match else None
    write_requested=bool(re.search(r'\b(record|enter|log|post|process|file|save|book|insert|create)\b',prompt,re.I))
    check=bool(re.search(r'\b(check|verify|already recorded|status)\b',prompt,re.I))
    operation='check' if check and not write_requested else 'record'
    interpretation='offline constrained rules'
    if settings.model_backend=='gemma':
        try:
            proposal=GemmaClient(settings.ollama_url,settings.ollama_timeout).decide(
                'invoice_operation',{'instruction':prompt,'vendor':explicit[0]})
            interpretation='Gemma 4 E2B proposal + authoritative business guards'
            # Do not let a model make a read-only inquiry into an unrequested write,
            # or change a user-requested write into a check.
            if not (check or write_requested):operation=proposal['operation']
        except InvalidModelResponse:
            interpretation='Gemma invalid response; safe deterministic interpretation'
    return {'operation':operation,'vendor':explicit[0],'invoice_number':invoice_number,
            'selection':'specific' if invoice_number else 'latest','interpretation':interpretation}
