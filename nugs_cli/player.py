"""Control the official nugs.net web player through a logged-in Chrome session.

This module deliberately controls rendered first-party UI. It does not resolve,
download, proxy, decrypt, or expose subscriber media streams.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from . import __version__
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


def validate_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise PlayerError("Chrome DevTools endpoint must be an HTTP(S) loopback address")


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


def select_track_row(
    candidates: list[dict[str, Any]],
    *,
    title: str,
    track_id: str | int | None = None,
) -> int:
    normalized_title = _normalize(title)
    expected_id = str(track_id) if track_id is not None else None
    matches = []
    for item in candidates:
        lines = [_normalize(line) for line in item.get("lines", [])]
        if normalized_title not in lines:
            continue
        if expected_id is not None and str(item.get("data_id") or "") != expected_id:
            continue
        matches.append(item)
    if len(matches) != 1:
        identity = f"track {expected_id} / {normalized_title!r}" if expected_id else repr(normalized_title)
        raise PlayerError(f"expected one rendered row for {identity}, found {len(matches)}")
    index = matches[0].get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        raise PlayerError("rendered track row had no stable index")
    return index


def signed_in_from_visible_text(text: str) -> bool:
    visible = _normalize(text).casefold()
    return "my library" in visible and re.search(r"\b(?:log in|login|sign in)\b", visible) is None


def reconcile_player_state(native: str, rendered: str, active_track_count: int) -> str:
    rendered_state = rendered if rendered in {"playing", "paused"} else "unknown"
    native_state = native if native in {"playing", "paused", "ended"} else "unknown"
    if active_track_count > 1:
        raise PlayerError(f"nugs player exposed {active_track_count} active track rows")
    if rendered_state == "playing":
        return "playing" if native_state in {"unknown", "playing"} else "unknown"
    if rendered_state == "paused":
        return "paused" if active_track_count == 0 and native_state in {"unknown", "paused"} else "unknown"
    if rendered_state == "unknown" and active_track_count == 1:
        if native_state in {"paused", "ended"}:
            raise PlayerError(
                f"nugs player state conflicted: active row=playing, native={native_state}"
            )
        return "playing"
    return rendered_state if rendered_state != "unknown" else native_state


async def _wait_for_signed_in(page: Any) -> bool:
    for _ in range(40):
        visible_text = await page.locator("body").inner_text(timeout=10_000)
        if signed_in_from_visible_text(visible_text):
            return True
        await page.wait_for_timeout(250)
    return False


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


async def _rendered_transport_state(page: Any) -> str:
    try:
        clusters = select_transport_cluster(await _transport_candidates(page))
    except PlayerError:
        return "unknown"
    control = page.locator("button:visible, [role='button']:visible").nth(
        clusters["Play/Pause"]
    )
    signal = await control.evaluate(
        """
        element => {
          const values = [element, ...element.querySelectorAll('*')].flatMap(candidate => [
            typeof candidate.className === 'string'
              ? candidate.className
              : (candidate.className && candidate.className.baseVal) || '',
            candidate.getAttribute('data-icon') || '',
            candidate.getAttribute('href') || '',
            candidate.getAttribute('xlink:href') || '',
          ]).join(' ').toLowerCase();
          if (/(^|[-_\\s])pause($|[-_\\s])/.test(values)) return 'playing';
          if (/(^|[-_\\s])play($|[-_\\s])/.test(values)) return 'paused';
          return 'unknown';
        }
        """
    )
    return signal if signal in {"playing", "paused"} else "unknown"


async def _snapshot(page: Any) -> dict[str, Any]:
    parsed = urlparse(page.url)
    match = re.fullmatch(r"/release/(\d+)", parsed.path.rstrip("/"))
    if parsed.scheme != "https" or parsed.hostname != PLAYER_HOST or not match:
        raise PlayerError(f"active page is not one exact nugs release: {page.url}")

    title = await _panel_title(page)
    rows = await _track_rows(page)
    active = [row for row in rows if row.get("active")]
    selected = active[0] if len(active) == 1 else None
    native_state = await _native_state(page)
    rendered_state = await _rendered_transport_state(page)
    return {
        "player_present": True,
        "state": reconcile_player_state(native_state, rendered_state, len(active)),
        "release_id": match.group(1),
        "release_url": page.url,
        "track_title": title,
        "track_id": selected.get("data_id") if selected else None,
        "song_id": selected.get("track_id") if selected else None,
    }


async def _wait_for(
    page: Any,
    *,
    state: str,
    title: str | None = None,
    track_id: str | int | None = None,
) -> dict[str, Any]:
    deadline = 15_000
    step = 250
    for _ in range(deadline // step):
        snapshot = await _snapshot(page)
        title_matches = title is None or snapshot["track_title"] == title
        id_matches = track_id is None or str(snapshot.get("track_id") or "") == str(track_id)
        if snapshot["state"] == state and title_matches and id_matches:
            return snapshot
        await page.wait_for_timeout(step)
    expected = " / ".join(filter(None, [state, title, str(track_id) if track_id else None]))
    raise PlayerError(f"nugs player did not reach {expected}")


async def _play(
    context: Any,
    target: PlayerTarget,
    track_title: str | None,
    track_id: str | int | None,
) -> dict[str, Any]:
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
        row_index = select_track_row(rows, title=normalized_title, track_id=track_id)
        row = page.locator("[role='group'].track-item:visible").nth(row_index)
        if track_id is not None and await row.get_attribute("data-id") != str(track_id):
            raise PlayerError("rendered track identity changed before playback")
        await row.dblclick(trial=True)
        await row.dblclick()
    else:
        button_index = select_release_play(await _release_play_candidates(page))
        button = page.locator("button:visible").nth(button_index)
        await button.click(trial=True)
        await button.click()
    snapshot = await _wait_for(
        page,
        state="playing",
        title=normalized_title or None,
        track_id=track_id,
    )
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
    track_id: str | int | None = None,
    from_track_title: str | None = None,
    to_track_title: str | None = None,
) -> dict[str, Any]:
    validate_endpoint(endpoint)
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
                return await _play(context, target_for(target), track_title, track_id)
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
            # Leaving the Playwright context disconnects this CDP client. Do
            # not call Browser.close() against a user-owned Chrome process.
            pass


async def diagnose(
    *,
    endpoint: str = DEFAULT_CDP_ENDPOINT,
    target: str | int | None = None,
) -> dict[str, Any]:
    """Inspect the local logged-in player without starting or changing playback."""
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    try:
        validate_endpoint(endpoint)
        record("endpoint", True, "HTTP(S) loopback endpoint")
    except PlayerError as error:
        record("endpoint", False, str(error))
        return {
            "ok": False,
            "version": __version__,
            "python": sys.version.split()[0],
            "endpoint": endpoint,
            "checks": checks,
        }

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        record("player_extra", False, "install with: pip install 'nugs-cli[player]'")
        return {
            "ok": False,
            "version": __version__,
            "python": sys.version.split()[0],
            "endpoint": endpoint,
            "checks": checks,
        }
    record("player_extra", True, "Playwright is installed")

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.connect_over_cdp(endpoint, timeout=10_000)
        except Exception:
            record("browser", False, f"could not connect to Chrome at {endpoint}")
            return {
                "ok": False,
                "version": __version__,
                "python": sys.version.split()[0],
                "endpoint": endpoint,
                "checks": checks,
            }
        record("browser", True, "connected to Chrome over DevTools")
        temporary_page = None
        try:
            if len(browser.contexts) != 1:
                record("context", False, f"expected one Chrome context, found {len(browser.contexts)}")
            else:
                record("context", True, "one Chrome context")
                context = browser.contexts[0]
                pages = _player_pages(context)
                requested = target_for(target) if target is not None else None
                page = pages[0] if len(pages) == 1 and requested is None else None
                if page is None:
                    temporary_page = await context.new_page()
                    page = temporary_page
                    destination = requested.release_url if requested else f"https://{PLAYER_HOST}"
                    try:
                        await page.goto(destination, wait_until="domcontentloaded", timeout=30_000)
                    except Exception:
                        record("web_player", False, f"could not load {destination}")
                        page = None
                if page is not None:
                    host_ok = urlparse(page.url).hostname == PLAYER_HOST
                    record("web_player", host_ok, page.url if host_ok else f"unexpected page: {page.url}")
                    if host_ok:
                        if requested is not None:
                            try:
                                await page.locator("[role='group'].track-item:visible").first.wait_for(
                                    state="visible", timeout=30_000
                                )
                                rows = await _track_rows(page)
                                release_buttons = await _release_play_candidates(page)
                                select_release_play(release_buttons)
                                record(
                                    "release_controls",
                                    bool(rows),
                                    f"release {requested.release_id}: {len(rows)} rendered tracks",
                                )
                            except Exception as error:
                                record("release_controls", False, str(error))
                        logged_in = await _wait_for_signed_in(page)
                        record(
                            "session",
                            logged_in,
                            "logged-in library navigation is present"
                            if logged_in else "logged-in nugs session was not detected",
                        )
        finally:
            if temporary_page is not None and not temporary_page.is_closed():
                await temporary_page.close()
            # The async_playwright context owns this CDP connection. Do not
            # close the user-owned Chrome process.

    return {
        "ok": all(check["ok"] for check in checks),
        "version": __version__,
        "python": sys.version.split()[0],
        "endpoint": endpoint,
        "checks": checks,
    }
