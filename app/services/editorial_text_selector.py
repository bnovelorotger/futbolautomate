from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.exceptions import InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.services.editorial_formatter import EditorialFormatterService


def _usable_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


@dataclass(slots=True)
class EditorialTextSelection:
    text: str
    source: str
    has_rewrite: bool
    has_formatted: bool


class EditorialTextSelectorService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.formatter = EditorialFormatterService(session)

    def select_text(
        self,
        candidate: ContentCandidate,
        *,
        prefer_rewrite: bool = True,
    ) -> EditorialTextSelection:
        rewrite_text = _usable_text(candidate.rewritten_text)
        draft_text = _usable_text(candidate.text_draft)
        if draft_text is None:
            raise InvalidStateTransitionError(f"El candidato {candidate.id} no tiene text_draft utilizable")
        layers = self.formatter.build_text_layers_for_candidate(candidate)
        formatted_text = _usable_text(candidate.formatted_text) or _usable_text(layers.formatted_text)
        enriched_text = _usable_text(layers.enriched_text)
        viral_formatted_text = _usable_text(layers.viral_formatted_text)
        if prefer_rewrite and rewrite_text is not None:
            return EditorialTextSelection(
                text=rewrite_text,
                source="rewritten_text",
                has_rewrite=True,
                has_formatted=formatted_text is not None,
            )
        if not prefer_rewrite:
            return EditorialTextSelection(
                text=draft_text,
                source="text_draft",
                has_rewrite=rewrite_text is not None,
                has_formatted=formatted_text is not None,
            )
        if viral_formatted_text is not None and viral_formatted_text != (enriched_text or formatted_text or draft_text):
            return EditorialTextSelection(
                text=viral_formatted_text,
                source="viral_formatted_text",
                has_rewrite=rewrite_text is not None,
                has_formatted=formatted_text is not None,
            )
        if enriched_text is not None and enriched_text != (formatted_text or draft_text):
            return EditorialTextSelection(
                text=enriched_text,
                source="enriched_text",
                has_rewrite=rewrite_text is not None,
                has_formatted=formatted_text is not None,
            )
        if formatted_text is not None:
            return EditorialTextSelection(
                text=formatted_text,
                source="formatted_text",
                has_rewrite=rewrite_text is not None,
                has_formatted=True,
            )
        return EditorialTextSelection(
            text=draft_text,
            source="text_draft",
            has_rewrite=rewrite_text is not None,
            has_formatted=False,
        )
