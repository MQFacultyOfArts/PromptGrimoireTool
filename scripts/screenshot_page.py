"""Take a Playwright screenshot of any page on a running dev server.

Usage:
    uv run scripts/screenshot_page.py /roleplay
    uv run scripts/screenshot_page.py /roleplay --width 800 --height 600
    uv run scripts/screenshot_page.py /roleplay --output /tmp/shot.png
    uv run scripts/screenshot_page.py /roleplay --inspect  # also dump flex chain
    uv run scripts/screenshot_page.py /annotation?workspace_id=...

Assumes DEV__AUTH_MOCK=true on the server. Authenticates as instructor@uni.edu.
"""

import asyncio

import typer
from playwright.async_api import async_playwright


async def _run(
    path: str,
    *,
    base_url: str,
    width: int,
    height: int,
    output: str,
    inspect: bool,
    email: str,
    chat: bool,
) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": width, "height": height})
        page = await context.new_page()

        # Mock auth
        await page.goto(
            f"{base_url}/auth/callback?token=mock-token-{email}",
            timeout=15_000,
        )
        await page.wait_for_url(lambda url: "/auth/callback" not in url, timeout=10_000)

        # Navigate to target
        url = f"{base_url}{path}" if path.startswith("/") else path
        await page.goto(url, wait_until="networkidle", timeout=15_000)
        await page.wait_for_timeout(2000)

        # Click "Mock Chat" button if --chat and it exists (dev mode only)
        if chat:
            mock_btn = page.get_by_text("Mock Chat")
            if await mock_btn.count() > 0:
                await mock_btn.click()
                await page.wait_for_timeout(500)

        # Screenshot
        await page.screenshot(path=output)
        print(f"Saved: {output}  ({width}x{height})")

        if inspect:
            await _inspect_layout(page)

        await browser.close()


async def _inspect_layout(page) -> None:
    """Dump bounding boxes and computed flex styles for layout debugging."""
    selectors = [
        ".q-layout",
        ".q-page-container",
        ".q-page",
        ".nicegui-content",
        ".roleplay-column",
        ".roleplay-main-row",
        ".roleplay-card",
        ".roleplay-chat",
    ]
    print("\n--- Layout inspection ---")
    for sel in selectors:
        count = await page.locator(sel).count()
        if count == 0:
            print(f"  {sel}: NOT FOUND")
            continue
        loc = page.locator(sel).first
        box = await loc.bounding_box()
        styles = await loc.evaluate(
            """el => {
            const s = getComputedStyle(el);
            return {
                display: s.display,
                flexDir: s.flexDirection,
                flex: s.flex,
                height: Math.round(parseFloat(s.height)) + 'px',
                minHeight: s.minHeight,
            };
        }"""
        )
        h = round(box["height"], 1) if box else "N/A"
        print(f"  {sel}: h={h}  {styles}")

    # Input width vs card width
    inp = page.locator('[data-testid="roleplay-message-input"]')
    card = page.locator(".roleplay-card")
    if await inp.count() > 0 and await card.count() > 0:
        ibox = await inp.first.bounding_box()
        cbox = await card.first.bounding_box()
        if ibox and cbox:
            pct = round(ibox["width"] / cbox["width"] * 100)
            iw = round(ibox["width"])
            cw = round(cbox["width"])
            print(f"  Input: {iw}px / card: {cw}px ({pct}%)")


app = typer.Typer(add_completion=False)


@app.command()
def main(
    path: str = typer.Argument(help="URL path, e.g. /roleplay"),
    base_url: str = typer.Option("http://localhost:8080", help="Server base URL"),
    width: int = typer.Option(1280, help="Viewport width"),
    height: int = typer.Option(800, help="Viewport height"),
    output: str = typer.Option(
        "/tmp/screenshot.png",  # noqa: S108
        help="Output file path",
    ),
    inspect: bool = typer.Option(False, help="Dump flex chain diagnostics"),
    email: str = typer.Option("instructor@uni.edu", help="Mock auth email"),
    chat: bool = typer.Option(False, help="Inject mock chat exchange (roleplay only)"),
) -> None:
    """Take a screenshot of a page on a running dev server."""
    asyncio.run(
        _run(
            path,
            base_url=base_url,
            width=width,
            height=height,
            output=output,
            inspect=inspect,
            email=email,
            chat=chat,
        )
    )


if __name__ == "__main__":
    app()
