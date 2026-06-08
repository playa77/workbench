"""Markdown-to-HTML conversion and HTML/PDF export functionality.

Provides:
    - markdown_to_html(content, title): Convert markdown to a full styled HTML document.
    - generate_pdf_print_page(content, title): Return an HTML page that auto-opens the
      browser print dialog (for saving as PDF).
"""

import re

# Placeholder markers used to protect HTML structural elements during escaping.
_PH_BQ_START = "\x00BQ\x00"
_PH_BQ_END = "\x00/BQ\x00"
_PH_HR = "\x00HR\x00"


def _escape_html(text: str) -> str:
    """Escape HTML special characters in text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_html(content: str, title: str = "Report") -> str:
    """Convert markdown text to a complete, styled HTML document.

    Handles: headings (# ## ###), bold (**), italic (*), inline code (`),
    blockquotes (>), unordered lists (- *), ordered lists (1.), paragraphs
    (double newlines), links, and horizontal rules (---).

    The returned HTML is a full document with embedded CSS that matches the
    workbench dark theme aesthetic.
    """
    md = content

    # ---- Phase 1: structural elements (before HTML escaping) ----
    # Blockquotes: replace markers with placeholders so ``>`` is not escaped
    md = re.sub(
        r"^> (.+)$",
        _PH_BQ_START + r"\1" + _PH_BQ_END,
        md,
        flags=re.MULTILINE,
    )
    # Horizontal rules: replace with placeholder
    md = re.sub(
        r"^---+$",
        _PH_HR,
        md,
        flags=re.MULTILINE,
    )

    # ---- Phase 2: HTML escaping (structural placeholders are safe) ----
    md = _escape_html(md)

    # ---- Phase 3: restore structural HTML ----
    blockquote_html = (
        '<blockquote style="border-left:3px solid #60a5fa;'
        'padding:6px 14px;margin:10px 0;color:#94a3b8;'
        'font-style:italic;background:#1a1f2e;'
        'border-radius:0 4px 4px 0">'
    )
    md = md.replace(_PH_BQ_START, blockquote_html)
    md = md.replace(_PH_BQ_END, "</blockquote>")
    md = md.replace(
        _PH_HR,
        '<hr style="border:none;border-top:1px solid #2d3748;margin:20px 0">',
    )

    # ---- Phase 4: inline markdown patterns ----
    # Bold
    md = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", md)
    # Italic
    md = re.sub(r"\*(.+?)\*", r"<em>\1</em>", md)
    # Inline code
    md = re.sub(r"`([^`]+)`", r"<code>\1</code>", md)
    # Images (must come before links)
    md = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        r'<img src="\2" alt="\1" style="max-width:100%;border-radius:6px;margin:12px 0">',
        md,
    )
    # Links
    md = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener" style="color:#60a5fa;text-decoration:none">\1</a>',
        md,
    )
    # Headings (must be processed before lists/paragraphs)
    md = re.sub(
        r"^### (.+)$",
        r'<h3 style="margin:20px 0 8px;font-size:16px;font-weight:600;color:#e2e8f0">\1</h3>',
        md,
        flags=re.MULTILINE,
    )
    md = re.sub(
        r"^## (.+)$",
        r'<h2 style="margin:24px 0 12px;font-size:18px;font-weight:700;color:#e2e8f0">\1</h2>',
        md,
        flags=re.MULTILINE,
    )
    md = re.sub(
        r"^# (.+)$",
        r'<h1 style="margin:28px 0 16px;font-size:22px;font-weight:700;color:#e2e8f0">\1</h1>',
        md,
        flags=re.MULTILINE,
    )
    # Unordered list items (indented)
    md = re.sub(
        r"^(  -|  \*) (.+)$",
        r'<li style="margin-left:40px;color:#cbd5e1">\2</li>',
        md,
        flags=re.MULTILINE,
    )
    md = re.sub(
        r"^[-*] (.+)$",
        r'<li style="margin-left:20px;color:#cbd5e1">\1</li>',
        md,
        flags=re.MULTILINE,
    )
    # Ordered list items
    md = re.sub(
        r"^\d+\. (.+)$",
        r'<li style="margin-left:20px;color:#cbd5e1">\1</li>',
        md,
        flags=re.MULTILINE,
    )
    # Paragraphs (double newlines)
    md = re.sub(r"\n\n", r'</p><p style="margin-bottom:10px;line-height:1.8">', md)
    # Remaining newlines
    md = re.sub(r"\n", r"<br>", md)

    body_content = (
        '<p style="margin-bottom:10px;line-height:1.8">' + md + "</p>"
    )

    css = """\
* { margin:0; padding:0; box-sizing:border-box; }
body {
    background-color: #0f1117;
    color: #cbd5e1;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.6;
    padding: 40px 20px;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
.container {
    max-width: 900px;
    margin: 0 auto;
    background: #161a24;
    border-radius: 10px;
    padding: 40px 48px;
    border: 1px solid #2d3748;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
}
.report-title {
    font-size: 24px;
    font-weight: 700;
    color: #e2e8f0;
    margin-bottom: 24px;
    padding-bottom: 12px;
    border-bottom: 1px solid #2d3748;
}
code {
    font-family: "SF Mono", "Fira Code", "Fira Mono", "Roboto Mono", Menlo, Courier, monospace;
    background: #1e2533;
    color: #93c5fd;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
}
pre {
    background: #1a1f2e;
    border: 1px solid #2d3748;
    border-radius: 6px;
    padding: 16px;
    margin: 12px 0;
    overflow-x: auto;
}
pre code {
    background: none;
    padding: 0;
    border-radius: 0;
    color: #cbd5e1;
    font-size: 0.85em;
    line-height: 1.5;
}
a:hover { text-decoration: underline !important; }
img { max-width: 100%; border-radius: 6px; margin: 12px 0; }
ul, ol { padding-left: 20px; margin: 8px 0; }
li { margin-bottom: 4px; }
h1, h2, h3, h4, h5, h6 { margin-top: 24px; }

@media print {
    body {
        background: #fff !important;
        color: #1a1a2e !important;
        padding: 20px !important;
    }
    .container {
        background: #fff !important;
        border: none !important;
        box-shadow: none !important;
        padding: 20px !important;
        max-width: 100% !important;
    }
    .report-title { color: #1a1a2e !important; border-bottom-color: #ddd !important; }
    h1, h2, h3 { color: #1a1a2e !important; }
    code { background: #f1f5f9 !important; color: #1e40af !important; }
    pre { background: #f8fafc !important; border-color: #ddd !important; }
    pre code { color: #1a1a2e !important; }
    blockquote { border-left-color: #3b82f6 !important; color: #475569 !important; background: #f8fafc !important; }
    a { color: #2563eb !important; }
    li { color: #1a1a2e !important; }
    p { color: #333 !important; }
}
""".strip()

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape_html(title)}</title>
    <style>
{css}
    </style>
</head>
<body>
    <div class="container">
        <div class="report-title">{_escape_html(title)}</div>
        {body_content}
    </div>
</body>
</html>"""


def generate_pdf_print_page(content: str, title: str = "Report") -> str:
    """Return an HTML page with auto-print JavaScript for PDF export.

    The page renders the full styled report and immediately opens the browser
    print dialog (``window.print()``) on load so the user can save as PDF.
    """
    html_doc = markdown_to_html(content, title=title)

    # Inject the auto-print script just before </body>
    script = (
        '<script>\n'
        'window.onload = function() {\n'
        '    window.print();\n'
        '};\n'
        '</script>\n'
    )
    html_doc = html_doc.replace("</body>", script + "</body>")

    return html_doc


def markdown_to_pdf_bytes(content: str, title: str = "Report") -> bytes:
    """Generate a professional PDF from markdown content using tectonic (LaTeX engine).

    Converts markdown to a LaTeX document, compiles it with tectonic
    (which auto-downloads missing LaTeX packages), and returns the raw PDF bytes.
    """
    import os
    import subprocess
    import tempfile

    latex_source = _build_latex_document(content, title)

    # Write .tex to a temp file
    tmp_tex = tempfile.NamedTemporaryFile(suffix=".tex", mode="w", delete=False, encoding="utf-8")
    tex_path: str | None = tmp_tex.name
    pdf_bytes: bytes | None = None
    try:
        tmp_tex.write(latex_source)
        tmp_tex.close()

        assert tex_path is not None
        out_dir = os.path.dirname(tex_path)

        # Compile with tectonic (XeTeX mode, auto-fetch packages)
        result = subprocess.run(
            ["tectonic", "-X", "compile", "--outdir", out_dir, tex_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tectonic compilation failed (exit {result.returncode}):\n"
                f"{result.stderr}"
            )

        pdf_path = tex_path.replace(".tex", ".pdf")
        if not os.path.exists(pdf_path):
            raise RuntimeError(
                f"tectonic did not produce expected PDF at {pdf_path}\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

    except FileNotFoundError:
        raise RuntimeError(
            "tectonic command not found. Install tectonic to enable PDF export."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("tectonic compilation timed out after 120 seconds.")
    finally:
        if tex_path is not None:
            # Clean up temp files
            base = tex_path.replace(".tex", "")
            for ext in (".tex", ".pdf", ".log", ".aux", ".out", ".toc"):
                p = base + ext
                if os.path.exists(p):
                    os.unlink(p)
            # Also clean up any tectonic cache/aux directory
            aux_dir = tex_path + ".d"
            if os.path.isdir(aux_dir):
                import shutil

                shutil.rmtree(aux_dir, ignore_errors=True)

    assert pdf_bytes is not None
    return pdf_bytes


# ---------------------------------------------------------------------------
# LaTeX helpers
# ---------------------------------------------------------------------------

_LATEX_SPECIAL = [
    ("\\", r"\textbackslash{}"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in plain text."""
    for char, replacement in _LATEX_SPECIAL:
        text = text.replace(char, replacement)
    return text


# Placeholder infrastructure for inline markdown→LaTeX conversion
# so we can escape raw text without damaging generated LaTeX commands.
_PH_IDX: int = 0
_PH_MAP: dict[str, str] = {}


def _ph(text: str) -> str:
    global _PH_IDX, _PH_MAP
    key = f"\x01PH{_PH_IDX}\x01"
    _PH_IDX += 1
    _PH_MAP[key] = text
    return key


def _process_inline(text: str) -> str:
    """Convert markdown inline formatting to LaTeX, escaping special chars.

    Handles: **bold**, *italic*, ``code``, [links](url), ![images](skipped),
    and [N] citations. Uses temporary placeholders so escaping does not
    corrupt generated LaTeX commands.
    """
    global _PH_IDX, _PH_MAP
    _PH_IDX = 0
    _PH_MAP.clear()

    # 1. Images — discard (no good LaTeX equivalent)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", text)

    # 2. Links → \href{url}{text}
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: _ph(
            r"\href{" + _escape_latex(m.group(2)) + "}{" + _escape_latex(m.group(1)) + "}"
        ),
        text,
    )

    # 3. Bold **text** → \textbf{text} (before italic so ** isn't consumed as * *)
    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: _ph(r"\textbf{" + _escape_latex(m.group(1)) + "}"),
        text,
    )

    # 4. Italic *text* → \textit{text}
    text = re.sub(
        r"\*(.+?)\*",
        lambda m: _ph(r"\textit{" + _escape_latex(m.group(1)) + "}"),
        text,
    )

    # 5. Inline code `text` → \texttt{text}
    text = re.sub(
        r"`([^`]+)`",
        lambda m: _ph(r"\texttt{" + _escape_latex(m.group(1)) + "}"),
        text,
    )

    # 6. Citations [N] → \textsuperscript{[N]}
    text = re.sub(r"\[(\d+)\]", lambda m: _ph(r"\textsuperscript{[" + m.group(1) + "]}"), text)

    # 7. Escape any remaining LaTeX special chars in raw text
    text = _escape_latex(text)

    # 8. Restore placeholders
    for key, value in _PH_MAP.items():
        text = text.replace(key, value)

    return text


def _convert_table(lines: list[str]) -> str:
    """Convert a list of markdown table rows to a LaTeX tabular environment."""
    # Find separator row (|---|---|)
    sep_idx = None
    for idx, line in enumerate(lines):
        if re.match(r"^\|[-:\s|]+\|$", line):
            sep_idx = idx
            break

    if sep_idx is None:
        header_lines: list[str] = []
        body_lines = lines[:]
    else:
        header_lines = lines[:sep_idx]
        body_lines = lines[sep_idx + 1 :]

    # Determine number of columns from the first row
    def _cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    ncols = 0
    if header_lines:
        ncols = len(_cells(header_lines[0]))
    elif body_lines:
        ncols = len(_cells(body_lines[0]))
    if ncols == 0:
        return ""

    colspec = "l" * ncols
    parts = [f"\\begin{{tabular}}{{{colspec}}}", "\\toprule"]

    for hline in header_lines:
        cells = [_process_inline(c) for c in _cells(hline)]
        parts.append(" & ".join(cells) + " \\\\")

    if header_lines:
        parts.append("\\midrule")

    for bline in body_lines:
        cells = [_process_inline(c) for c in _cells(bline)]
        parts.append(" & ".join(cells) + " \\\\")

    parts.append("\\bottomrule")
    parts.append("\\end{tabular}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LaTeX document template
# ---------------------------------------------------------------------------

_LATEX_TEMPLATE = r"""\documentclass[11pt,a4paper]{{article}}

% --- Page setup ---
\usepackage[a4paper, left=25mm, right=25mm, top=30mm, bottom=25mm]{{geometry}}
\usepackage{{fancyhdr}}
\usepackage{{lastpage}}
\usepackage{{titlesec}}
\usepackage{{hyperref}}
\usepackage{{xcolor}}
\usepackage{{fontspec}}
\usepackage{{listings}}
\usepackage{{booktabs}}
\usepackage{{enumitem}}
\usepackage{{parskip}}

% --- Fonts: Linux Libertine (modern professional) ---
\setmainfont{{Linux Libertine O}}
\setsansfont{{Linux Biolinum O}}
\setmonofont{{Inconsolata}}

% --- Colors ---
\definecolor{{headingcolor}}{{RGB}}{{30,30,30}}
\definecolor{{linkcolor}}{{RGB}}{{44,90,160}}
\definecolor{{codebg}}{{RGB}}{{245,245,245}}

% --- Headers/Footers ---
\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[L]{{\small\itshape\color{{gray}} \reporttitle}}
\fancyhead[R]{{\small\color{{gray}} \today}}
\fancyfoot[C]{{\small\color{{gray}} \thepage{{}} of \pageref{{LastPage}}}}
\renewcommand{{\headrulewidth}}{{0.4pt}}
\renewcommand{{\footrulewidth}}{{0pt}}
\fancypagestyle{{plain}}{{
  \fancyhf{{}}
  \fancyfoot[C]{{\small\color{{gray}} \thepage{{}} of \pageref{{LastPage}}}}
}}

% --- Section formatting ---
\titleformat{{\section}}{{\Large\bfseries\sffamily\color{{headingcolor}}}}{{}}{{0em}}{{}}[\vspace{{-0.5em}}]
\titleformat{{\subsection}}{{\large\bfseries\sffamily\color{{headingcolor}}}}{{}}{{0em}}{{}}[\vspace{{-0.5em}}]
\titleformat{{\subsubsection}}{{\normalsize\bfseries\sffamily\color{{headingcolor}}}}{{}}{{0em}}{{}}[\vspace{{-0.5em}}]

% --- Code blocks ---
\lstset{{
  basicstyle=\small\ttfamily,
  backgroundcolor=\color{{codebg}},
  frame=single,
  framerule=0pt,
  framesep=8pt,
  rulecolor=\color{{lightgray}},
  breaklines=true,
  showstringspaces=false,
  aboveskip=10pt,
  belowskip=10pt,
  xleftmargin=0pt,
  framexleftmargin=0pt,
}}

% --- Links ---
\hypersetup{{
  colorlinks=true,
  linkcolor=linkcolor,
  urlcolor=linkcolor,
  citecolor=linkcolor,
}}

% --- Report title command ---
\newcommand{{\reporttitle}}{{TITLE}}

% --- Title page ---
\newcommand{{\maketitlepage}}[2]{{
  \begin{{titlepage}}
    \centering
    \vspace*{{6cm}}
    {{\Huge\bfseries\sffamily #1\par}}
    \vspace{{1.5cm}}
    {{\Large\color{{gray}} #2\par}}
    \vspace{{3cm}}
    {{\normalsize\color{{gray}} Generated by Workbench\par}}
    \vfill
  \end{{titlepage}}
}}

\begin{{document}}

\renewcommand{{\reporttitle}}{{{TITLE}}}

\maketitlepage{{\reporttitle}}{{\today}}

{BODY}

\end{{document}}
"""


def _build_latex_document(content: str, title: str) -> str:
    """Convert markdown content into a complete LaTeX document string.

    Processes paragraph-by-paragraph with special handling for code blocks,
    tables, lists, blockquotes, headings, and horizontal rules.
    """
    lines = content.split("\n")
    parts: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # ---- Code block ----
        if line.startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            parts.append("\\begin{lstlisting}")
            parts.extend(code_lines)
            parts.append("\\end{lstlisting}")
            parts.append("")
            continue

        # ---- Empty line ----
        if not line.strip():
            i += 1
            continue

        # ---- Horizontal rule ----
        if re.match(r"^---+$", line.strip()):
            parts.append("\\vspace{1em}\\hrule\\vspace{1em}")
            parts.append("")
            i += 1
            continue

        # ---- Heading (# ## ###) ----
        h_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if h_match:
            level = len(h_match.group(1))
            text = _process_inline(h_match.group(2))
            cmd = {1: "section", 2: "subsection", 3: "subsubsection"}[level]
            parts.append(f"\\{cmd}{{{text}}}")
            parts.append("")
            i += 1
            continue

        # ---- Blockquote ----
        bq_match = re.match(r"^>\s+(.*)$", line)
        if bq_match:
            bq_text: list[str] = []
            while i < len(lines):
                m = re.match(r"^>\s*(.*)$", lines[i])
                if not m:
                    break
                bq_text.append(m.group(1))
                i += 1
            text = _process_inline(" ".join(bq_text))
            parts.append(f"\\begin{{quote}}\\small\\itshape {text}\\end{{quote}}")
            parts.append("")
            continue

        # ---- Table ----
        if re.match(r"^\|.+\|$", line.strip()):
            tbl_lines: list[str] = []
            while i < len(lines) and re.match(r"^\|.+\|$", lines[i].strip()):
                tbl_lines.append(lines[i])
                i += 1
            parts.append(_convert_table(tbl_lines))
            parts.append("")
            continue

        # ---- Unordered list ----
        ul_match = re.match(r"^[-*]\s+(.+)$", line)
        if ul_match:
            items: list[str] = []
            while i < len(lines):
                m = re.match(r"^[-*]\s+(.+)$", lines[i])
                if not m:
                    break
                items.append(f"\\item {_process_inline(m.group(1))}")
                i += 1
            parts.append("\\begin{itemize}")
            parts.extend(items)
            parts.append("\\end{itemize}")
            parts.append("")
            continue

        # ---- Ordered list ----
        ol_match = re.match(r"^\d+\.\s+(.+)$", line)
        if ol_match:
            items = []
            while i < len(lines):
                m = re.match(r"^\d+\.\s+(.+)$", lines[i])
                if not m:
                    break
                items.append(f"\\item {_process_inline(m.group(1))}")
                i += 1
            parts.append("\\begin{enumerate}")
            parts.extend(items)
            parts.append("\\end{enumerate}")
            parts.append("")
            continue

        # ---- Regular paragraph ----
        para: list[str] = []
        while i < len(lines) and lines[i].strip():
            para.append(lines[i])
            i += 1
        text = _process_inline(" ".join(para))
        if text.strip():
            parts.append(text)
            parts.append("")

    body = "\n".join(parts).strip()
    return _LATEX_TEMPLATE.replace("{TITLE}", _escape_latex(title)).replace(
        "{BODY}", body
    )
