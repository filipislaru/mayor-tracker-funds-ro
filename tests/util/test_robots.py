from __future__ import annotations

import pytest
from mayortracker.util.robots import RobotsRules

AGENT = "mayor-tracker-ro"


def allowed(text: str, path: str, agent: str = AGENT) -> bool:
    return RobotsRules.parse(text).is_allowed(f"https://test.invalid{path}", agent)


def test_empty_file_allows_everything() -> None:
    assert allowed("", "/anything")
    assert RobotsRules.allow_all().is_allowed("https://test.invalid/x", AGENT)


def test_wildcard_group_applies_when_no_specific_group() -> None:
    text = "User-agent: *\nDisallow: /private/\n"
    assert allowed(text, "/public/page")
    assert not allowed(text, "/private/page")


def test_specific_group_overrides_wildcard() -> None:
    text = "User-agent: *\nAllow: /\n\nUser-agent: Mayor-Tracker-RO\nDisallow: /\n"
    assert not allowed(text, "/page")
    assert allowed(text, "/page", agent="other-bot")


def test_longest_match_wins_and_allow_wins_ties() -> None:
    text = "User-agent: *\nDisallow: /docs/\nAllow: /docs/public/\nDisallow: /tie\nAllow: /tie\n"
    assert not allowed(text, "/docs/secret.pdf")
    assert allowed(text, "/docs/public/file.pdf")
    assert allowed(text, "/tie")


@pytest.mark.parametrize(
    ("path", "expected"),
    [("/files/a.pdf", False), ("/files/a.pdf?x=1", True), ("/a/b/tmp/c", False), ("/x", True)],
)
def test_wildcards_and_end_anchor(path: str, expected: bool) -> None:
    text = "User-agent: *\nDisallow: /*.pdf$\nDisallow: /*/tmp/\n"
    assert allowed(text, path) is expected


def test_multiple_agents_share_group_and_comments_ignored() -> None:
    text = "# TEST\nUser-agent: a-bot\nUser-agent: mayor-tracker-ro # us\nDisallow: /x\n"
    assert not allowed(text, "/x/1")
    assert not allowed(text, "/x/1", agent="a-bot")


def test_empty_disallow_matches_nothing() -> None:
    assert allowed("User-agent: *\nDisallow:\n", "/page")


def test_robots_txt_itself_always_allowed() -> None:
    assert allowed("User-agent: *\nDisallow: /\n", "/robots.txt")
