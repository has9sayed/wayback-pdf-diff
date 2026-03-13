"""
PDF diff functions.

Every public function here accepts raw PDF bytes (a_body / b_body) and returns
a dict whose shape matches the web-monitoring-diff JSON contract:

    {"diff": ..., "change_count": ..., ...}

The web service layer adds ``version`` and ``type`` before sending the response.
Function signatures use the same naming convention as web-monitoring-diff's
``caller()`` dependency-injection: ``a_body``, ``b_body``, ``a_text``, ``b_text``.

Compatible diff codes (inherited from diff-match-patch convention):
    -1  deletion
     0  unchanged
     1  insertion
"""
from __future__ import annotations

import base64
import io
import re
from html import escape as html_escape

from fast_diff_match_patch import diff
from PIL import Image, ImageChops

from . import extract

DIFF_CODES: dict[str, int] = {"=": 0, "-": -1, "+": 1}
REPEATED_BLANK_LINES = re.compile(r"([^\S\n]*\n\s*){2,}")


def _clean_text(text: str) -> str:
    return REPEATED_BLANK_LINES.sub("\n\n", text).strip()


def _compute_dmp_diff(
    a_text: str, b_text: str, *, timelimit: float = 4.0
) -> list[tuple[int, str]]:
    if not (isinstance(a_text, str) and isinstance(b_text, str)):
        raise TypeError("Both texts must be str")
    changes = diff(
        a_text,
        b_text,
        checklines=False,
        timelimit=timelimit,
        cleanup="Semantic",
        counts_only=False,
    )
    return [(DIFF_CODES[c[0]], c[1]) for c in changes]


# ── byte-level / length diffs (identical to web-monitoring-diff) ─────────────

def compare_length(a_body: bytes, b_body: bytes) -> dict:
    """Compute difference in response body lengths."""
    return {"diff": len(b_body) - len(a_body)}


def identical_bytes(a_body: bytes, b_body: bytes) -> dict:
    """Compute whether response bodies are exactly identical."""
    return {"diff": a_body == b_body}


# ── text-based diffs ─────────────────────────────────────────────────────────

def _extract_clean_text(pdf_bytes: bytes) -> str:
    return _clean_text(extract.extract_text(pdf_bytes))


def side_by_side_text(a_body: bytes, b_body: bytes) -> dict:
    """Extract visible text from both PDFs.

    Output shape matches ``side_by_side_text`` in web-monitoring-diff.
    """
    return {
        "diff": {
            "a_text": _extract_clean_text(a_body),
            "b_text": _extract_clean_text(b_body),
        }
    }


def pdf_text_diff(a_body: bytes, b_body: bytes) -> dict:
    """Diff the extracted text of two PDFs using diff-match-patch.

    Output shape matches ``html_text_dmp`` in web-monitoring-diff:
    ``{"change_count": int, "diff": [[code, text], ...]}``
    """
    a_text = _extract_clean_text(a_body)
    b_text = _extract_clean_text(b_body)
    result = _compute_dmp_diff(a_text, b_text, timelimit=2.0)
    change_count = sum(1 for code, _ in result if code != 0)
    return {"change_count": change_count, "diff": result}


