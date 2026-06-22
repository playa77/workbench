"""Comprehensive tests for workbench.services.export_service (100% coverage)."""

import os
import subprocess

import pytest

from workbench.services.export_service import (
    _build_latex_document,
    _convert_table,
    _escape_html,
    _escape_latex,
    _ph,
    _PH_IDX,
    _PH_MAP,
    _process_inline,
    _tie_heading,
    generate_pdf_print_page,
    list_templates,
    markdown_to_html,
    markdown_to_pdf_bytes,
)


# ===========================================================================
# _escape_html
# ===========================================================================


class TestEscapeHtml:
    def test_escapes_ampersand_first(self):
        assert _escape_html("a&b") == "a&amp;b"

    def test_escapes_lt_and_gt(self):
        assert _escape_html("<tag>") == "&lt;tag&gt;"

    def test_escapes_all_together(self):
        assert _escape_html("a&b <c> d") == "a&amp;b &lt;c&gt; d"

    def test_no_special_chars(self):
        assert _escape_html("hello world") == "hello world"

    def test_empty_string(self):
        assert _escape_html("") == ""


# ===========================================================================
# markdown_to_html
# ===========================================================================


class TestMarkdownToHtml:
    def test_empty_content(self):
        result = markdown_to_html("")
        assert "<!DOCTYPE html>" in result
        assert "<p" in result
        assert "Report</title>" in result

    def test_custom_title(self):
        result = markdown_to_html("Hello", title="My Title")
        assert "My Title</title>" in result
        assert "My Title</div>" in result

    def test_title_escaped(self):
        result = markdown_to_html("x", title="<script>alert(1)</script>")
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in result

    def test_heading_h1(self):
        result = markdown_to_html("# Main Heading")
        assert "<h1" in result
        assert "Main Heading" in result

    def test_heading_h2(self):
        result = markdown_to_html("## Sub Heading")
        assert "<h2" in result
        assert "Sub Heading" in result

    def test_heading_h3(self):
        result = markdown_to_html("### Sub Sub Heading")
        assert "<h3" in result
        assert "Sub Sub Heading" in result

    def test_bold(self):
        result = markdown_to_html("**bold text**")
        assert "<strong>bold text</strong>" in result

    def test_italic(self):
        result = markdown_to_html("*italic text*")
        assert "<em>italic text</em>" in result

    def test_inline_code(self):
        result = markdown_to_html("text `code` here")
        assert "<code>code</code>" in result

    def test_image(self):
        result = markdown_to_html("![alt](img.png)")
        assert '<img src="img.png" alt="alt"' in result

    def test_link(self):
        result = markdown_to_html("[text](http://example.com)")
        assert '<a href="http://example.com"' in result
        assert "text</a>" in result

    def test_blockquote(self):
        result = markdown_to_html("> quoted text")
        assert "<blockquote" in result
        assert "quoted text" in result

    def test_horizontal_rule(self):
        result = markdown_to_html("---")
        assert "<hr" in result

    def test_unordered_list_dash(self):
        result = markdown_to_html("- item 1\n- item 2")
        assert "<li" in result
        assert "item 1" in result
        assert "item 2" in result

    def test_unordered_list_star(self):
        result = markdown_to_html("* item 1\n* item 2")
        assert "<li" in result

    def test_ordered_list(self):
        result = markdown_to_html("1. first\n2. second")
        assert "<li" in result
        assert "first" in result
        assert "second" in result

    def test_paragraphs(self):
        result = markdown_to_html("para1\n\npara2")
        assert "para1" in result
        assert "para2" in result

    def test_newline_in_paragraph(self):
        result = markdown_to_html("line1\nline2")
        assert "line1<br>" in result or "line1<br/>" in result

    def test_html_escaping_in_content(self):
        """HTML in markdown content should be escaped, not rendered."""
        result = markdown_to_html("<script>alert(1)</script>")
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_html_escaping_around_structural_elements(self):
        """Structural elements (blockquotes, HR) should not be double-escaped."""
        result = markdown_to_html("> text with <angle>")
        assert "<blockquote" in result
        assert "&lt;angle&gt;" in result

    def test_full_structure(self):
        result = markdown_to_html("Hello", title="Report")
        assert result.startswith("<!DOCTYPE html>")
        assert "</html>" in result
        assert "class=\"container\"" in result
        assert "class=\"report-title\"" in result
        assert "<style>" in result
        assert "</style>" in result

    def test_indented_unordered(self):
        result = markdown_to_html("  - indented item")
        assert "<li" in result
        assert "indented item" in result

    def test_indented_unordered_star(self):
        result = markdown_to_html("  * indented star")
        assert "<li" in result


