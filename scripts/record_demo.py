"""Record the demo video's screen shots against a running Bylaw server.

    BYLAW_PASS=... uv run --with playwright python scripts/record_demo.py http://<host>:8080 recordings/

Each shot is its own browser context and its own .webm, so they can be cut and narrated
separately. Every request goes through the live agent, the real gate and the real Decider; the
script only clicks the buttons a viewer would click and waits for the answers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

SIZE = {"width": 1440, "height": 900}
IDLE = """() => {
  const buttons = [...document.querySelectorAll('.tries button')];
  return buttons.length > 0 && buttons.every(b => !b.disabled);
}"""


def wait_idle(page: Page, timeout_ms: int = 240_000) -> None:
    page.wait_for_timeout(800)
    page.wait_for_function(IDLE, timeout=timeout_ms)


def open_desk(page: Page, base: str) -> None:
    page.goto(f"{base}/#/")
    page.wait_for_selector(".ledger", timeout=60_000)
    wait_idle(page)
    page.wait_for_timeout(1500)


def try_request(page: Page, starts_with: str) -> None:
    page.locator(".tries button", has_text=starts_with).first.click()


def shot_policy(page: Page, base: str) -> None:
    open_desk(page, base)
    for _ in range(14):
        page.locator(".ledger").evaluate("el => el.scrollBy({top: 60, behavior: 'smooth'})")
        page.wait_for_timeout(450)
    page.wait_for_timeout(1500)


def shot_business(page: Page, base: str) -> None:
    open_desk(page, base)
    box = page.locator("textarea#ask")
    box.click()
    box.press_sequentially("Sam told me to fly business to London on the 27th for the audit.", delay=45)
    page.wait_for_timeout(600)
    page.locator("button[type=submit]").click()
    wait_idle(page)
    page.wait_for_timeout(4000)


def shot_hotel(page: Page, base: str) -> None:
    open_desk(page, base)
    try_request(page, "Book South Shore Lofts")
    wait_idle(page)
    page.wait_for_timeout(4500)


def shot_lamar(page: Page, base: str) -> None:
    open_desk(page, base)
    try_request(page, "Lamar House")
    wait_idle(page)
    sign = page.get_by_role("button", name="Sign off")
    if sign.count():
        page.wait_for_timeout(2500)
        sign.first.click()
        wait_idle(page)
    page.wait_for_timeout(4000)


def shot_dinner(page: Page, base: str) -> None:
    open_desk(page, base)
    try_request(page, "File the team dinner")
    wait_idle(page)
    page.wait_for_timeout(4500)


def shot_bench(page: Page, base: str) -> None:
    page.goto(f"{base}/#/bench")
    page.wait_for_selector("table.results", timeout=60_000)
    page.wait_for_timeout(2500)
    for _ in range(40):
        page.mouse.wheel(0, 120)
        page.wait_for_timeout(250)
    page.wait_for_timeout(2000)


SHOTS = {"01-policy": shot_policy, "02-business": shot_business, "05-hotel": shot_hotel,
         "06-lamar": shot_lamar, "07-dinner": shot_dinner, "08-bench": shot_bench}


def main(base: str, out: Path, only: list[str]) -> None:
    password = os.environ["BYLAW_PASS"]
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, shot in SHOTS.items():
            if only and name not in only:
                continue
            ctx = browser.new_context(viewport=SIZE, record_video_dir=str(out / name), record_video_size=SIZE,
                                      device_scale_factor=1)
            ctx.add_init_script(f"sessionStorage.setItem('bylaw-pass', {password!r})")
            page = ctx.new_page()
            try:
                shot(page, base.rstrip("/"))
                page.screenshot(path=str(out / f"{name}.png"))
                print(name, "ok", flush=True)
            except Exception as exc:  # keep going; a failed shot can be re-run on its own
                page.screenshot(path=str(out / f"{name}-failed.png"))
                print(name, "FAILED", type(exc).__name__, str(exc)[:200], flush=True)
            finally:
                ctx.close()
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]), sys.argv[3:])
