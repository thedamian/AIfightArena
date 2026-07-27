"""Screenshot a page, optionally running some JS first.

    python tools/shot.py <url> <out.png> [width] [height] ["await someJs()"]

Drives headless Chrome over the DevTools protocol, so unlike `--screenshot` it
can interact with the page first - joining the lobby, clicking through a step,
waiting for a match to reach a particular state. Uses the `websockets` package
that already ships with uvicorn[standard]; nothing extra to install.
"""
from __future__ import annotations

import asyncio
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def find_chrome() -> str:
    for path in CHROME_CANDIDATES:
        if path and Path(path).exists():
            return path
    raise SystemExit("no Chrome/Chromium found")


class Page:
    def __init__(self, ws):
        self.ws = ws
        self._id = 0

    async def call(self, method: str, **params):
        self._id += 1
        await self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    async def evaluate(self, expression: str):
        result = await self.call(
            "Runtime.evaluate", expression=f"(async () => {{ {expression} }})()",
            awaitPromise=True, returnByValue=True)
        return result.get("result", {}).get("value")


async def shoot(url: str, out: Path, width: int, height: int, script: str | None) -> None:
    chrome = find_chrome()
    with tempfile.TemporaryDirectory() as profile:
        port = 9222
        proc = subprocess.Popen(
            [chrome, "--headless=new", f"--remote-debugging-port={port}",
             f"--user-data-dir={profile}", "--no-first-run", "--disable-gpu",
             f"--window-size={width},{height}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            target = None
            for _ in range(60):
                try:
                    tabs = httpx.get(f"http://127.0.0.1:{port}/json", timeout=1.0).json()
                    target = next((t for t in tabs if t["type"] == "page"), None)
                    if target:
                        break
                except Exception:                    # noqa: BLE001 - chrome still booting
                    pass
                time.sleep(0.25)
            if not target:
                raise SystemExit("chrome did not come up")

            async with websockets.connect(target["webSocketDebuggerUrl"],
                                          max_size=64 * 1024 * 1024) as ws:
                page = Page(ws)
                await page.call("Page.enable")
                await page.call("Runtime.enable")
                await page.call("Emulation.setDeviceMetricsOverride",
                                width=width, height=height,
                                deviceScaleFactor=2, mobile=False)
                await page.call("Page.navigate", url=url)
                await asyncio.sleep(2.0)

                if script:
                    value = await page.evaluate(script)
                    if value is not None:
                        print(f"  js -> {value}")
                    await asyncio.sleep(1.6)

                shot = await page.call("Page.captureScreenshot", format="png")
                out.write_bytes(base64.b64decode(shot["data"]))
                print(f"  wrote {out} ({out.stat().st_size // 1024} KB)")
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    url, out = sys.argv[1], Path(sys.argv[2])
    width = int(sys.argv[3]) if len(sys.argv) > 3 else 1440
    height = int(sys.argv[4]) if len(sys.argv) > 4 else 900
    script = sys.argv[5] if len(sys.argv) > 5 else None
    asyncio.run(shoot(url, out, width, height, script))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
