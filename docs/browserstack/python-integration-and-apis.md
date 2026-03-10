---
source: https://www.browserstack.com/docs/automate/playwright/getting-started/python/integrate-your-tests, https://www.browserstack.com/docs/automate/playwright/playwright-capabilities, https://www.browserstack.com/docs/automate/api-reference/selenium/introduction, https://www.browserstack.com/docs/automate/api-reference/selenium/automate-api, https://www.browserstack.com/docs/automate/api-reference/selenium/plan, https://www.browserstack.com/docs/automate/api-reference/selenium/browser, https://www.browserstack.com/docs/automate/api-reference/selenium/build, https://www.browserstack.com/docs/automate/api-reference/selenium/session, https://www.browserstack.com/docs/automate/selenium/sdk-faqs/generic/cli-args, https://www.browserstack.com/docs/automate/selenium/manage-incoming-connections, https://www.browserstack.com/docs/local-testing/internals, https://github.com/browserstack/mcp-server
fetched: 2026-03-09
library: browserstack
summary: BrowserStack integration patterns for Python pytest and Playwright suites, Automate REST APIs, Local Testing, and MCP workflows
---

# BrowserStack for Python Projects

BrowserStack exposes three distinct integration surfaces that matter for a Python project:

1. **Pytest SDK integration** for Python suites, including Playwright-Pytest and Selenium-Pytest.
2. **Direct Playwright connection** over BrowserStack's CDP endpoint for custom or non-SDK Playwright runs.
3. **Automate REST APIs** for plan capacity, browser inventory, builds, sessions, logs, and session status updates.

For PromptGrimoire specifically, the first-class path is now **Playwright-Pytest via the BrowserStack SDK**, because the repo already uses `pytest` and Playwright for browser E2E work.

## Credentials and Configuration

BrowserStack's docs recommend storing credentials in environment variables before integrating your suite:

- `BROWSERSTACK_USERNAME`
- `BROWSERSTACK_ACCESS_KEY`

BrowserStack SDK also supports these optional environment variables and matching CLI args:

- `BROWSERSTACK_PROJECT_NAME`
- `BROWSERSTACK_BUILD_NAME`
- `BROWSERSTACK_BUILD_IDENTIFIER`
- `BROWSERSTACK_PARALLELS_PER_PLATFORM`
- `BROWSERSTACK_LOCAL`
- `BROWSERSTACK_LOCAL_IDENTIFIER`

`browserstack.yml` can interpolate environment variables using `${ENV_VARIABLE}`. CLI args override environment variables.

Repo-specific recommendation: keep secrets only in CI/local env vars and use `browserstack.yml` for non-secret matrix and reporting settings.

## Preferred Path: Pytest SDK

BrowserStack now documents a **Playwright-Pytest SDK** flow in addition to the older direct-capability Playwright flow.

### What BrowserStack documents

- Existing automated suite required.
- `pytest`, Python 3, and **Java 8+** installed locally.
- Install the SDK with `pip`.
- Run `browserstack-sdk setup --framework "pytest"` once.
- A root-level `browserstack.yml` is created.
- Run tests by prepending `browserstack-sdk` to the normal pytest command.

### Minimal setup

```bash
python3 -m pip install browserstack-sdk
browserstack-sdk setup --framework "pytest"
browserstack-sdk pytest tests/e2e
```

### Example `browserstack.yml`

This example combines BrowserStack's documented config shape with env-var interpolation:

```yaml
userName: ${BROWSERSTACK_USERNAME}
accessKey: ${BROWSERSTACK_ACCESS_KEY}
framework: pytest

platforms:
  - browserName: chrome
    os: OS X
    osVersion: Ventura
    browserVersion: latest
  - browserName: edge
    os: Windows
    osVersion: 11
    browserVersion: latest

browserstackLocal: true
buildName: ${BROWSERSTACK_BUILD_NAME}
projectName: ${BROWSERSTACK_PROJECT_NAME}
```

### Reporting details

BrowserStack's Playwright-Pytest docs call out these conventions:

