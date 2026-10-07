"""Minimal robots.txt parser and matcher following RFC 9309.

Implemented here rather than with ``urllib.robotparser`` because the standard library uses
first-match instead of longest-match, does not support the ``*`` and ``$`` wildcards, and
treats 401/403 differently from RFC 9309.

Fetching and HTTP-status semantics live in :mod:`mayortracker.util.http`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class _Rule:
    allow: bool
    pattern: str
    regex: re.Pattern[str]


def _compile(pattern: str) -> re.Pattern[str]:
    anchored_end = pattern.endswith("$")
    body = pattern[:-1] if anchored_end else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(regex + (r"\Z" if anchored_end else ""))


@dataclass
class RobotsRules:
    """Parsed robots.txt: rule groups keyed by lower-cased user-agent product token."""

    groups: dict[str, list[_Rule]] = field(default_factory=dict)

    @classmethod
    def allow_all(cls) -> RobotsRules:
        return cls()

    @classmethod
    def parse(cls, text: str) -> RobotsRules:
        groups: dict[str, list[_Rule]] = {}
        current_agents: list[str] = []
        in_rules = False  # True once the current group has seen a rule line
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if in_rules:
                    current_agents = []
                    in_rules = False
                agent = value.lower()
                current_agents.append(agent)
                groups.setdefault(agent, [])
            elif key in ("allow", "disallow"):
                in_rules = True
                if not current_agents or not value:
                    continue  # rule outside a group, or empty rule (matches nothing)
                rule = _Rule(allow=key == "allow", pattern=value, regex=_compile(value))
                for agent in current_agents:
                    groups[agent].append(rule)
            # Other keys (sitemap, crawl-delay, ...) are ignored and do not end a group.
        return cls(groups=groups)

    def is_allowed(self, url: str, agent_token: str) -> bool:
        """Return whether ``agent_token`` may fetch ``url`` (longest match; allow wins ties)."""
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        if path == "/robots.txt":
            return True
        rules = self.groups.get(agent_token.lower())
        if rules is None:
            rules = self.groups.get("*", [])
        best: _Rule | None = None
        for rule in rules:
            if not rule.regex.match(path):
                continue
            if (
                best is None
                or len(rule.pattern) > len(best.pattern)
                or (len(rule.pattern) == len(best.pattern) and rule.allow)
            ):
                best = rule
        return True if best is None else best.allow
