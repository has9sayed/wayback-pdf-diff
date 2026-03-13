__version__ = '0.1.0'

from .pdf_diffs import (  # noqa: F401
    compare_length,
    identical_bytes,
    side_by_side_text,
    pdf_text_diff,
    pdf_text_diff_html,
    pdf_visual_diff,
)