- `buildName` should usually match the CI build/run identifier.
- `projectName` and `buildName` should stay static for a single build run.
- `sessionName` is picked automatically from the test class/spec name when using the SDK.
- BrowserStack provides session logs and whole-test video by default, and exposes extra debugging toggles for video and console logging.

## When To Use Direct Playwright Instead

Use BrowserStack's direct Playwright connection when you want full manual control over capabilities, session naming, or custom status reporting without the SDK wrapper.

BrowserStack's documented Python pattern is:

```python
import json
import urllib.parse
from playwright.sync_api import sync_playwright


def mark_test_status(status: str, reason: str, page) -> None:
    page.evaluate(
        "_ => {}",
        'browserstack_executor: {"action": "setSessionStatus", '
        f'"arguments": {{"status":"{status}", "reason": "{reason}"}}}',
    )


desired_cap = {
    "os": "osx",
    "os_version": "catalina",
    "browser": "chrome",
    "browser_version": "latest",
    "browserstack.username": "YOUR_USERNAME",
    "browserstack.accessKey": "YOUR_ACCESS_KEY",
    "project": "PromptGrimoire",
    "build": "playwright-build-1",
    "name": "test_law_student",
    "browserstack.local": "true",
    "browserstack.localIdentifier": "promptgrimoire-local",
    "browserstack.playwrightVersion": "1.latest",
    "client.playwrightVersion": "1.latest",
}

with sync_playwright() as playwright:
    cdp_url = (
        "wss://cdp.browserstack.com/playwright?caps="
        + urllib.parse.quote(json.dumps(desired_cap))
    )
    browser = playwright.chromium.connect(cdp_url)
    page = browser.new_page()
    page.goto("http://localhost:8080")
    mark_test_status("passed", "Smoke flow completed", page)
    browser.close()
```

Notable BrowserStack Playwright capabilities:

- `os`, `os_version`, `browser`, `browser_version`
- `project`, `build`, `name`, `buildTag`
- `browserstack.local`, `browserstack.localIdentifier`
- `browserstack.playwrightVersion`, `client.playwrightVersion`
- `browserstack.debug`
- `browserstack.console`
- `browserstack.networkLogs`
- `browserstack.interactiveDebugging`

BrowserStack's support matrix changes over time; prefer their supported browsers/OS page or the Browser API instead of hardcoding version assumptions.

## Automate REST APIs

BrowserStack's Automate REST API base URL is:

```text
https://api.browserstack.com/
```

Auth is HTTP Basic auth with `username:access_key`.

Documented rate limits:

- `1600` API requests per 5 minutes per user
- `160` API requests per second per IP

### High-value endpoints

| Endpoint | Use |
|----------|-----|
| `GET /automate/plan.json` | Check current parallel capacity and queue pressure |
| `GET /automate/browsers.json` | Discover currently supported OS/browser/device combinations |
| `GET /automate/builds.json` | List recent builds |
| `PUT /automate/builds/{build_id}.json` | Rename a build |
| `DELETE /automate/builds/{build_id}.json` | Delete a build |
| `GET /automate/builds/{build-id}/sessions.json` | List sessions in a build |
| `GET /automate/sessions/{session-id}.json` | Retrieve session details and debugging links |
| `PUT /automate/sessions/{session-id}.json` | Set session status or rename a session |
| `GET /automate/sessions/{session-id}/networklogs` | Download HAR/network logs |
| `POST /automate/sessions/{session_id}/terminallogs` | Upload terminal logs |
| `DELETE /automate/sessions/{session-id}.json` | Delete a session |

### What the session API is good for

`GET /automate/sessions/{session-id}.json` returns detailed session metadata plus pre-signed URLs for debugging artifacts such as:

- dashboard links
- public share links
- console logs
- HAR/network logs
- Selenium logs
- Appium logs when relevant

That makes the session API the right place to harvest BrowserStack artifacts back into CI summaries.

### Thin Python client example

