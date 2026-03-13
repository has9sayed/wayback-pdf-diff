from __future__ import annotations

import wayback_pdf_diff
from wayback_pdf_diff import (
    compare_length,
    identical_bytes,
    pdf_text_diff,
    pdf_text_diff_html,
    pdf_visual_diff,
    side_by_side_text,
)


class TestCompareLength:
    def test_same_length(self, pdf_identical):
        a, b = pdf_identical
        result = compare_length(a, b)
        assert "diff" in result
        assert result["diff"] == 0

    def test_different_length(self, pdf_pair):
        a, b = pdf_pair
        result = compare_length(a, b)
        assert "diff" in result
        assert isinstance(result["diff"], int)


class TestIdenticalBytes:
    def test_identical(self, pdf_identical):
        a, b = pdf_identical
        assert identical_bytes(a, b)["diff"] is True

    def test_different(self, pdf_pair):
        a, b = pdf_pair
        assert identical_bytes(a, b)["diff"] is False


class TestSideBySideText:
    def test_output_shape(self, pdf_pair):
        a, b = pdf_pair
        result = side_by_side_text(a, b)
        assert "diff" in result
        assert "a_text" in result["diff"]
        assert "b_text" in result["diff"]
        assert isinstance(result["diff"]["a_text"], str)
        assert isinstance(result["diff"]["b_text"], str)

    def test_text_content(self, pdf_pair):
        a, b = pdf_pair
        result = side_by_side_text(a, b)
        assert "document A" in result["diff"]["a_text"]
        assert "document B" in result["diff"]["b_text"]


class TestPdfTextDiff:
    def test_output_shape(self, pdf_pair):
        a, b = pdf_pair
        result = pdf_text_diff(a, b)
        assert "change_count" in result
        assert "diff" in result
        assert isinstance(result["change_count"], int)
        assert isinstance(result["diff"], list)

    def test_dmp_codes(self, pdf_pair):
        a, b = pdf_pair
        result = pdf_text_diff(a, b)
        for entry in result["diff"]:
            assert len(entry) == 2
            code, text = entry
            assert code in (-1, 0, 1)
            assert isinstance(text, str)

    def test_no_changes_when_identical(self, pdf_identical):
        a, b = pdf_identical
        result = pdf_text_diff(a, b)
        assert result["change_count"] == 0
        assert all(code == 0 for code, _ in result["diff"])


class TestPdfTextDiffHtml:
    def test_output_shape(self, pdf_pair):
        a, b = pdf_pair
        result = pdf_text_diff_html(a, b)
        assert "change_count" in result
        assert "insertions_count" in result
        assert "deletions_count" in result
        assert "combined" in result
        assert "insertions" in result
        assert "deletions" in result

    def test_html_contains_tags(self, pdf_pair):
        a, b = pdf_pair
        result = pdf_text_diff_html(a, b)
        combined = result["combined"]
        assert "<ins" in combined or "<del" in combined

    def test_counts_consistent(self, pdf_pair):
        a, b = pdf_pair
        result = pdf_text_diff_html(a, b)
        assert result["change_count"] == (
            result["insertions_count"] + result["deletions_count"]
        )


class TestPdfVisualDiff:
    def test_output_shape(self, pdf_pair):
        a, b = pdf_pair
        result = pdf_visual_diff(a, b)
        assert "change_count" in result
        assert "diff" in result
        diff_data = result["diff"]
        assert "page_count_a" in diff_data
        assert "page_count_b" in diff_data
        assert "pages" in diff_data
        assert isinstance(diff_data["pages"], list)

    def test_page_diff_fields(self, pdf_pair):
        a, b = pdf_pair
        result = pdf_visual_diff(a, b)
        page = result["diff"]["pages"][0]
        assert "page" in page
        assert "status" in page
        assert page["status"] in ("changed", "unchanged", "added", "removed")

    def test_identical_no_changes(self, pdf_identical):
        a, b = pdf_identical
        result = pdf_visual_diff(a, b)
        assert result["change_count"] == 0
        for page in result["diff"]["pages"]:
            assert page["status"] == "unchanged"


class TestVersion:
    def test_version_exists(self):
        assert hasattr(wayback_pdf_diff, "__version__")
        assert isinstance(wayback_pdf_diff.__version__, str)
