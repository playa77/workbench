"""Output formatting and console UI."""

from presearch.output.console import ConsoleUI
from presearch.output.markdown import ensure_citations, format_source_list, save_report
from presearch.output.protocol import UIProtocol

__all__ = ["ConsoleUI", "UIProtocol", "ensure_citations", "format_source_list", "save_report"]
