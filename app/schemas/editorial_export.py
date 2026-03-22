from __future__ import annotations

from pydantic import BaseModel


class EditorialExportPolicy(BaseModel):
    use_rewrite_by_default: bool = True
    max_text_length: int = 240
    duplicate_window_hours: int = 72
    max_line_breaks: int = 6
