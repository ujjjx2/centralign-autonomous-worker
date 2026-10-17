"""Extract business facts from two deliberately different *rendered* invoice layouts."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class ExtractionError(ValueError):
    pass


def capture(text: str, patterns: list[str], field: str) -> str:
    for pattern in patterns:
        result = re.search(pattern,text,re.I|re.M)
        if result:
            return result.group(1).strip()
    raise ExtractionError("Unable to identify "+field)


def iso_date(text: str) -> str:
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(),fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ExtractionError("Invalid due date: "+text)


def extract_invoice(text: str) -> dict:
    # This data is untrusted. Only known labelled fields are interpreted;
    # instructions appearing in descriptions/notes are ignored.
    vendor = capture(text,[r"^Vendor\s*:\s*([^\n]+)",r"^Billed by\s*:\s*([^\n]+)"],"vendor")
    number = capture(text,[r"^Invoice Number\s*:\s*([^\n]+)",r"^Reference\s*:\s*([^\n]+)"],"invoice number")
    amount = capture(text,[r"^Amount Due\s*:\s*(?:USD\s*)?\$?([0-9,]+(?:\.[0-9]{1,2})?)",
                           r"^Total Payable\s*:\s*(?:USD\s*)?\$?([0-9,]+(?:\.[0-9]{1,2})?)"],"amount")
    due = capture(text,[r"^Due Date\s*:\s*([^\n]+)",r"^Payment deadline\s*:\s*([^\n]+)"],"due date")
    try:
        cents = int((Decimal(amount.replace(",",""))*100).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        raise ExtractionError("Invalid invoice amount")
    if cents<=0:
        raise ExtractionError("Invoice amount must be positive")
    if not re.fullmatch(r"[\w-]{2,40}",number):
        raise ExtractionError("Unsafe or malformed invoice reference")
    return {"vendor":vendor,"number":number,"amount_cents":cents,"currency":"USD","due_date":iso_date(due)}
