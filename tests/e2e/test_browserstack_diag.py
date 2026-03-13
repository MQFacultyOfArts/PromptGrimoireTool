"""Diagnostic: verify Socket.IO connects through BrowserStack Local tunnel.

Run via: uv run grimoire e2e browserstack safari -k "test_socketio_connects"

This test navigates to a NiceGUI page and checks whether the Socket.IO
WebSocket connection establishes -- the prerequisite for ALL NiceGUI
server-initiated actions (ui.navigate.to, ui.notify, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page


@pytest.mark.e2e
class TestBrowserStackDiagnostics:
    """Diagnostic tests for BrowserStack tunnel connectivity."""

    def test_socketio_connects(self, fresh_page: Page, app_server: str) -> None:
        """Verify NiceGUI Socket.IO connects through the tunnel."""
        fresh_page.goto(f"{app_server}/login")

        # Poll for Socket.IO connection for up to 15 seconds
        connected = fresh_page.evaluate(
            """() => {
            return new Promise((resolve) => {
                let attempts = 0;
                const check = () => {
                    attempts++;
                    const sio = window.socket;
                    if (sio && sio.connected) {
                        resolve({
                            connected: true,
                            transport: (
                                sio.io?.engine?.transport?.name
                                || 'unknown'
                            ),
                            attempts: attempts,
                        });
                        return;
                    }
                    if (attempts >= 75) {
                        const scripts = Array.from(
                            document.querySelectorAll('script[src]')
                        ).map(s => s.src)
                         .filter(s => s.includes('socket'));
                        resolve({
                            connected: false,
                            socketExists: !!sio,
                            socketState: sio ? {
                                connected: sio.connected,
                                disconnected: sio.disconnected,
                                id: sio.id,
                            } : null,
                            attempts: attempts,
                            scripts: scripts,
                        });
                        return;
                    }
                    setTimeout(check, 200);
                };
                check();
            });
        }"""
        )

        print("\n=== Socket.IO diagnostic ===")
        print(f"  Connected: {connected.get('connected')}")
        print(f"  Transport: {connected.get('transport', 'N/A')}")
        print(f"  Attempts: {connected.get('attempts')}")
        if not connected.get("connected"):
            print(f"  Socket exists: {connected.get('socketExists')}")
            print(f"  Socket state: {connected.get('socketState')}")
            print(f"  Socket scripts: {connected.get('scripts')}")

        # Also probe the Socket.IO polling endpoint directly
        poll_result = fresh_page.evaluate(
            """() => {
            return fetch(
                window.location.origin
                + '/_nicegui_ws/socket.io/?EIO=4&transport=polling',
                {method: 'GET'}
            ).then(r => ({
                status: r.status,
                statusText: r.statusText,
                headers: Object.fromEntries(r.headers.entries()),
                bodyPreview: null,
            })).then(async (obj) => {
                // re-fetch for body (can't read twice)
                const r2 = await fetch(
                    window.location.origin
                    + '/_nicegui_ws/socket.io/?EIO=4&transport=polling'
                );
                const text = await r2.text();
                obj.bodyPreview = text.substring(0, 200);
                return obj;
            }).catch(e => ({
                error: e.message,
                name: e.name,
            }));
        }"""
        )
        print("\n=== Socket.IO polling probe ===")
        for k, v in poll_result.items():
            print(f"  {k}: {v}")

        # Try a manual Socket.IO connection with polling-only transport
        manual_result = fresh_page.evaluate(
            """() => {
            return new Promise((resolve) => {
                const sio2 = io(window.location.origin, {
                    path: window.path_prefix
                        + '/_nicegui_ws/socket.io',
                    transports: ['polling'],
                });
                sio2.on('connect', () => {
                    resolve({
                        manual_connected: true,
                        transport: 'polling',
                        id: sio2.id,
                    });
                    sio2.disconnect();
                });
                sio2.on('connect_error', (err) => {
                    resolve({
                        manual_connected: false,
                        error: err.message,
                        type: err.type,
                        desc: String(err.description || ''),
                    });
                    sio2.disconnect();
                });
                setTimeout(() => {
                    resolve({
                        manual_connected: false,
                        error: 'timeout after 10s',
                    });
                    sio2.disconnect();
                }, 10000);
            });
        }"""
        )
        print("\n=== Manual polling-only Socket.IO ===")
        for k, v in manual_result.items():
            print(f"  {k}: {v}")

        assert connected["connected"] or manual_result.get("manual_connected"), (
            f"Socket.IO did not connect."
            f" Default: {connected}."
            f" Polling-only: {manual_result}"
        )
