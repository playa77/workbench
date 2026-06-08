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
