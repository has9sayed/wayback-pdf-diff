wayback-pdf-diff
=================

Tools for diffing and comparing PDF content in a way that mirrors the JSON API of `web-monitoring-diff`. It can be used as:

- a **Python library** (call diff functions directly), or  
- a small **HTTP server** that exposes PDF diff endpoints compatible with the existing web-monitoring-diff frontend.

The goal is to make PDF diffs “drop in” alongside the existing HTML diff infrastructure.

-------------------------------------------------------------------------------
Installation
-------------------------------------------------------------------------------

Requirements
------------

- Python 3.10 or newer
- A C compiler and basic build tools (needed by PyMuPDF / Pillow on some platforms)
- `pip` or any PEP 517–compatible installer

Core install
------------

From the project root:

    python3 -m venv .venv
    source .venv/bin/activate

    pip install --upgrade pip
    pip install .

This installs the library (`wayback_pdf_diff`) only.

Install with server extras
--------------------------

To run the HTTP server, you also need the optional `server` extra (Tornado):

    pip install ".[server]"

For development / editing in-place, install editable with extras:

    pip install -e ".[server]"

Verify installation:

    python -c "import wayback_pdf_diff; print(wayback_pdf_diff.__version__)"

-------------------------------------------------------------------------------
Quick start: run the PDF diff server
-------------------------------------------------------------------------------

Start the server on the default port (8889):

    wayback-pdf-diff

or explicitly:

    python -m wayback_pdf_diff.server.server --port 8889

You should see:

    Starting wayback-pdf-diff server on port 8889

Health check:

    curl http://localhost:8889/healthcheck

List available diff types:

    curl http://localhost:8889/

Typical JSON response:

    {
      "diff_types": ["pdf_text_dmp", "pdf_text_rendered", "html_token", "pdf_visual", ...],
      "version": "0.1.0"
    }

-------------------------------------------------------------------------------
HTTP API
-------------------------------------------------------------------------------

The server mirrors the `web-monitoring-diff` contract:

- Base URL: `http://localhost:8889`
- Pattern: `GET /<diff_type>?a=<url>&b=<url>[&dpi=<int>]`
- Response: JSON dict, shape depends on the diff type

Example: text diff using diff-match-patch
-----------------------------------------

    curl "http://localhost:8889/pdf_text_dmp\
        ?a=http://web.archive.org/web/20130301000000id_/https://example.com/a.pdf\
        &b=http://web.archive.org/web/20230301000000id_/https://example.com/a.pdf"

Returns:

    {
      "change_count": 108,
      "diff": [[0, "Form "], [1, " "], [0, "W-4"], ...],
      "version": "0.1.0",
      "type": "pdf_text_dmp"
    }

Example: HTML-rendered text diff
--------------------------------

    curl "http://localhost:8889/pdf_text_rendered\
        ?a=http://web.archive.org/web/20130301000000id_/https://example.com/a.pdf\
        &b=http://web.archive.org/web/20230301000000id_/https://example.com/a.pdf"

Returns:

- `change_count`, `insertions_count`, `deletions_count`
- `combined`, `insertions`, `deletions` — full HTML snippets with `<ins class="wm-diff">` and `<del class="wm-diff">` markers, plus inline CSS that colors insertions/deletions.

This shape matches `html_token` from `web-monitoring-diff`, so existing HTML diff renderers can be reused.

Example: visual (pixel) diff
----------------------------

    curl "http://localhost:8889/pdf_visual\
        ?a=http://web.archive.org/web/20130301000000id_/https://example.com/a.pdf\
        &b=http://web.archive.org/web/20230301000000id_/https://example.com/a.pdf\
        &dpi=150"

Returns:

- `change_count`: number of pages with any pixel changes
- `diff`:
  - `page_count_a`, `page_count_b`
  - `pages`: array of per-page dicts with:
    - `status`: `"unchanged" | "changed" | "added" | "removed"`
    - `a_image`, `b_image`, `diff_image`: base64‑encoded PNGs
    - `total_pixels`, `changed_pixels`, `percent_changed`

-------------------------------------------------------------------------------
Diff types and their JSON shapes
-------------------------------------------------------------------------------

Defined in `wayback_pdf_diff/routes.py`:

- `length` → `compare_length(a_body, b_body)`
  - Output: `{"diff": <int delta_bytes>}`

- `identical_bytes` → `identical_bytes(a_body, b_body)`
  - Output: `{"diff": <bool same_bytes>}`

- `side_by_side_text` → `side_by_side_text(a_body, b_body)`
  - Output:

        {
          "diff": {
            "a_text": "<plain text>",
            "b_text": "<plain text>"
          }
        }

