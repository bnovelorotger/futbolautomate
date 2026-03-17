from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class SourceName(StrEnum):
    SOCCERWAY = "soccerway"
    FUTBOLME = "futbolme"
    FFIB = "ffib"
    DIARIO_MALLORCA = "diario_mallorca"
    ULTIMA_HORA = "ultima_hora"
    IB3 = "ib3"


class TargetType(StrEnum):
    MATCHES = "matches"
    STANDINGS = "standings"
    NEWS = "news"


class MatchStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class NewsType(StrEnum):
    PREVIEW = "preview"
    CHRONICLE = "chronicle"
    TRANSFER = "transfer"
    SANCTION = "sanction"
    OFFICIAL_STATEMENT = "official_statement"
    RESULTS = "results"
    STANDINGS = "standings"
    INJURY = "injury"
    INSTITUTIONAL = "institutional"
    OTHER = "other"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class MatchWindow(StrEnum):
    TODAY = "today"
    TOMORROW = "tomorrow"
    NEXT_WEEKEND = "next_weekend"


class OutputFormat(StrEnum):
    CONSOLE = "console"
    JSON = "json"


class CompetitionIntegrationStatus(StrEnum):
    INTEGRATED = "integrated"
    READY_TO_INTEGRATE = "ready_to_integrate"
    DEFERRED = "deferred"
    MANUAL_ONLY = "manual_only"
    DISCARDED_FOR_NOW = "discarded_for_now"


class CompetitionReferenceRole(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    OFFICIAL = "official"
    NEWS = "news"
    DISCARDED = "discarded"


class ContentType(StrEnum):
    MATCH_RESULT = "match_result"
    RESULTS_ROUNDUP = "results_roundup"
    STANDINGS = "standings"
    STANDINGS_ROUNDUP = "standings_roundup"
    STANDINGS_EVENT = "standings_event"
    PREVIEW = "preview"
    RANKING = "ranking"
    FORM_RANKING = "form_ranking"
    FORM_EVENT = "form_event"
    FEATURED_MATCH_PREVIEW = "featured_match_preview"
    FEATURED_MATCH_EVENT = "featured_match_event"
    STAT_NARRATIVE = "stat_narrative"
    METRIC_NARRATIVE = "metric_narrative"
    VIRAL_STORY = "viral_story"


class EditorialPlanningContent(StrEnum):
    LATEST_RESULTS = "latest_results"
    RESULTS_ROUNDUP = "results_roundup"
    STANDINGS = "standings"
    STANDINGS_ROUNDUP = "standings_roundup"
    PREVIEW = "preview"
    FEATURED_MATCH_PREVIEW = "featured_match_preview"
    RANKING = "ranking"
    STAT_NARRATIVE = "stat_narrative"
    METRIC_NARRATIVE = "metric_narrative"
    VIRAL_STORY = "viral_story"


class NarrativeMetricType(StrEnum):
    WIN_STREAK = "win_streak"
    UNBEATEN_STREAK = "unbeaten_streak"
    BEST_ATTACK = "best_attack"
    BEST_DEFENSE = "best_defense"
    MOST_WINS = "most_wins"
    GOALS_AVERAGE = "goals_average"


class ViralStoryType(StrEnum):
    WIN_STREAK = "win_streak"
    UNBEATEN_STREAK = "unbeaten_streak"
    LOSING_STREAK = "losing_streak"
    BEST_ATTACK = "best_attack"
    BEST_DEFENSE = "best_defense"
    RECENT_TOP_SCORER = "recent_top_scorer"
    HOT_FORM = "hot_form"
    COLD_FORM = "cold_form"
    GOALS_TREND = "goals_trend"


class ContentCandidateStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class StandingsEventType(StrEnum):
    NEW_LEADER = "new_leader"
    ENTERED_PLAYOFF = "entered_playoff"
    LEFT_PLAYOFF = "left_playoff"
    ENTERED_RELEGATION = "entered_relegation"
    LEFT_RELEGATION = "left_relegation"
    BIGGEST_POSITION_RISE = "biggest_position_rise"
    BIGGEST_POSITION_DROP = "biggest_position_drop"


class FormEventType(StrEnum):
    BEST_FORM_TEAM = "best_form_team"
    WORST_FORM_TEAM = "worst_form_team"
    LONGEST_WIN_STREAK_RECENT = "longest_win_streak_recent"
    LONGEST_LOSS_STREAK_RECENT = "longest_loss_streak_recent"
