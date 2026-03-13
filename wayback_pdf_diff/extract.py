"""
PDF content extraction using PyMuPDF (fitz).

All extraction functions accept raw PDF bytes and return structured data.
They never do I/O themselves — the caller is responsible for fetching content.
"""
from __future__ import annotations

import fitz

from .exceptions import UndiffableContentError


def _open_pdf(data: bytes) -> fitz.Document:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise UndiffableContentError(
            f"Could not open data as PDF: {exc}"
        ) from exc
    if doc.page_count == 0:
        raise UndiffableContentError("PDF has zero pages")
    return doc


def extract_text(data: bytes) -> str:
    """Return the concatenated visible text of every page, separated by form-feeds."""
    doc = _open_pdf(data)
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()
    return "\f".join(pages)


def extract_text_by_page(data: bytes) -> list[str]:
    """Return a list of per-page text strings."""
    doc = _open_pdf(data)
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return pages


def render_page(data: bytes, page_num: int, *, dpi: int = 150) -> bytes:
    """Render a single page to PNG bytes at the given DPI."""
    doc = _open_pdf(data)
    if page_num >= doc.page_count:
        doc.close()
        raise UndiffableContentError(
            f"Page {page_num} out of range (document has {doc.page_count} pages)"
        )
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = doc[page_num].get_pixmap(matrix=mat)
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes


def page_count(data: bytes) -> int:
    doc = _open_pdf(data)
    count = doc.page_count
    doc.close()
    return count


def extract_metadata(data: bytes) -> dict:
    """Return PDF metadata as a flat dict."""
    doc = _open_pdf(data)
    meta = dict(doc.metadata) if doc.metadata else {}
    meta["page_count"] = doc.page_count
    doc.close()
    return meta
