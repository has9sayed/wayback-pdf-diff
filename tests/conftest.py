from __future__ import annotations

import fitz
import pytest


def _make_pdf(text: str, *, font_size: float = 11) -> bytes:
    """Create a minimal single-page PDF containing *text*."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), text, fontsize=font_size)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture()
def pdf_a() -> bytes:
    return _make_pdf("Hello World\nThis is document A.")


@pytest.fixture()
def pdf_b() -> bytes:
    return _make_pdf("Hello World\nThis is document B.")


@pytest.fixture()
def pdf_identical(pdf_a) -> tuple[bytes, bytes]:
    return pdf_a, pdf_a


@pytest.fixture()
def pdf_pair(pdf_a, pdf_b) -> tuple[bytes, bytes]:
    return pdf_a, pdf_b
