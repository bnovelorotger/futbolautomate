from __future__ import annotations

import logging
from pathlib import Path

from app.channels.x_browser.engagement import EngagementResult, engage_timeline
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class XEngagementService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def run_daily_engagement(self, *, dry_run: bool = False) -> EngagementResult:
        """Like a few tweets from the home timeline. Designed to run once per day."""
        state_file = Path(self._settings.x_browser_state_file)
        likes = self._settings.x_engagement_daily_likes
        result = engage_timeline(likes=likes, state_file=state_file, dry_run=dry_run)
        if dry_run:
            logger.info("[dry-run] Would like %d tweets", likes)
        else:
            logger.info("Engagement done: liked %d/%d tweets", result.liked, result.attempted)
        return result