```python
from __future__ import annotations

import os

import httpx


class BrowserStackAutomateClient:
    """Small helper for the BrowserStack Automate REST API."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url="https://api.browserstack.com/automate",
            auth=(
                os.environ["BROWSERSTACK_USERNAME"],
                os.environ["BROWSERSTACK_ACCESS_KEY"],
            ),
            timeout=30.0,
        )

    def get_plan(self) -> dict[str, object]:
        response = self._client.get("/plan.json")
        response.raise_for_status()
        return response.json()

    def list_builds(self, limit: int = 10) -> list[dict[str, object]]:
        response = self._client.get("/builds.json", params={"limit": limit})
        response.raise_for_status()
        return response.json()

    def list_sessions(self, build_id: str, limit: int = 10) -> list[dict[str, object]]:
        response = self._client.get(
            f"/builds/{build_id}/sessions.json",
            params={"limit": limit},
        )
        response.raise_for_status()
        return response.json()

    def get_session(self, session_id: str) -> dict[str, object]:
        response = self._client.get(f"/sessions/{session_id}.json")
        response.raise_for_status()
        return response.json()

    def set_session_status(self, session_id: str, status: str, reason: str) -> None:
        response = self._client.put(
            f"/sessions/{session_id}.json",
            json={"status": status, "reason": reason},
        )
        response.raise_for_status()
```

Repo-specific recommendation: use the REST API to pull artifacts and capacity information around BrowserStack runs, not to replace the SDK itself.

## BrowserStack Local

BrowserStack Local is the path for testing:

- `localhost`
- staging hosts not exposed publicly
- internal services behind VPN, proxy, or firewall

Important documented behaviors:

- SDK-based config uses `browserstackLocal: true` in `browserstack.yml`.
- Direct Playwright capability mode uses `browserstack.local: "true"` and optionally `browserstack.localIdentifier`.
- `--force-local` forces all requests through the local tunnel, even when a host is publicly resolvable.
- On iOS Safari, localhost URLs are rewritten to `http://bs-local.com`.
- BrowserStack Local operates as a **TCP-level proxy**, so HTTPS and WebSockets are supported.
- The connection is persistent until explicitly closed.

That TCP-level behavior is directly relevant to NiceGUI and other websocket-heavy apps.

## MCP Server

BrowserStack also publishes an official MCP server: `@browserstack/mcp-server`.

What it is good for:

- manual web and app testing from an MCP client
- triggering or debugging automated tests from IDE/agent workflows
- BrowserStack Test Management operations

Key setup points from the README:

- Requires Node `>= 18`
- Typical local config uses:

```json
{
  "mcpServers": {
    "browserstack": {
      "command": "npx",
      "args": ["-y", "@browserstack/mcp-server@latest"],
      "env": {
        "BROWSERSTACK_USERNAME": "<username>",
        "BROWSERSTACK_ACCESS_KEY": "<access_key>"
      }
    }
  }
}
```

- BrowserStack documents both local MCP and remote MCP options.
- The **remote MCP server does not support Local Testing**; BrowserStack says to use a BrowserStack Local MCP server when localhost/VPN/firewalled targets matter.

Repo-specific inference: the MCP server is a useful operator tool for exploratory debugging and test-management workflows, but it should not be the primary execution path for the repo's CI test suite.

## Recommendation for PromptGrimoire

This section is a repo-specific inference from BrowserStack's docs and the current test architecture.

1. Keep the existing local Playwright lane authoritative for fast feedback.
2. Add BrowserStack as an **optional remote cross-browser lane** for a small smoke subset first.
3. Use the **Playwright-Pytest SDK** path before considering raw CDP integration.
4. Use **BrowserStack Local** for any CI job that points at ephemeral preview deployments, localhost, or websocket-heavy staging hosts.
5. Use the **Automate REST API** after each remote run to collect build URLs, session URLs, console/HAR logs, and plan telemetry.
6. Treat the **MCP server** as a developer-assistance surface, not as the backbone of automated execution.

The main pragmatic conclusion is: **do not port PromptGrimoire to Selenium just to use BrowserStack**. BrowserStack's current docs already support the repo's existing Playwright-plus-pytest shape.
