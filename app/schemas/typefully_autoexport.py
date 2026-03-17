from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.core.enums import ContentCandidateStatus, ContentType


class TypefullyAutoexportPhasePolicy(BaseModel):
    allowed_content_types: list[ContentType] = Field(default_factory=list)
    validation_required_content_types: list[ContentType] = Field(default_factory=list)


class TypefullyAutoexportPolicy(BaseModel):
    enabled: bool = True
    phase: int = Field(default=1, ge=1)
    default_limit: int = 10
    use_rewrite_by_default: bool = True
    max_text_length: int = 280
    duplicate_window_hours: int = 72
    max_line_breaks: int = 6
    max_exports_per_run: int | None = Field(default=5, ge=1)
    max_exports_per_day: int | None = Field(default=None, ge=1)
    stop_on_capacity_limit: bool = True
    capacity_error_codes: list[str] = Field(default_factory=lambda: ["MONETIZATION_ERROR"])
    allowed_content_types: list[ContentType] = Field(default_factory=list)
    manual_review_content_types: list[ContentType] = Field(default_factory=list)
    validation_required_content_types: list[ContentType] = Field(default_factory=list)
    phases: dict[int, TypefullyAutoexportPhasePolicy] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_overlap(self) -> "TypefullyAutoexportPolicy":
        overlap = set(self.allowed_content_types) & set(self.manual_review_content_types)
        if overlap:
            values = ", ".join(sorted(str(item) for item in overlap))
            raise ValueError(f"Typefully autoexport policy solapa tipos permitidos y manuales: {values}")
        invalid_validation = set(self.validation_required_content_types) - set(self.allowed_content_types)
        if invalid_validation:
            values = ", ".join(sorted(str(item) for item in invalid_validation))
            raise ValueError(f"Typefully autoexport policy exige validacion sobre tipos no permitidos: {values}")
        if self.phases:
            if self.phase not in self.phases:
                raise ValueError(f"Typefully autoexport policy no define la fase activa: {self.phase}")
            for phase_id, phase_policy in self.phases.items():
                phase_overlap = set(phase_policy.allowed_content_types) & set(self.manual_review_content_types)
                if phase_overlap:
                    values = ", ".join(sorted(str(item) for item in phase_overlap))
                    raise ValueError(
                        f"Typefully autoexport policy solapa tipos manuales con la fase {phase_id}: {values}"
                    )
                phase_invalid_allowed = set(phase_policy.allowed_content_types) - set(self.allowed_content_types)
                if phase_invalid_allowed:
                    values = ", ".join(sorted(str(item) for item in phase_invalid_allowed))
                    raise ValueError(
                        f"Typefully autoexport policy define tipos fuera del catalogo global en fase {phase_id}: {values}"
                    )
                phase_invalid_validation = (
                    set(phase_policy.validation_required_content_types) - set(phase_policy.allowed_content_types)
                )
                if phase_invalid_validation:
                    values = ", ".join(sorted(str(item) for item in phase_invalid_validation))
                    raise ValueError(
                        f"Typefully autoexport policy exige validacion sobre tipos no permitidos en fase {phase_id}: {values}"
                    )
        return self

    def active_phase_policy(self) -> TypefullyAutoexportPhasePolicy:
        if not self.phases:
            return TypefullyAutoexportPhasePolicy(
                allowed_content_types=list(self.allowed_content_types),
                validation_required_content_types=list(self.validation_required_content_types),
            )
        return self.phases[self.phase]

    def active_allowed_content_types(self) -> list[ContentType]:
        return list(self.active_phase_policy().allowed_content_types)

    def active_validation_required_content_types(self) -> list[ContentType]:
        return list(self.active_phase_policy().validation_required_content_types)

    def allows(self, content_type: ContentType) -> bool:
        if content_type in self.manual_review_content_types:
            return False
        return content_type in self.active_allowed_content_types()

    def requires_validation(self, content_type: ContentType) -> bool:
        return content_type in self.active_validation_required_content_types()


class TypefullyAutoexportCandidateView(BaseModel):
    id: int
    competition_slug: str
    content_type: ContentType
    priority: int
    status: ContentCandidateStatus
    autoexport_allowed: bool
    policy_reason: str
    importance_score: int | None = None
    priority_bucket: str | None = None
    importance_reasoning: list[str] = Field(default_factory=list)
    order_selected: int | None = None
    quality_check_passed: bool | None = None
    quality_check_errors: list[str] = Field(default_factory=list)
    export_outcome: str = "pending"
    has_rewrite: bool = False
    text_source: str = "text_draft"
    external_publication_ref: str | None = None
    external_publication_error: str | None = None
    excerpt: str


class TypefullyAutoexportRunResult(BaseModel):
    executed_at: datetime
    dry_run: bool
    policy_enabled: bool
    phase: int
    reference_date: date | None = None
    scanned_count: int
    eligible_count: int
    exported_count: int
    blocked_count: int
    capacity_deferred_count: int = 0
    failed_count: int = 0
    capacity_limit_reached: bool = False
    capacity_limit_reason: str | None = None
    rows: list[TypefullyAutoexportCandidateView] = Field(default_factory=list)


class TypefullyAutoexportLastRun(BaseModel):
    executed_at: datetime
    dry_run: bool
    policy_enabled: bool
    phase: int
    reference_date: date | None = None
    scanned_count: int
    eligible_count: int
    exported_count: int
    blocked_count: int
    capacity_deferred_count: int = 0
    failed_count: int = 0
    capacity_limit_reached: bool = False
    capacity_limit_reason: str | None = None


class TypefullyAutoexportStatusView(BaseModel):
    enabled: bool
    phase: int
    importance_prioritization_enabled: bool = True
    importance_tie_breaker: str = "importance_score desc, priority desc, created_at asc, id asc"
    max_exports_per_run: int | None = None
    max_exports_per_day: int | None = None
    stop_on_capacity_limit: bool = True
    capacity_error_codes: list[str] = Field(default_factory=list)
    allowed_content_types: list[ContentType] = Field(default_factory=list)
    validation_required_content_types: list[ContentType] = Field(default_factory=list)
    manual_review_content_types: list[ContentType] = Field(default_factory=list)
    pending_capacity_count: int = 0
    pending_normal_count: int = 0
    last_run: TypefullyAutoexportLastRun | None = None
