"""Extract plain text from uploaded PDF resumes."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text.strip())
    body = "\n\n".join(parts).strip()
    if not body:
        raise ValueError("no text extracted from PDF")
    return body
