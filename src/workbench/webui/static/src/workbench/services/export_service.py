"""Markdown-to-HTML conversion and HTML/PDF export with multi-template LaTeX.

Provides:
    - markdown_to_html(content, title): Convert markdown to a full styled HTML document.
    - generate_pdf_print_page(content, title): Return an HTML page that auto-opens the
      browser print dialog (for saving as PDF).
    - list_templates(): Return metadata for all available PDF export templates.
    - markdown_to_pdf_bytes(content, title, template): Generate a PDF using the selected
      LaTeX template (compiled via tectonic).

Templates:
    professional  — Default: clean single-column, TOC, accent color, numbered sections
    tufte         — Tufte-inspired: wide margins, small caps, generous whitespace
    classic       — Thesis-style: elegant chapter-like section openings, small caps headers
    modern        — Sans-serif institutional: color blocks, clean contemporary feel
    compact       — Two-column dense technical layout for maximum information density
    manuscript    — Kaobook-inspired: wide outer margins for notes and annotations
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


def _tie_heading(text: str) -> str:
    """Prevent line breaks at commas in headings and titles.

    In LaTeX, a comma followed by a space is a valid line-breaking point.
    This makes headings like "Widersprüche, Debatten" wrap ugly: the comma
    ends up isolated at the end of a line.  Replacing ", " with ",~" ties
    the comma to the following word via a non-breaking space (~), so the
    comma never sits alone at a line boundary.
    """
    return text.replace(", ", ",~")


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
# LaTeX Template System
# ---------------------------------------------------------------------------

# Shared font configuration used by all templates.
# Uses Linux Libertine (serif), Biolinum (sans), Inconsolata (mono) —
# installed via fonts-linuxlibertine and fonts-inconsolata (Debian/Docker).
_FONT_BLOCK = r"""
% --- Fonts: Linux Libertine + Biolinum + Inconsolata ---
\usepackage{fontspec}
\setmainfont[
  Path=/usr/share/fonts/opentype/linux-libertine/,
  Extension=.otf,
  UprightFont=LinLibertine_R,
  BoldFont=LinLibertine_RB,
  ItalicFont=LinLibertine_RI,
  BoldItalicFont=LinLibertine_RBI
]{LinLibertine_R}
\setsansfont[
  Path=/usr/share/fonts/opentype/linux-libertine/,
  Extension=.otf,
  UprightFont=LinBiolinum_R,
  BoldFont=LinBiolinum_RB,
  ItalicFont=LinBiolinum_RI
]{LinBiolinum_R}
\setmonofont[
  Path=/usr/share/fonts/truetype/inconsolata/,
  Extension=.otf,
  UprightFont=Inconsolata
]{Inconsolata}
"""


_TEMPLATES: dict[str, dict] = {
    # ── Professional (default, improved) ────────────────────────────────
    "professional": {
        "name": "Professional",
        "description": "Clean single-column, TOC, accent color, numbered sections, professional layout.",
        "document_pre": r"""\documentclass[11pt,a4paper]{article}

% --- Packages ---
\usepackage[a4paper, left=25mm, right=25mm, top=30mm, bottom=25mm]{geometry}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{titlesec}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{listings}
\usepackage{booktabs}
\usepackage{enumitem}
\usepackage{parskip}
\usepackage{microtype}
\usepackage{tcolorbox}
\tcbuselibrary{skins, breakable}
""" + _FONT_BLOCK + r"""
% --- Colors ---
\definecolor{accent}{RGB}{44,90,160}
\definecolor{headingcolor}{RGB}{25,25,30}
\definecolor{linkcolor}{RGB}{44,90,160}
\definecolor{codebg}{RGB}{245,245,245}

% --- Section formatting ---
\titleformat{\section}
  {\Large\bfseries\sffamily\color{headingcolor}}
  {\thesection}{1em}{}[\vspace{-0.5em}]
\titleformat{\subsection}
  {\large\bfseries\sffamily\color{headingcolor}}
  {\thesubsection}{1em}{}[\vspace{-0.5em}]
\titleformat{\subsubsection}
  {\normalsize\bfseries\sffamily\color{headingcolor}}
  {\thesubsubsection}{1em}{}[\vspace{-0.5em}]

