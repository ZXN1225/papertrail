"""Supported, explicitly versioned PDF parser lineage identifiers."""

from __future__ import annotations

import re
from typing import Any

_SUPPORTED_PDF_PARSER_VERSION = re.compile(
    r"(?:pdfplumber-layout-v\d+|mineru-[0-9][0-9A-Za-z.+-]*-papertrail-v\d+)"
)


def is_supported_pdf_parser_version(value: Any) -> bool:
    """Return whether a PDF parser version belongs to a versioned PaperTrail adapter."""
    return isinstance(value, str) and _SUPPORTED_PDF_PARSER_VERSION.fullmatch(value) is not None