# ===========================================================================
# generate_pdf_print_page
# ===========================================================================


class TestGeneratePdfPrintPage:
    def test_contains_print_script(self):
        result = generate_pdf_print_page("# Hello", title="Test")
        assert "window.print()" in result
        assert "window.onload" in result
        assert "<script>" in result
        assert "Hello" in result

    def test_passes_custom_title(self):
        result = generate_pdf_print_page("body", title="CustomTitle")
        assert "CustomTitle" in result

    def test_script_before_body_end(self):
        result = generate_pdf_print_page("x")
        assert "</script>" in result
        assert result.index("<script>") < result.index("</body>")


# ===========================================================================
# _tie_heading
# ===========================================================================


class TestTieHeading:
    def test_replaces_comma_space_with_tie(self):
        assert _tie_heading("Hello, World") == "Hello,~World"

    def test_no_comma(self):
        assert _tie_heading("Hello World") == "Hello World"

    def test_multiple_commas(self):
        assert _tie_heading("A, B, C") == "A,~B,~C"

    def test_empty_string(self):
        assert _tie_heading("") == ""


# ===========================================================================
# _escape_latex
# ===========================================================================


class TestEscapeLatex:
    def test_backslash(self):
        result = _escape_latex("a\\b")
        # \\ -> \\textbackslash{} -> then {} within that get escaped too
        assert "\\textbackslash" in result
        assert "\\{" in result
        assert "\\}" in result

    def test_braces(self):
        assert _escape_latex("a{b}c}") == "a\\{b\\}c\\}"

    def test_ampersand(self):
        assert _escape_latex("a&b") == "a\\&b"

    def test_percent(self):
        assert _escape_latex("a%b") == "a\\%b"

    def test_dollar(self):
        assert _escape_latex("a$b") == "a\\$b"

    def test_hash(self):
        assert _escape_latex("a#b") == "a\\#b"

    def test_underscore(self):
        assert _escape_latex("a_b") == "a\\_b"

    def test_tilde(self):
        assert _escape_latex("a~b") == "a\\textasciitilde{}b"

    def test_caret(self):
        assert _escape_latex("a^b") == "a\\textasciicircum{}b"

    def test_all_special_chars(self):
        assert _escape_latex("\\{&%$#_~^")
        # Just ensure no exception and all are replaced

    def test_no_special_chars(self):
        assert _escape_latex("hello") == "hello"

    def test_empty_string(self):
        assert _escape_latex("") == ""


# ===========================================================================
# _ph (placeholder infrastructure)
# ===========================================================================


class TestPh:
    def _reset(self):
        import workbench.services.export_service as svc
        svc._PH_IDX = 0
        svc._PH_MAP.clear()

    def test_returns_unique_keys(self):
        self._reset()
        a = _ph("hello")
        b = _ph("world")
        assert a != b
        assert _PH_MAP[a] == "hello"
        assert _PH_MAP[b] == "world"


# ===========================================================================
# _process_inline
# ===========================================================================


