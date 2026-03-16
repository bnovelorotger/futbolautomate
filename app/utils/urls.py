from __future__ import annotations

from functools import lru_cache
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser


def absolutize(base_url: str, value: str | None) -> str | None:
    if not value:
        return value
    return urljoin(base_url, value)


@lru_cache(maxsize=64)
def build_robot_parser(base_url: str) -> RobotFileParser:
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.read()
    return parser


def is_allowed_by_robots(base_url: str, user_agent: str, url: str) -> bool:
    parser = build_robot_parser(base_url)
    return parser.can_fetch(user_agent, url)

