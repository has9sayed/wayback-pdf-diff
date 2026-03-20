wayback-pdf-diff
=================

Tools for diffing and comparing PDF content in a way that mirrors the JSON API of `web-monitoring-diff`. It can be used as:

- a **Python library** (call diff functions directly), or  
- a small **HTTP server** that exposes PDF diff endpoints compatible with the existing web-monitoring-diff frontend.

The goal is to make PDF diffs “drop in” alongside the existing HTML diff infrastructure.

## Example Output
 
Used this referance [www.irs.gov/pub/irs-pdf/fw4.pdf](https://web.archive.org/web/20130308204355id_/http://www.irs.gov/pub/irs-pdf/fw4.pdf) compared  with March 2022 and March 2023

<img width="1830" height="732" alt="image" src="https://github.com/user-attachments/assets/9443f7bd-db99-4bf4-9cd7-25af2f626e7a" />


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