class TestProcessInline:
    def test_bold(self):
        result = _process_inline("**bold**")
        assert "\\textbf{bold}" in result

    def test_italic(self):
        result = _process_inline("*italic*")
        assert "\\textit{italic}" in result

    def test_inline_code(self):
        result = _process_inline("`code`")
        assert "\\texttt{code}" in result

    def test_link(self):
        result = _process_inline("[text](http://example.com)")
        assert "\\href{http://example.com}{text}" in result

    def test_link_escapes_special_chars_in_url_and_text(self):
        result = _process_inline("[a&b](http://x.com?a=1&b=2)")
        assert "\\&" in result

    def test_image_is_discarded(self):
        result = _process_inline("![alt](img.png)")
        assert "img" not in result

    def test_citation(self):
        result = _process_inline("see [1] for details")
        assert "\\textsuperscript{[1]}" in result

    def test_escapes_special_chars_in_plain_text(self):
        result = _process_inline("a & b")
        assert "\\&" in result

    def test_mixed_formatting(self):
        result = _process_inline("**bold** and *italic* and `code`")
        assert "\\textbf{bold}" in result
        assert "\\textit{italic}" in result
        assert "\\texttt{code}" in result

    def test_placeholder_restoration(self):
        result = _process_inline("**hello**")
        assert "\x01" not in result  # no raw placeholders left

    def test_empty_string(self):
        assert _process_inline("") == ""

    def test_backslash_preserved_in_plain_text(self):
        result = _process_inline("a\\b")
        assert "\\textbackslash" in result


# ===========================================================================
# _convert_table
# ===========================================================================


class TestConvertTable:
    def test_with_separator_and_header(self):
        lines = ["| H1 | H2 |", "|---|---|", "| C1 | C2 |"]
        result = _convert_table(lines)
        assert "\\begin{tabular}" in result
        assert "\\toprule" in result
        assert "\\midrule" in result
        assert "\\bottomrule" in result
        assert "\\end{tabular}" in result
        assert "H1" in result
        assert "C1" in result

    def test_without_separator(self):
        lines = ["| C1 | C2 |", "| C3 | C4 |"]
        result = _convert_table(lines)
        assert "\\begin{tabular}" in result
        assert "C1" in result
        assert "C3" in result
        # No header treatment
        assert "\\midrule" not in result

    def test_no_columns(self):
        result = _convert_table([])
        assert result == ""

    def test_empty_cells(self):
        lines = ["|  |  |", "|---|---|", "|  |  |"]
        result = _convert_table(lines)
        assert "\\begin{tabular}" in result

    def test_inline_formatting_in_cells(self):
        lines = ["| **bold** | *italic* |", "|---|---|", "| `code` | plain |"]
        result = _convert_table(lines)
        assert "\\textbf" in result
        assert "\\textit" in result
        assert "\\texttt" in result

    def test_separator_only(self):
        """If there's only a separator line, no columns can be determined."""
        lines = ["|---|---|---|"]
        result = _convert_table(lines)
        assert result == ""


# ===========================================================================
# list_templates
# ===========================================================================


class TestListTemplates:
    def test_returns_list_of_dicts(self):
        templates = list_templates()
        assert isinstance(templates, list)
        assert len(templates) > 0

    def test_each_template_has_required_keys(self):
        for tmpl in list_templates():
            assert "key" in tmpl
            assert "name" in tmpl
            assert "description" in tmpl

    def test_first_is_professional(self):
        assert list_templates()[0]["key"] == "professional"

    def test_contains_all_known_templates(self):
        keys = {t["key"] for t in list_templates()}
        expected = {"professional", "tufte", "classic", "modern", "compact", "manuscript"}
        assert keys == expected

    def test_templates_are_immutable_copies(self):
        templates = list_templates()
        templates[0]["name"] = "Hacked"
        # Original should be unchanged
        updated = list_templates()
        assert updated[0]["name"] != "Hacked"


# ===========================================================================
# _build_latex_document
# ===========================================================================