def pdf_text_diff_html(a_body: bytes, b_body: bytes) -> dict:
    """Produce an HTML rendering of the text diff between two PDFs.

    Output shape matches ``html_token`` in web-monitoring-diff:
    ``{"change_count": int, "insertions_count": int, "deletions_count": int,
       "combined": html, "insertions": html, "deletions": html}``
    """
    a_text = _extract_clean_text(a_body)
    b_text = _extract_clean_text(b_body)
    result = _compute_dmp_diff(a_text, b_text, timelimit=4.0)

    insertions_count = 0
    deletions_count = 0
    combined_parts: list[str] = []
    ins_parts: list[str] = []
    del_parts: list[str] = []

    for code, text in result:
        escaped = html_escape(text).replace("\n", "<br>")
        if code == 0:
            combined_parts.append(f"<span>{escaped}</span>")
            ins_parts.append(f"<span>{escaped}</span>")
            del_parts.append(f"<span>{escaped}</span>")
        elif code == 1:
            insertions_count += 1
            combined_parts.append(
                f'<ins class="wm-diff">{escaped}</ins>'
            )
            ins_parts.append(
                f'<ins class="wm-diff">{escaped}</ins>'
            )
        elif code == -1:
            deletions_count += 1
            combined_parts.append(
                f'<del class="wm-diff">{escaped}</del>'
            )
            del_parts.append(
                f'<del class="wm-diff">{escaped}</del>'
            )

    _wrap = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<meta name="wm-diff-title" content="PDF Document">'
        '<template id="wm-diff-old-head"></template>'
        '<style id="wm-diff-style">'
        'body{{font-family:monospace;white-space:pre-wrap;}}'
        'ins.wm-diff, del.wm-diff {{display: unset;visibility: unset;opacity: 1;clip: auto;text-decoration: unset;color: inherit;}}'
        'ins.wm-diff, ins.wm-diff > * {{background-color: #a1d76a !important;}}'
        'del.wm-diff, del.wm-diff > * {{background-color: #e8a4c8 !important;}}'
        '</style>'
        '</head><body>{}</body></html>'
    )
    return {
        "change_count": insertions_count + deletions_count,
        "insertions_count": insertions_count,
        "deletions_count": deletions_count,
        "combined": _wrap.format("".join(combined_parts)),
        "insertions": _wrap.format("".join(ins_parts)),
        "deletions": _wrap.format("".join(del_parts)),
    }


# ── visual / image-based diffs ───────────────────────────────────────────────

def _image_from_png(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes)).convert("RGB")


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _b64_png(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


def _diff_single_page(
    a_png: bytes, b_png: bytes
) -> dict:
    a_img = _image_from_png(a_png)
    b_img = _image_from_png(b_png)

    width = max(a_img.width, b_img.width)
    height = max(a_img.height, b_img.height)
    a_resized = Image.new("RGB", (width, height), (255, 255, 255))
    a_resized.paste(a_img, (0, 0))
    b_resized = Image.new("RGB", (width, height), (255, 255, 255))
    b_resized.paste(b_img, (0, 0))

    diff_img = ImageChops.difference(a_resized, b_resized)

    pixels = list(diff_img.get_flattened_data())
    changed_pixels = sum(1 for p in pixels if p != (0, 0, 0))
    total_pixels = len(pixels)

    return {
        "diff_image": _b64_png(_png_bytes(diff_img)),
        "a_image": _b64_png(a_png),
        "b_image": _b64_png(b_png),
        "total_pixels": total_pixels,
        "changed_pixels": changed_pixels,
        "percent_changed": round(changed_pixels / total_pixels * 100, 4)
        if total_pixels
        else 0.0,
    }


def pdf_visual_diff(
    a_body: bytes, b_body: bytes, *, dpi: int = 150
) -> dict:
    """Render each page to an image and produce a pixel-level diff.

    Returns a structure with per-page visual diff data that can be consumed
    by the existing WBM UI or any other client.

    Output shape:
    ``{"change_count": int, "diff": {"pages": [...], "page_count_a": int, ...}}``
    """
    a_count = extract.page_count(a_body)
    b_count = extract.page_count(b_body)
    max_pages = max(a_count, b_count)

    pages: list[dict] = []
    total_changed = 0

    for i in range(max_pages):
        a_png = (
            extract.render_page(a_body, i, dpi=dpi) if i < a_count else None
        )
        b_png = (
            extract.render_page(b_body, i, dpi=dpi) if i < b_count else None
        )

        if a_png is None:
            pages.append({
                "page": i,
                "status": "added",
                "b_image": _b64_png(b_png),
            })
            total_changed += 1
        elif b_png is None:
            pages.append({
                "page": i,
                "status": "removed",
                "a_image": _b64_png(a_png),
            })
            total_changed += 1
        else:
            page_diff = _diff_single_page(a_png, b_png)
            status = "changed" if page_diff["changed_pixels"] > 0 else "unchanged"
            if status == "changed":
                total_changed += 1
            pages.append({"page": i, "status": status, **page_diff})

    return {
        "change_count": total_changed,
        "diff": {
            "page_count_a": a_count,
            "page_count_b": b_count,
            "pages": pages,
        },
    }
