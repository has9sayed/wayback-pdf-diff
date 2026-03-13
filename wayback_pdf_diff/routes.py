"""
DIFF_ROUTES mapping for PDF diffs.

This mirrors the ``DIFF_ROUTES`` dict in web-monitoring-diff's server module.
A web service integrating wayback-pdf-diff can merge this mapping into its
own routing table.

Usage from a web service::

    from wayback_pdf_diff.routes import DIFF_ROUTES as PDF_DIFF_ROUTES
    # merge into your existing routes dict
    all_routes = {**HTML_DIFF_ROUTES, **PDF_DIFF_ROUTES}
"""
from __future__ import annotations

from . import pdf_diffs

DIFF_ROUTES: dict[str, callable] = {
    # Basic, media-agnostic helpers
    "length": pdf_diffs.compare_length,
    "identical_bytes": pdf_diffs.identical_bytes,
    "side_by_side_text": pdf_diffs.side_by_side_text,
    # Native PDF routes
    "pdf_text_dmp": pdf_diffs.pdf_text_diff,
    "pdf_text_rendered": pdf_diffs.pdf_text_diff_html,
    "html_token": pdf_diffs.pdf_text_diff_html,
    "pdf_visual": pdf_diffs.pdf_visual_diff,
}