- `pdf_text_dmp` → `pdf_text_diff(a_body, b_body)`
  - Output like `html_text_dmp` in web-monitoring-diff:

        {
          "change_count": <int>,
          "diff": [[code, text], ...]
        }

    where `code` is:
    - `-1` deletion
    - `0` unchanged
    - `1` insertion

- `pdf_text_rendered` and `html_token` → `pdf_text_diff_html(a_body, b_body)`
  - Output like `html_token`:

        {
          "change_count": <int>,
          "insertions_count": <int>,
          "deletions_count": <int>,
          "combined": "<html ...>",
          "insertions": "<html ...>",
          "deletions": "<html ...>"
        }

- `pdf_visual` → `pdf_visual_diff(a_body, b_body, dpi=150)`
  - Layout-preserving visual diff, as described in the previous section.

The HTTP layer (`DiffHandler`) automatically injects:

- `version`: package version from `wayback_pdf_diff.__version__`
- `type`: the diff type string (e.g. `"pdf_text_rendered"`)

-------------------------------------------------------------------------------
Library usage (Python)
-------------------------------------------------------------------------------

Basic text diff:

    from wayback_pdf_diff import pdf_diffs

    with open("old.pdf", "rb") as fa, open("new.pdf", "rb") as fb:
        a_bytes = fa.read()
        b_bytes = fb.read()

    result = pdf_diffs.pdf_text_diff(a_bytes, b_bytes)
    print(result["change_count"])
    print(result["diff"][:10])

HTML-rendered diff:

    html_result = pdf_diffs.pdf_text_diff_html(a_bytes, b_bytes)
    combined_html = html_result["combined"]
    with open("diff.html", "w", encoding="utf-8") as f:
        f.write(combined_html)

Visual diff:

    visual = pdf_diffs.pdf_visual_diff(a_bytes, b_bytes, dpi=150)
    first_page = visual["diff"]["pages"][0]
    diff_png_b64 = first_page["diff_image"]

-------------------------------------------------------------------------------
CORS and integration with a frontend
-------------------------------------------------------------------------------

The included HTTP server (`wayback_pdf_diff.server.server`) sets permissive CORS headers by default:

- `Access-Control-Allow-Origin`: mirrors request `Origin` if allowed, otherwise `"*"` when `ACCESS_CONTROL_ALLOW_ORIGIN_HEADER` is not set.
- `Access-Control-Allow-Credentials`: `true`
- `Access-Control-Allow-Headers`: `x-requested-with`
- `Access-Control-Allow-Methods`: `GET, OPTIONS`

This is enough for a local frontend (e.g. `http://localhost:5000`) to talk to `http://localhost:8889` directly, including `OPTIONS` preflight.

Typical frontend wiring:

- For PDF diff types, point your client’s base URL at `http://localhost:8889`.
- Call:
  - `/pdf_text_dmp` for raw DMP text diffs.
  - `/pdf_text_rendered` (or `/html_token`) for HTML-rendered diffs compatible with existing `html_token` renderers.
  - `/pdf_visual` for layout-preserving image diffs.

-------------------------------------------------------------------------------
Development and tests
-------------------------------------------------------------------------------

Create and activate a virtual environment, then install dev dependencies:

    python3 -m venv .venv
    source .venv/bin/activate

    pip install -e ".[server]"
    pip install -e ".[dev]"

Run tests:

    pytest

The test suite (`tests/`) exercises both text-based and visual PDF diffs.

-------------------------------------------------------------------------------
Core libraries
-------------------------------------------------------------------------------

- **PyMuPDF (`pymupdf`)**  
  - Used for PDF text extraction and page rendering.  
  - Provides `extract_text()`, `render_page()`, and `page_count()` helpers in `wayback_pdf_diff.extract`.

- **fast-diff-match-patch**  
  - High‑performance Python port of Google’s diff‑match‑patch.
  - Used to compute character-level diffs between extracted texts.

- **Pillow**  
  - Python Imaging Library fork.
  - Used for PNG generation and pixel-level operations in `pdf_visual_diff`.

- **Tornado** (optional `server` extra)  
  - Async HTTP server framework.
  - Powers `wayback_pdf_diff.server.server`, including:
    - URL routing and handler classes
    - Async upstream fetches of PDFs
    - CORS handling
    - Process pool for CPU‑heavy diffing work.

-------------------------------------------------------------------------------
License
-------------------------------------------------------------------------------

- License: **AGPL-3.0-only**  
- Copyright: Internet Archive