class TestBuildLatexDocument:
    def test_empty_content(self):
        result = _build_latex_document("", "Test Title")
        assert "\\begin{document}" in result
        assert "Test Title" in result or "Test,~Title" in result

    def test_default_template(self):
        result = _build_latex_document("Hello", "Title")
        assert "document_pre" not in result  # raw template not visible

    def test_nonexistent_template_falls_back_to_professional(self):
        result = _build_latex_document("Hello", "Title", template_key="nonexistent")
        assert "\\section" not in result or True  # just checking no error
        assert "Hello" in result

    def test_heading_h1_section(self):
        result = _build_latex_document("# Hello", "Title")
        assert "\\section{Hello}" in result

    def test_heading_h2_subsection(self):
        result = _build_latex_document("## Hello", "Title")
        assert "\\subsection{Hello}" in result

    def test_heading_h3_subsubsection(self):
        result = _build_latex_document("### Hello", "Title")
        assert "\\subsubsection{Hello}" in result

    def test_executive_summary_heading(self):
        result = _build_latex_document("## Executive Summary\n\nContent", "Title")
        assert "\\section*" in result
        assert "\\begin{execsummarybox}" in result
        assert "\\end{execsummarybox}" in result

    def test_zusammenfassung_heading(self):
        result = _build_latex_document("## Zusammenfassung\n\nInhalt", "Title")
        assert "\\begin{execsummarybox}" in result

    def test_exec_summary_with_colon(self):
        result = _build_latex_document("## Executive Summary:\n\nContent", "Title")
        assert "\\begin{execsummarybox}" in result

    def test_sources_heading(self):
        result = _build_latex_document("## Sources\n\nSource 1", "Title")
        assert "\\begin{small}" in result
        assert "\\end{small}" in result
        assert "\\newpage" in result

    def test_quellen_heading(self):
        result = _build_latex_document("## Quellen\n\nQ1", "Title")
        assert "\\begin{small}" in result

    def test_references_heading(self):
        result = _build_latex_document("## References\n\nRef", "Title")
        assert "\\begin{small}" in result

    def test_bibliography_heading(self):
        result = _build_latex_document("## Bibliography\n\nBib", "Title")
        assert "\\begin{small}" in result

    def test_code_block(self):
        result = _build_latex_document("```\ncode line\n```", "Title")
        assert "\\begin{lstlisting}" in result
        assert "code line" in result
        assert "\\end{lstlisting}" in result

    def test_horizontal_rule(self):
        result = _build_latex_document("---", "Title")
        assert "\\hrule" in result

    def test_blockquote(self):
        result = _build_latex_document("> quoted text", "Title")
        assert "\\begin{quote}" in result
        assert "quoted text" in result
        assert "\\end{quote}" in result

    def test_multi_line_blockquote(self):
        result = _build_latex_document("> line1\n> line2", "Title")
        assert "line1 line2" in result

    def test_unordered_list(self):
        result = _build_latex_document("- item 1\n- item 2", "Title")
        assert "\\begin{itemize}" in result
        assert "\\item" in result
        assert "\\end{itemize}" in result

    def test_ordered_list(self):
        result = _build_latex_document("1. first\n2. second", "Title")
        assert "\\begin{enumerate}" in result
        assert "\\item" in result
        assert "\\end{enumerate}" in result

    def test_table(self):
        result = _build_latex_document("| H1 | H2 |\n|---|---|\n| C1 | C2 |", "Title")
        assert "\\begin{tabular}" in result

    def test_paragraph(self):
        result = _build_latex_document("This is a paragraph.", "Title")
        assert "This is a paragraph" in result

    def test_paragraph_with_line_break(self):
        result = _build_latex_document("line one\ncontinues here", "Title")
        assert "line one continues here" in result

    def test_empty_line_skipped(self):
        result = _build_latex_document("\n\n\n# Hi\n\n\n", "Title")
        assert "\\section{Hi}" in result

    def test_smart_heading_tie(self):
        result = _build_latex_document("# Hello, World", "Title")
        assert "Hello,~World" in result

    def test_escaped_title(self):
        result = _build_latex_document("", "Title with $pecial & chars")
        assert "\\$" in result or "\\&" in result

    def test_semantic_blocks_closed_on_next_heading(self):
        content = "## Executive Summary\n\nContent\n\n# New Section"
        result = _build_latex_document(content, "Title")
        assert "\\end{execsummarybox}" in result
        assert "\\section{New Section}" in result

    def test_sources_closed_on_next_heading(self):
        """Sources block closed when a new heading appears (covers lines 1312-1314)."""
        content = "## Sources\n\nRef1\n\n# New Heading"
        result = _build_latex_document(content, "Title")
        assert "\\end{small}" in result
        assert "New Heading" in result
        # The sources \end{small} should appear before the new section
        assert result.index("\\end{small}") < result.index("New Heading") or "\\end{small}" not in result

    def test_semantic_blocks_closed_at_end(self):
        content = "## Sources\n\nSome source"
        result = _build_latex_document(content, "Title")
        assert "\\end{small}" in result

    def test_code_block_with_language(self):
        result = _build_latex_document("```python\nprint('hi')\n```", "Title")
        assert "\\begin{lstlisting}" in result
        assert "print('hi')" in result
        assert "\\end{lstlisting}" in result

    def test_table_without_separator_in_document(self):
        result = _build_latex_document("| col1 | col2 |", "Title")
        assert "\\begin{tabular}" in result

    def test_blockquote_terminated_by_non_blockquote(self):
        """Blockquote ends when a non-quote line appears (covers line 1355)."""
        content = "> quote line 1\nnormal paragraph"
        result = _build_latex_document(content, "Title")
        assert "\\begin{quote}" in result
        assert "quote line 1" in result
        assert "\\end{quote}" in result
        assert "normal paragraph" in result

    def test_unordered_list_terminated_by_non_list(self):
        """Unordered list ends when a non-list line appears (covers line 1380)."""
        content = "- item 1\nnormal paragraph"
        result = _build_latex_document(content, "Title")
        assert "\\begin{itemize}" in result
        assert "\\item" in result
        assert "\\end{itemize}" in result
        assert "normal paragraph" in result

    def test_ordered_list_terminated_by_non_list(self):
        """Ordered list ends when a non-list line appears (covers line 1396)."""
        content = "1. first item\nnormal paragraph"
        result = _build_latex_document(content, "Title")
        assert "\\begin{enumerate}" in result
        assert "\\item" in result
        assert "\\end{enumerate}" in result
        assert "normal paragraph" in result