% --- Headers/Footers ---
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\itshape\color{gray}\leftmark}
\fancyhead[R]{\small\color{gray}\today}
\fancyfoot[C]{\small\color{gray}\thepage{} of \pageref{LastPage}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0pt}
\fancypagestyle{plain}{
  \fancyhf{}
  \fancyfoot[C]{\small\color{gray}\thepage{} of \pageref{LastPage}}
}

% --- Exec Summary box ---
\newtcolorbox{execsummarybox}{
  colback=accent!7,
  colframe=accent!40,
  leftrule=3mm,
  arc=0mm,
  boxrule=0pt,
  left=10pt,
  right=8pt,
  top=8pt,
  bottom=8pt,
  before skip=18pt,
  after skip=18pt,
  breakable,
}

% --- Code blocks ---
\lstset{
  basicstyle=\small\ttfamily,
  backgroundcolor=\color{codebg},
  frame=single,
  framerule=0pt,
  framesep=8pt,
  rulecolor=\color{lightgray},
  breaklines=true,
  showstringspaces=false,
  aboveskip=10pt,
  belowskip=10pt,
  xleftmargin=0pt,
  framexleftmargin=0pt,
}

% --- Links ---
\hypersetup{
  colorlinks=true,
  linkcolor=linkcolor,
  urlcolor=linkcolor,
  citecolor=linkcolor,
  bookmarksnumbered=true,
  pdfpagemode=UseOutlines,
}

% --- Report metadata ---
\newcommand{\reporttitle}{Workbench Report}

