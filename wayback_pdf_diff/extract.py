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


def extract_positioned_words(
    data: bytes,
) -> tuple[str, list[dict]]:
    """Extract words with bounding box positions from every page.

    Returns ``(full_text, word_positions)`` where:

    * ``full_text`` — words joined by spaces within a line, ``\\n`` between
      lines and between text blocks; pages separated by ``\\f``.
    * ``word_positions`` — list of dicts, one per word::

          {"start": int, "end": int, "page": int,
           "x": float, "y": float, "w": float, "h": float}

      ``start`` / ``end`` are character offsets into ``full_text``.
      ``x``, ``y``, ``w``, ``h`` are in PDF points (origin top-left,
      y-axis pointing down — PyMuPDF device coordinates, compatible
      with PDF.js canvas coordinates when multiplied by the same scale).

    Words are grouped by their PDF text-block before sorting.  This keeps
    multi-column layouts coherent: words from column A are never interleaved
    with words from column B (which ``sort=True`` on a flat word list would
    produce), so DMP sees the same paragraph order in both versions of a
    document even when column widths or x-positions change between captures.
    """
    doc = _open_pdf(data)
    text_parts: list[str] = []
    positions: list[dict] = []
    offset = 0

    for page_num in range(len(doc)):
        page = doc[page_num]

        # fetch words with their block/line/word indices but WITHOUT the
        # flat (y, x) sort that would interleave multi-column content.
        # tuple: (x0, y0, x1, y1, word, block_no, line_no, word_no)
        raw_words = page.get_text("words")

        # --- group by block, sort within block by (line_no, word_no) -------
        blocks: dict[int, list] = {}
        for w in raw_words:
            blocks.setdefault(w[5], []).append(w)
        for block_words in blocks.values():
            block_words.sort(key=lambda w: (w[6], w[7]))

        # sort blocks by the top-left corner of the block's bounding box so
        # that upper blocks come before lower ones and left columns before
        # right columns at the same vertical band.
        sorted_blocks = sorted(
            blocks.values(),
            key=lambda bw: (min(w[1] for w in bw), min(w[0] for w in bw)),
        )

        # --- build text + position list -----------------------------------
        first_word_on_page = True
        for block_words in sorted_blocks:
            prev_line_no: int | None = None

            for x0, y0, x1, y1, word, _bn, line_no, _wn in block_words:
                if first_word_on_page:
                    first_word_on_page = False
                elif prev_line_no is None:
                    # first word of a new block → block separator
                    text_parts.append("\n")
                    offset += 1
                elif line_no != prev_line_no:
                    # new line within the same block
                    text_parts.append("\n")
                    offset += 1
                else:
                    # same line, same block → inter-word space
                    text_parts.append(" ")
                    offset += 1

                start = offset
                text_parts.append(word)
                offset += len(word)
                positions.append(
                    {
                        "start": start,
                        "end": offset,
                        "page": page_num,
                        "x": float(x0),
                        "y": float(y0),
                        "w": float(x1 - x0),
                        "h": float(y1 - y0),
                    }
                )
                prev_line_no = line_no

        text_parts.append("\f")
        offset += 1

    doc.close()
    return "".join(text_parts), positions
