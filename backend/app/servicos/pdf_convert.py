"""Conversao DOCX -> PDF usando LibreOffice headless (substitui docx2pdf/MS Word)."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


def docx_to_pdf(docx_path: str) -> str:
    docx_path = Path(docx_path)
    out_dir = tempfile.mkdtemp()
    result = subprocess.run(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            out_dir,
            str(docx_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    pdf_path = Path(out_dir) / (docx_path.stem + ".pdf")
    if result.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f"Falha ao converter DOCX para PDF: {result.stderr}")
    return str(pdf_path)