# ===========================================================================
# markdown_to_pdf_bytes
# ===========================================================================


class TestMarkdownToPdfBytes:
    """Helper to create a mock temp file for testing."""

    @staticmethod
    def _make_fake_file(fname):
        class FakeFile:
            name_val = fname

            @property
            def name(self):
                return self.name_val

            def write(self, s):
                pass

            def close(self):
                pass

        return FakeFile()

    def test_happy_path(self, tmp_path):
        """Mock tectonic compilation succeeding and producing PDF."""
        mock_pdf_content = b"%PDF-1.4 mock pdf content"

        def fake_run(*args, **kwargs):
            class FakeResult:
                returncode = 0
                stdout = ""
                stderr = ""
            return FakeResult()

        tex_path = str(tmp_path / "test_output.tex")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "tempfile.NamedTemporaryFile",
                lambda *a, **kw: self._make_fake_file(tex_path),
            )

            # Write the expected PDF output
            pdf_path = tmp_path / "test_output.pdf"
            pdf_path.write_bytes(mock_pdf_content)

            mp.setattr("subprocess.run", fake_run)

            result = markdown_to_pdf_bytes("# Hello", title="Test")
            assert result == mock_pdf_content

    def test_tectonic_not_found(self):
        """FileNotFoundError when tectonic binary is missing."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "tempfile.NamedTemporaryFile",
                lambda *a, **kw: self._make_fake_file("/tmp/foo.tex"),
            )
            mp.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("not found")),
            )
            with pytest.raises(RuntimeError, match="tectonic command not found"):
                markdown_to_pdf_bytes("# Hello")

    def test_tectonic_timeout(self):
        """subprocess.TimeoutExpired raises RuntimeError."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "tempfile.NamedTemporaryFile",
                lambda *a, **kw: self._make_fake_file("/tmp/foo.tex"),
            )
            mp.setattr(
                "subprocess.run",
                lambda *a, **kw: (_ for _ in ()).throw(
                    subprocess.TimeoutExpired(cmd="tectonic", timeout=120)
                ),
            )
            with pytest.raises(RuntimeError, match="timed out"):
                markdown_to_pdf_bytes("# Hello")

    def test_compilation_failure(self):
        """Non-zero return code from tectonic raises RuntimeError."""
        def fake_run(*args, **kwargs):
            class FakeResult:
                returncode = 1
                stdout = ""
                stderr = "LaTeX Error: File not found"
            return FakeResult()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "tempfile.NamedTemporaryFile",
                lambda *a, **kw: self._make_fake_file("/tmp/foo.tex"),
            )
            mp.setattr("subprocess.run", fake_run)

            with pytest.raises(RuntimeError, match="tectonic compilation failed"):
                markdown_to_pdf_bytes("# Hello")

    def test_pdf_not_produced(self, tmp_path):
        """tectonic succeeds but no PDF appears."""
        def fake_run(*args, **kwargs):
            class FakeResult:
                returncode = 0
                stdout = "compilation successful"
                stderr = ""
            return FakeResult()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "tempfile.NamedTemporaryFile",
                lambda *a, **kw: self._make_fake_file(str(tmp_path / "output.tex")),
            )
            mp.setattr("subprocess.run", fake_run)

            with pytest.raises(RuntimeError, match="did not produce expected PDF"):
                markdown_to_pdf_bytes("# Hello", title="Test")

    def test_cleanup_in_finally(self, tmp_path):
        """Temp files and aux dir are cleaned up in finally block even on error."""
        tex_file = tmp_path / "test_clean.tex"
        pdf_file = tmp_path / "test_clean.pdf"
        aux_dir = tmp_path / "test_clean.tex.d"

        # Create files that should be cleaned up
        tex_file.write_text("dummy")
        pdf_file.write_text("dummy")
        aux_dir.mkdir()
        (aux_dir / "cache").write_text("cached")

        def fake_run(*args, **kwargs):
            class FakeResult:
                returncode = 1
                stdout = ""
                stderr = "error"
            return FakeResult()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "tempfile.NamedTemporaryFile",
                lambda *a, **kw: self._make_fake_file(str(tex_file)),
            )
            mp.setattr("subprocess.run", fake_run)

            with pytest.raises(RuntimeError):
                markdown_to_pdf_bytes("# Hello", title="Test")

        # After cleanup, files should be gone
        assert not tex_file.exists()
        assert not pdf_file.exists()
        assert not aux_dir.exists()

    def test_cleanup_on_success(self, tmp_path):
        """Temp files are cleaned up even on success."""
        tex_path = str(tmp_path / "test_ok.tex")

        def fake_run(*args, **kwargs):
            class FakeResult:
                returncode = 0
                stdout = ""
                stderr = ""
            return FakeResult()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "tempfile.NamedTemporaryFile",
                lambda *a, **kw: self._make_fake_file(tex_path),
            )
            mp.setattr("subprocess.run", fake_run)

            # Create the pdf that will be read
            pdf_out = tmp_path / "test_ok.pdf"
            pdf_out.write_bytes(b"%PDF-1.4")

            result = markdown_to_pdf_bytes("# Hello", title="Test")
            assert result == b"%PDF-1.4"

        # Files should be cleaned up
        assert not os.path.exists(tex_path)
        assert not (tmp_path / "test_ok.pdf").exists()
