"""Control the official nugs.net web player through a logged-in Chrome session.

This module deliberately controls rendered first-party UI. It does not resolve,
download, proxy, decrypt, or expose subscriber media streams.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .api import extract_show_id

DEFAULT_CDP_ENDPOINT = os.environ.get("NUGS_CDP_ENDPOINT", "http://127.0.0.1:9222")
PLAYER_HOST = "play.nugs.net"
PLAYER_PANEL_LABEL = "Audio Player Control Panel"
TRANSPORT_TITLES = ("Previous Track", "Play/Pause", "Next Track")


class PlayerError(RuntimeError):
    """A bounded player failure suitable for CLI output."""


@dataclass(frozen=True)
class PlayerTarget:
    release_id: str
    release_url: str


def target_for(value: str | int) -> PlayerTarget:
    release_id = str(extract_show_id(value))
    return PlayerTarget(release_id, f"https://{PLAYER_HOST}/release/{release_id}")


def _normalize(value: str | None) -> str:
    return " ".join((value or "").split())


def _player_pages(context: Any) -> list[Any]:
    return [
        page
        for page in context.pages
        if not page.is_closed() and urlparse(page.url).hostname == PLAYER_HOST
    ]


def _one_player_page(context: Any) -> Any:
    pages = _player_pages(context)
    if len(pages) != 1:
        raise PlayerError(f"expected exactly one active nugs player page, found {len(pages)}")
    return pages[0]


def select_release_play(candidates: list[dict[str, Any]]) -> int:
    matches = [
        item
        for item in candidates
        if item.get("text") == "PLAY" and item.get("tag") == "button"
    ]
    if len(matches) != 1:
        raise PlayerError(f"expected one visible release PLAY button, found {len(matches)}")
    index = matches[0].get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        raise PlayerError("release PLAY button had no stable index")
    return index


def select_transport_cluster(candidates: list[dict[str, Any]]) -> dict[str, int]:
    matches = [item for item in candidates if item.get("titles") == list(TRANSPORT_TITLES)]
    if len(matches) != 1:
        raise PlayerError(f"expected one native transport cluster, found {len(matches)}")
    indexes = matches[0].get("indexes")
    if (
        not isinstance(indexes, list)
        or len(indexes) != 3
        or any(isinstance(value, bool) or not isinstance(value, int) for value in indexes)
    ):
        raise PlayerError("native transport cluster had invalid control indexes")
    return dict(zip(TRANSPORT_TITLES, indexes))


async def _release_play_candidates(page: Any) -> list[dict[str, Any]]:
    return await page.locator("button:visible").evaluate_all(
        r"""
        buttons => buttons.map((button, index) => ({
          index,
          tag: button.tagName.toLowerCase(),
          text: (button.innerText || '').replace(/\s+/g, ' ').trim().toUpperCase(),
        })).filter(item => item.text === 'PLAY')
        """
    )


async def _track_rows(page: Any) -> list[dict[str, Any]]:
    return await page.locator("[role='group'].track-item:visible").evaluate_all(
        r"""
        cards => cards.map((card, index) => {
          const normalize = value => (value || '').replace(/\s+/g, ' ').trim();
          const iconText = Array.from(card.querySelectorAll('button, [role="button"]'))
            .flatMap(control => [control, ...control.querySelectorAll('*')])
            .flatMap(element => [
              typeof element.className === 'string'
                ? element.className
                : (element.className && element.className.baseVal) || '',
              element.getAttribute('data-icon') || '',
              element.getAttribute('href') || '',
              element.getAttribute('xlink:href') || '',
            ])
            .join(' ')
            .toLowerCase();
          return {
            index,
            id: card.id || '',
            data_id: card.getAttribute('data-id') || '',
            track_id: card.getAttribute('data-song-id') || '',
            lines: (card.innerText || '').split(/\n+/).map(normalize).filter(Boolean),
            active: /(^|[-_\s])pause($|[-_\s])/.test(iconText),
          };
        })
        """
    )


async def _panel_title(page: Any) -> str | None:
    panels = page.locator(f"[aria-label='{PLAYER_PANEL_LABEL}']:visible")
    if await panels.count() != 1:
        return None
    lines = [_normalize(line) for line in (await panels.first.inner_text()).splitlines()]
    return next((line for line in lines if line), None)


async def _transport_candidates(page: Any) -> list[dict[str, Any]]:
    return await page.locator("button:visible, [role='button']:visible").evaluate_all(
        """
        controls => {
          const visible = element => {
            const style = window.getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
              && rect.width > 0 && rect.height > 0;
          };
          const wanted = ['Previous Track', 'Play/Pause', 'Next Track'];
          const clusters = [];
          controls.forEach((control, controlIndex) => {
            if (control.getAttribute('title') !== 'Play/Pause') return;
            let ancestor = control;
            while (ancestor && ancestor !== document.documentElement) {
              const descendants = controls.filter(item => ancestor.contains(item) && visible(item));
              const found = wanted.map(title => descendants.filter(
                item => item.getAttribute('title') === title
              ));
              if (found.every(group => group.length === 1)) {
                clusters.push({
                  titles: wanted,
                  indexes: found.map(group => controls.indexOf(group[0])),
                  control_index: controlIndex,
                });
                break;
              }
              ancestor = ancestor.parentElement;
            }
          });
          return clusters.filter((item, index, all) =>
            all.findIndex(other => JSON.stringify(other.indexes) === JSON.stringify(item.indexes)) === index
          );
        }
        """
    )


async def _native_state(page: Any) -> str:
    value = await page.evaluate(
        """
        () => {
          const media = navigator.mediaSession ? navigator.mediaSession.playbackState : null;
          const elements = Array.from(document.querySelectorAll('audio, video'));
          const element = elements.length === 1
            ? (elements[0].ended ? 'ended' : (elements[0].paused ? 'paused' : 'playing'))
            : null;
          if (media === element && media) return media;
          if (media === 'playing' || media === 'paused') return media;
          if (element) return element;
          return 'unknown';
        }
        """
    )
    return value if value in {"playing", "paused", "ended"} else "unknown"


async def _snapshot(page: Any) -> dict[str, Any]:
    parsed = urlparse(page.url)
    match = re.fullmatch(r"/release/(\d+)", parsed.path.rstrip("/"))
    if parsed.scheme != "https" or parsed.hostname != PLAYER_HOST or not match:
        raise PlayerError(f"active page is not one exact nugs release: {page.url}")

    title = await _panel_title(page)
    rows = await _track_rows(page)
    active = [row for row in rows if row.get("active")]
    selected = active[0] if len(active) == 1 else None
    return {
        "player_present": True,
        "state": await _native_state(page),
        "release_id": match.group(1),
        "release_url": page.url,
        "track_title": title,
        "track_id": selected.get("track_id") if selected else None,
    }


async def _wait_for(page: Any, *, state: str, title: str | None = None) -> dict[str, Any]:
    deadline = 15_000
    step = 250
    for _ in range(deadline // step):
        snapshot = await _snapshot(page)
        if snapshot["state"] == state and (title is None or snapshot["track_title"] == title):
            return snapshot
        await page.wait_for_timeout(step)
    expected = f"{state} / {title}" if title else state
    raise PlayerError(f"nugs player did not reach {expected}")


async def _play(context: Any, target: PlayerTarget, track_title: str | None) -> dict[str, Any]:
    if _player_pages(context):
        raise PlayerError("stop the active nugs player before starting another release")
    page = next((candidate for candidate in context.pages if not candidate.is_closed()), None)
    if page is None:
        page = await context.new_page()
    await page.goto(target.release_url, wait_until="domcontentloaded", timeout=30_000)
    if page.url.rstrip("/") != target.release_url:
        raise PlayerError(f"nugs player resolved a different release: {page.url}")
    await page.locator("[role='group'].track-item:visible").first.wait_for(
        state="visible", timeout=30_000
    )
    rows = await _track_rows(page)
    normalized_title = _normalize(track_title)
    if normalized_title:
        if not rows or normalized_title not in rows[0].get("lines", []):
            raise PlayerError(
                "play-track supports the exact first rendered track only; "
                f"requested {normalized_title!r}"
            )
    button_index = select_release_play(await _release_play_candidates(page))
    button = page.locator("button:visible").nth(button_index)
    await button.click(trial=True)
    await button.click()
    snapshot = await _wait_for(page, state="playing", title=normalized_title or None)
    return {"command": "play-track" if normalized_title else "play", **snapshot}


async def _transport(
    context: Any,
    command: str,
    expected_title: str | None = None,
    expected_target: str | int | None = None,
) -> dict[str, Any]:
    page = _one_player_page(context)
    before = await _snapshot(page)
    if expected_target is not None and before["release_id"] != target_for(expected_target).release_id:
        raise PlayerError(
            f"active release {before['release_id']} did not match {target_for(expected_target).release_id}"
        )
    if expected_title and before["track_title"] != _normalize(expected_title):
        raise PlayerError(
            f"active track {before['track_title']!r} did not match {expected_title!r}"
        )
    required_before = "paused" if command == "resume" else "playing"
    if before["state"] != required_before:
        raise PlayerError(
            f"{command} requires {required_before} playback, found {before['state']}"
        )
    clusters = select_transport_cluster(await _transport_candidates(page))
    title = {
        "pause": "Play/Pause",
        "resume": "Play/Pause",
        "next": "Next Track",
        "previous": "Previous Track",
    }[command]
    desired_state = "paused" if command == "pause" else "playing"
    control = page.locator("button:visible, [role='button']:visible").nth(clusters[title])
    if await control.get_attribute("title") != title:
        raise PlayerError("native transport controls changed before click")
    await control.click()
    after = await _wait_for(page, state=desired_state)
    return {"command": command, "before": before, **after}


async def run_command(
    command: str,
    *,
    endpoint: str = DEFAULT_CDP_ENDPOINT,
    target: str | int | None = None,
    source_url: str | None = None,
    track_title: str | None = None,
    from_track_title: str | None = None,
    to_track_title: str | None = None,
) -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as error:
        raise PlayerError("player commands require: pip install 'nugs-cli[player]'") from error

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.connect_over_cdp(endpoint, timeout=10_000)
        except Exception as error:
            raise PlayerError(f"could not connect to logged-in Chrome at {endpoint}") from error
        try:
            if len(browser.contexts) != 1:
                raise PlayerError(
                    f"expected one Chrome context at {endpoint}, found {len(browser.contexts)}"
                )
            context = browser.contexts[0]
            if command in {"play", "play-track"}:
                if target is None:
                    raise PlayerError(f"{command} requires a release target")
                if source_url:
                    parsed_source = urlparse(source_url)
                    if (
                        parsed_source.scheme != "https"
                        or parsed_source.hostname not in {"nugs.net", "www.nugs.net"}
                        or str(extract_show_id(source_url)) != target_for(target).release_id
                    ):
                        raise PlayerError("source URL did not identify the exact nugs release target")
                return await _play(context, target_for(target), track_title)
            if command == "status":
                pages = _player_pages(context)
                if not pages:
                    return {"command": "status", "player_present": False, "state": "idle"}
                return {"command": "status", **await _snapshot(_one_player_page(context))}
            if command == "stop":
                page = _one_player_page(context)
                before = await _snapshot(page)
                remaining = [item for item in context.pages if item is not page and not item.is_closed()]
                if not remaining:
                    await context.new_page()
                await page.close()
                if _player_pages(context):
                    raise PlayerError("nugs player page remained after stop")
                return {"command": "stop", "before": before, "player_present": False, "state": "idle"}
            if command in {"pause", "resume"}:
                return await _transport(context, command, expected_target=target)
            if command in {"next", "previous"}:
                result = await _transport(
                    context,
                    command,
                    from_track_title,
                    expected_target=target,
                )
                expected = _normalize(to_track_title)
                if expected and result.get("track_title") != expected:
                    raise PlayerError(
                        f"{command} selected {result.get('track_title')!r}, expected {expected!r}"
                    )
                return result
            raise PlayerError(f"unsupported player command: {command}")
        finally:
            await browser.close()