% --- Title page ---
\newcommand{\maketitlepage}[2]{
  \begin{titlepage}
    \centering
    \vspace*{6cm}
    {\Huge\bfseries\sffamily #1\par}
    \vspace{1.5cm}
    {\Large\color{gray} #2\par}
    \vspace{3cm}
    {\normalsize\color{gray} Generated by Workbench\par}
    \vfill
  \end{titlepage}
}

\begin{document}

\renewcommand{\reporttitle}{{TITLE}}

\maketitlepage{\reporttitle}{\today}

\tableofcontents
\newpage

{BODY}

\end{document}
""",
    },

    # ── Tufte ────────────────────────────────────────────────────────────
    "tufte": {
        "name": "Tufte",
        "description": "Tufte-inspired elegance: wide margins, small caps, generous whitespace, margin notes.",
        "document_pre": r"""\documentclass[11pt,a4paper,twoside]{article}

% --- Packages ---
\usepackage[a4paper, left=25mm, right=55mm, top=30mm, bottom=25mm]{geometry}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{titlesec}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{listings}
\usepackage{booktabs}
\usepackage{enumitem}
\usepackage{parskip}
\usepackage{microtype}
\usepackage{marginnote}
\usepackage{tcolorbox}
\tcbuselibrary{skins, breakable}
""" + _FONT_BLOCK + r"""
% --- Colors ---
\definecolor{accent}{RGB}{139,0,0}
\definecolor{headingcolor}{RGB}{30,30,30}
\definecolor{linkcolor}{RGB}{139,0,0}
\definecolor{codebg}{RGB}{250,250,250}
\definecolor{tuftebg}{RGB}{255,252,245}

% --- Page background ---
\pagecolor{tuftebg}

% --- Section formatting (Tufte: small caps, understated) ---
\titleformat{\section}
  {\Large\scshape\color{headingcolor}}
  {\thesection}{1em}{}[\vspace{-0.5em}]
\titleformat{\subsection}
  {\large\scshape\color{headingcolor}}
  {\thesubsection}{1em}{}[\vspace{-0.5em}]
\titleformat{\subsubsection}
  {\normalsize\scshape\itshape\color{headingcolor}}
  {\thesubsubsection}{1em}{}[\vspace{-0.5em}]

% --- Headers/Footers (minimal) ---
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE]{\small\scshape\color{gray}\leftmark}
\fancyhead[RO]{\small\scshape\color{gray}\rightmark}
\fancyfoot[C]{\small\color{gray}\thepage}
\renewcommand{\headrulewidth}{0.3pt}
\renewcommand{\footrulewidth}{0pt}
\fancypagestyle{plain}{
  \fancyhf{}
  \fancyfoot[C]{\small\color{gray}\thepage}
}

% --- Exec Summary box (Tufte style: subtle) ---
\newtcolorbox{execsummarybox}{
  colback=black!3,
  colframe=black!15,
  leftrule=2mm,
  arc=0mm,
  boxrule=0pt,
  left=10pt,
  right=8pt,
  top=8pt,
  bottom=8pt,
  before skip=18pt,
  after skip=18pt,
  breakable,
}

% --- Code blocks ---
\lstset{
  basicstyle=\small\ttfamily,
  backgroundcolor=\color{codebg},
  frame=single,
  framerule=0pt,
  framesep=8pt,
  rulecolor=\color{lightgray},
  breaklines=true,
  showstringspaces=false,
  aboveskip=10pt,
  belowskip=10pt,
  xleftmargin=0pt,
  framexleftmargin=0pt,
}

% --- Links ---
\hypersetup{
  colorlinks=true,
  linkcolor=linkcolor,
  urlcolor=linkcolor,
  citecolor=linkcolor,
}

% --- Report metadata ---
\newcommand{\reporttitle}{Workbench Report}

% --- Title page (Tufte: generous whitespace, restrained) ---
\newcommand{\maketitlepage}[2]{
  \thispagestyle{empty}
  \vspace*{8cm}
  \begin{fullwidth}
  {\Huge\scshape\color{headingcolor}#1\par}
  \vspace{2cm}
  {\Large\itshape\color{gray}#2\par}
  \vspace{5cm}
  {\normalsize\color{gray}Workbench Research Report\par}
  \end{fullwidth}
  \newpage
}

% --- Fullwidth environment (for title page) ---
\newenvironment{fullwidth}
  {\begin{adjustwidth}{}{-30mm}}
  {\end{adjustwidth}}
\usepackage{changepage}

\begin{document}

\renewcommand{\reporttitle}{{TITLE}}

\maketitlepage{\reporttitle}{\today}

{BODY}

\end{document}
""",
    },

    # ── Classic ──────────────────────────────────────────────────────────
    "classic": {
        "name": "Classic",
        "description": "Thesis-style: elegant chapter-like openings, small caps running heads, Bringhurst proportions.",
        "document_pre": r"""\documentclass[11pt,a4paper,twoside]{article}

% --- Packages ---
\usepackage[a4paper, left=30mm, right=30mm, top=35mm, bottom=30mm]{geometry}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{titlesec}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{listings}
\usepackage{booktabs}
\usepackage{enumitem}
\usepackage{parskip}
\usepackage{microtype}
\usepackage{setspace}
\usepackage{tcolorbox}
\tcbuselibrary{skins, breakable}
\usepackage{lettrine}
""" + _FONT_BLOCK + r"""
% --- Typography ---
\onehalfspacing
\microtypesetup{protrusion=true, expansion=true, tracking=smallcaps, letterspace=50}

% --- Colors ---
\definecolor{accent}{RGB}{70,50,30}
\definecolor{headingcolor}{RGB}{30,25,20}
\definecolor{linkcolor}{RGB}{70,50,30}
\definecolor{codebg}{RGB}{248,245,240}

% --- Section formatting (Classic: serif headings, elegant) ---
\titleformat{\section}
  {\LARGE\rmfamily\scshape\color{headingcolor}}
  {\thesection}{1em}{}[\vspace{-0.5em}{\color{accent}\hrule height 0.5pt}\vspace{0.5em}]
\titleformat{\subsection}
  {\Large\rmfamily\itshape\color{headingcolor}}
  {\thesubsection}{1em}{}[\vspace{-0.3em}]
\titleformat{\subsubsection}
  {\large\rmfamily\scshape\color{headingcolor}}
  {\thesubsubsection}{1em}{}[\vspace{-0.3em}]

% --- Headers/Footers ---
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE]{\small\scshape\color{gray}\leftmark}
\fancyhead[RO]{\small\scshape\color{gray}\rightmark}
\fancyfoot[C]{\small\scshape\color{gray}\thepage}
\renewcommand{\headrulewidth}{0.3pt}
\renewcommand{\footrulewidth}{0pt}
\fancypagestyle{plain}{
  \fancyhf{}
  \fancyfoot[C]{\small\scshape\color{gray}\thepage}
}

% --- Exec Summary box ---
\newtcolorbox{execsummarybox}{
  colback=accent!5,
  colframe=accent!30,
  leftrule=2mm,
  arc=0mm,
  boxrule=0pt,
  left=12pt,
  right=8pt,
  top=10pt,
  bottom=10pt,
  before skip=20pt,
  after skip=20pt,
  breakable,
}

% --- Code blocks ---
\lstset{
  basicstyle=\small\ttfamily,
  backgroundcolor=\color{codebg},
  frame=single,
  framerule=0pt,
  framesep=8pt,
  rulecolor=\color{lightgray},
  breaklines=true,
  showstringspaces=false,
  aboveskip=10pt,
  belowskip=10pt,
  xleftmargin=0pt,
  framexleftmargin=0pt,
}

% --- Links ---
\hypersetup{
  colorlinks=true,
  linkcolor=linkcolor,
  urlcolor=linkcolor,
  citecolor=linkcolor,
}

% --- Report metadata ---
\newcommand{\reporttitle}{Workbench Report}

% --- Title page ---
\newcommand{\maketitlepage}[2]{
  \begin{titlepage}
    \centering
    \vspace*{5cm}
    {\Huge\rmfamily\scshape\color{headingcolor}#1\par}
    \vspace{2cm}
    {\Large\itshape\color{gray}#2\par}
    \vspace{4cm}
    {\small\scshape\color{gray}Workbench Research\par}
    \vfill
    {\footnotesize\color{gray}Typeset with \LaTeX\par}
  \end{titlepage}
}

\begin{document}

\renewcommand{\reporttitle}{{TITLE}}

\maketitlepage{\reporttitle}{\today}

\tableofcontents
\newpage

{BODY}

\end{document}
""",
    },

    # ── Modern ───────────────────────────────────────────────────────────
    "modern": {
        "name": "Modern",
        "description": "Sans-serif institutional: color-accented headings, clean blocks, contemporary feel.",
        "document_pre": r"""\documentclass[11pt,a4paper]{article}

% --- Packages ---
\usepackage[a4paper, left=22mm, right=22mm, top=30mm, bottom=22mm]{geometry}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{titlesec}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{listings}
\usepackage{booktabs}
\usepackage{enumitem}
\usepackage{parskip}
\usepackage{microtype}
\usepackage{tcolorbox}
\tcbuselibrary{skins, breakable}
""" + _FONT_BLOCK + r"""
% --- Colors (McKinsey/Deutsche Bank inspired) ---
\definecolor{accent}{RGB}{0,70,100}
\definecolor{accentlight}{RGB}{230,242,250}
\definecolor{headingcolor}{RGB}{0,55,80}
\definecolor{linkcolor}{RGB}{0,70,100}
\definecolor{codebg}{RGB}{240,245,248}
\definecolor{bodycolor}{RGB}{40,40,45}

% --- Use sans-serif for body (institutional look) ---
\renewcommand{\familydefault}{\sfdefault}

% --- Section formatting (Modern: bold sans-serif with color block) ---
\titleformat{\section}
  {\LARGE\bfseries\color{white}}
  {}
  {0em}
  {\colorbox{accent}{\parbox{\dimexpr\textwidth-20pt\relax}{\strut\thesection\hspace{1em}#1}}}
  [\vspace{0.5em}]
\titleformat{\subsection}
  {\Large\bfseries\color{headingcolor}}
  {\thesubsection}{1em}{}[\vspace{-0.3em}]
\titleformat{\subsubsection}
  {\large\bfseries\color{headingcolor}}
  {\thesubsubsection}{1em}{}[\vspace{-0.3em}]

% --- Headers/Footers ---
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\color{gray}\leftmark}
\fancyhead[R]{\small\color{gray}\today}
\fancyfoot[C]{\small\color{gray}\thepage{} of \pageref{LastPage}}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0pt}
\fancypagestyle{plain}{
  \fancyhf{}
  \fancyfoot[C]{\small\color{gray}\thepage{} of \pageref{LastPage}}
}

% --- Exec Summary box ---
\newtcolorbox{execsummarybox}{
  colback=accentlight,
  colframe=accent,
  leftrule=4mm,
  arc=0mm,
  boxrule=0pt,
  left=10pt,
  right=8pt,
  top=8pt,
  bottom=8pt,
  before skip=18pt,
  after skip=18pt,
  breakable,
}

% --- Code blocks ---
\lstset{
  basicstyle=\small\ttfamily,
  backgroundcolor=\color{codebg},
  frame=single,
  framerule=0pt,
  framesep=8pt,
  rulecolor=\color{lightgray},
  breaklines=true,
  showstringspaces=false,
  aboveskip=10pt,
  belowskip=10pt,
  xleftmargin=0pt,
  framexleftmargin=0pt,
}

% --- Links ---
\hypersetup{
  colorlinks=true,
  linkcolor=linkcolor,
  urlcolor=linkcolor,
  citecolor=linkcolor,
  bookmarksnumbered=true,
  pdfpagemode=UseOutlines,
}

% --- Report metadata ---
\newcommand{\reporttitle}{Workbench Report}

% --- Title page ---
\newcommand{\maketitlepage}[2]{
  \begin{titlepage}
    \vspace*{4cm}
    \begin{center}
    \colorbox{accent}{\parbox{0.9\textwidth}{\centering\vspace{2cm}
      {\Huge\bfseries\color{white}#1\par}
      \vspace{1cm}
      {\Large\color{white}#2\par}
      \vspace{2cm}
    }}
    \end{center}
    \vspace{3cm}
    {\centering\normalsize\color{gray}Workbench Research Report\par}
    \vfill
  \end{titlepage}
}

\begin{document}

\renewcommand{\reporttitle}{{TITLE}}

\maketitlepage{\reporttitle}{\today}

\tableofcontents
\newpage

{BODY}

\end{document}
""",
    },

    # ── Compact ──────────────────────────────────────────────────────────
    "compact": {
        "name": "Compact",
        "description": "Two-column dense layout: small type, efficient spacing, maximum information density.",
        "document_pre": r"""\documentclass[9pt,a4paper,twocolumn]{extarticle}

% --- Packages ---
\usepackage[a4paper, left=18mm, right=18mm, top=22mm, bottom=18mm, columnsep=5mm]{geometry}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{titlesec}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{listings}
\usepackage{booktabs}
\usepackage{enumitem}
\usepackage{parskip}
\usepackage{microtype}
\usepackage{tcolorbox}
\tcbuselibrary{skins, breakable}
""" + _FONT_BLOCK + r"""
% --- Colors ---
\definecolor{accent}{RGB}{0,60,110}
\definecolor{headingcolor}{RGB}{20,20,25}
\definecolor{linkcolor}{RGB}{0,60,110}
\definecolor{codebg}{RGB}{245,245,248}

% --- Compact spacing ---
\setlength{\parindent}{0pt}
\setlength{\parskip}{2pt plus 1pt minus 1pt}
\setlist{nosep, leftmargin=*}

% --- Section formatting (compact) ---
\titleformat{\section}
  {\normalsize\bfseries\sffamily\color{headingcolor}}
  {\thesection}{0.5em}{}[\vspace{-0.3em}]
\titlespacing{\section}{0pt}{8pt}{2pt}
\titleformat{\subsection}
  {\small\bfseries\sffamily\color{headingcolor}}
  {\thesubsection}{0.5em}{}[\vspace{-0.2em}]
\titlespacing{\subsection}{0pt}{6pt}{1pt}
\titleformat{\subsubsection}
  {\small\bfseries\sffamily\color{headingcolor}}
  {\thesubsubsection}{0.5em}{}[\vspace{-0.2em}]
\titlespacing{\subsubsection}{0pt}{4pt}{1pt}

% --- Code (compact) ---
\lstset{
  basicstyle=\footnotesize\ttfamily,
  backgroundcolor=\color{codebg},
  frame=single,
  framerule=0pt,
  framesep=4pt,
  rulecolor=\color{lightgray},
  breaklines=true,
  showstringspaces=false,
  aboveskip=4pt,
  belowskip=4pt,
  xleftmargin=0pt,
  framexleftmargin=0pt,
}

% --- Headers/Footers (minimal) ---
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\tiny\color{gray}\leftmark}
\fancyhead[R]{\tiny\color{gray}\today}
\fancyfoot[C]{\tiny\color{gray}\thepage}
\renewcommand{\headrulewidth}{0.2pt}
\renewcommand{\footrulewidth}{0pt}
\fancypagestyle{plain}{
  \fancyhf{}
  \fancyfoot[C]{\tiny\color{gray}\thepage}
}

% --- Exec Summary (compact: full-width at top) ---
\newtcolorbox{execsummarybox}{
  colback=accent!5,
  colframe=accent!30,
  leftrule=2mm,
  arc=0mm,
  boxrule=0pt,
  left=8pt,
  right=6pt,
  top=6pt,
  bottom=6pt,
  before skip=10pt,
  after skip=10pt,
  breakable,
}

% --- Links ---
\hypersetup{
  colorlinks=true,
  linkcolor=linkcolor,
  urlcolor=linkcolor,
  citecolor=linkcolor,
}

% --- Title ---
\newcommand{\reporttitle}{Workbench Report}

% --- Title block (compact: no separate page, just a header block) ---
\newcommand{\maketitleblock}[2]{
  \twocolumn[
    \begin{@twocolumnfalse}
    \hrule
    \vspace{10pt}
    {\LARGE\bfseries\sffamily\color{headingcolor}#1\par}
    \vspace{6pt}
    {\large\color{gray}#2\hfill Workbench Research\par}
    \vspace{10pt}
    \hrule
    \vspace{16pt}
    \end{@twocolumnfalse}
  ]
}

\begin{document}

\renewcommand{\reporttitle}{{TITLE}}

\maketitleblock{\reporttitle}{\today}

{BODY}

\end{document}
""",
    },

    # ── Manuscript ───────────────────────────────────────────────────────
    "manuscript": {
        "name": "Manuscript",
        "description": "Kaobook-inspired: wide outer margins for notes, generous whitespace, clean typography.",
        "document_pre": r"""\documentclass[11pt,a4paper,twoside]{article}

% --- Packages ---
\usepackage[a4paper, left=25mm, right=55mm, top=30mm, bottom=30mm]{geometry}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{titlesec}
\usepackage{hyperref}
\usepackage{xcolor}
\usepackage{listings}
\usepackage{booktabs}
\usepackage{enumitem}
\usepackage{parskip}
\usepackage{microtype}
\usepackage{marginnote}
\usepackage{tcolorbox}
\tcbuselibrary{skins, breakable}
""" + _FONT_BLOCK + r"""
% --- Colors ---
\definecolor{accent}{RGB}{55,65,81}
\definecolor{headingcolor}{RGB}{20,25,30}
\definecolor{linkcolor}{RGB}{55,65,81}
\definecolor{codebg}{RGB}{248,248,250}
\definecolor{marginbg}{RGB}{250,250,252}

% --- Section formatting (Manuscript: understated, elegant) ---
\titleformat{\section}
  {\LARGE\rmfamily\itshape\color{headingcolor}}
  {\thesection}{1em}{}[\vspace{-0.5em}]
\titleformat{\subsection}
  {\Large\rmfamily\color{headingcolor}}
  {\thesubsection}{1em}{}[\vspace{-0.3em}]
\titleformat{\subsubsection}
  {\large\rmfamily\scshape\color{headingcolor}}
  {\thesubsubsection}{1em}{}[\vspace{-0.3em}]

% --- Headers/Footers ---
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE]{\small\itshape\color{gray}\leftmark}
\fancyhead[RO]{\small\itshape\color{gray}\rightmark}
\fancyfoot[C]{\small\color{gray}\thepage}
\renewcommand{\headrulewidth}{0.3pt}
\renewcommand{\footrulewidth}{0pt}
\fancypagestyle{plain}{
  \fancyhf{}
  \fancyfoot[C]{\small\color{gray}\thepage}
}

% --- Exec Summary box ---
\newtcolorbox{execsummarybox}{
  colback=black!2,
  colframe=black!10,
  leftrule=2mm,
  arc=0mm,
  boxrule=0pt,
  left=10pt,
  right=8pt,
  top=8pt,
  bottom=8pt,
  before skip=18pt,
  after skip=18pt,
  breakable,
}

% --- Code blocks ---
\lstset{
  basicstyle=\small\ttfamily,
  backgroundcolor=\color{codebg},
  frame=single,
  framerule=0pt,
  framesep=8pt,
  rulecolor=\color{lightgray},
  breaklines=true,
  showstringspaces=false,
  aboveskip=10pt,
  belowskip=10pt,
  xleftmargin=0pt,
  framexleftmargin=0pt,
}

% --- Links ---
\hypersetup{
  colorlinks=true,
  linkcolor=linkcolor,
  urlcolor=linkcolor,
  citecolor=linkcolor,
}

% --- Report metadata ---
\newcommand{\reporttitle}{Workbench Report}

% --- Title page ---
\newcommand{\maketitlepage}[2]{
  \begin{titlepage}
    \centering
    \vspace*{7cm}
    {\Huge\rmfamily\itshape\color{headingcolor}#1\par}
    \vspace{2cm}
    {\Large\color{gray}#2\par}
    \vspace{5cm}
    {\small\color{gray}Workbench Research\par}
    \vfill
  \end{titlepage}
}

\begin{document}

\renewcommand{\reporttitle}{{TITLE}}

\maketitlepage{\reporttitle}{\today}

{BODY}

\end{document}
""",
    },
}


def list_templates() -> list[dict]:
    """Return metadata for all available PDF export templates.

    Returns a list of dicts with keys: key, name, description.
    The first entry is the default (professional).
    """
    return [
        {"key": key, "name": tmpl["name"], "description": tmpl["description"]}
        for key, tmpl in _TEMPLATES.items()
    ]


# ---------------------------------------------------------------------------
# LaTeX document assembly
# ---------------------------------------------------------------------------

def _build_latex_document(content: str, title: str, template_key: str = "professional") -> str:
    """Convert markdown content into a complete LaTeX document string.

    Processes paragraph-by-paragraph with special handling for code blocks,
    tables, lists, blockquotes, headings, and horizontal rules.

    Smart section handling: recognizes ``Executive Summary`` / ``Zusammenfassung``
    headings and wraps their content in a tinted box; ``Sources`` / ``Quellen``
    sections are rendered in smaller type with hanging indent.
    """
    template = _TEMPLATES.get(template_key, _TEMPLATES["professional"])

    # ---- Parse content into structured blocks ----
    class _BlockState:
        in_exec_summary: bool = False
        in_sources: bool = False

    state = _BlockState()

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
            # Close any open semantic block
            if state.in_exec_summary:
                parts.append("\\end{execsummarybox}")
                parts.append("")
                state.in_exec_summary = False
            if state.in_sources:
                parts.append("\\end{small}")
                parts.append("")
                state.in_sources = False

            level = len(h_match.group(1))
            raw_text = h_match.group(2).strip()
            text = _process_inline(raw_text)
            text = _tie_heading(text)

            # Smart section detection
            text_lower = raw_text.lower()
            exec_keywords = {"executive summary", "zusammenfassung", "executive summary:"}
            sources_keywords = {"sources", "quellen", "references", "bibliography"}

            if text_lower.rstrip(":") in exec_keywords and level == 2:
                state.in_exec_summary = True
                parts.append(f"\\section*{{{text}}}")
                parts.append("\\begin{execsummarybox}")
                parts.append("")
            elif text_lower.rstrip(":") in sources_keywords and level >= 2:
                state.in_sources = True
                parts.append("\\newpage")
                parts.append(f"\\section*{{{text}}}")
                parts.append("\\begin{small}")
                parts.append("\\setlength{\\parindent}{0pt}")
                parts.append("\\setlength{\\leftskip}{2em}")
                parts.append("\\setlength{\\parskip}{3pt}")
                parts.append("")
            else:
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

    # Close any remaining semantic block
    if state.in_exec_summary:
        parts.append("\\end{execsummarybox}")
        parts.append("")
    if state.in_sources:
        parts.append("\\end{small}")
        parts.append("")

    body = "\n".join(parts).strip()
    safe_title = _tie_heading(_escape_latex(title))

    # Assemble: insert title + body into template
    doc = template["document_pre"]
    doc = doc.replace("{TITLE}", safe_title)
    doc = doc.replace("{BODY}", body)
    return doc


def markdown_to_pdf_bytes(content: str, title: str = "Report", template: str = "professional") -> bytes:
    """Generate a professional PDF from markdown content using tectonic (LaTeX engine).

    Converts markdown to a LaTeX document using the selected template,
    compiles it with tectonic (which auto-downloads missing LaTeX packages
    from CTAN), and returns the raw PDF bytes.

    Args:
        content: Markdown source text.
        title: Report title (used on the title page and in PDF metadata).
        template: Template key (one of: professional, tufte, classic, modern, compact, manuscript).
                  Defaults to ``"professional"``.  Falls back to ``"professional"`` if the key
                  is unknown.
    """
    import os
    import subprocess
    import tempfile

    latex_source = _build_latex_document(content, title, template)

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
