# -*- coding: utf-8 -*-
"""
Proven CDP capture script to visually verify:
1. Header at 360px (zero clipping of [X-Ray])
2. Header actions dragged/scrolled state
3. report.html mobile layout with sticky back bar
4. Updated QR modal with on-device status
"""
import asyncio
import base64
import json
import os
import subprocess
import time
import urllib.request
import websockets
from pathlib import Path

ARTIFACT_DIR = Path(r"C:\Users\iyf77\.gemini\antigravity\brain\e7b79a3d-2d4c-4535-b625-4ee21f9b979a")
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

SCENARIOS = [
    {
        "name": "fix_1_header_360px.png",
        "url": "http://localhost:5050/",
        "wait_js": "document.querySelector('.app-header') !== null",
        "viewport": {"width": 360, "height": 780},
        "desc": "360px 모바일 화면 헤더: DTC Mobile, ⚡ 온디바이스, 해설서, 공유, X-Ray 잘림 없음 검증"
    },
    {
        "name": "fix_2_header_dragged.png",
        "url": "http://localhost:5050/",
        "wait_js": "document.querySelector('.app-header') !== null",
        "viewport": {"width": 360, "height": 780},
        "action_js": "const el = document.getElementById('header-actions-bar'); if(el) el.scrollLeft = 35;",
        "desc": "헤더 액션 가로 드래그 스크롤 동작 검증"
    },
    {
        "name": "fix_3_qr_modal.png",
        "url": "http://localhost:5050/?qr=1",
        "wait_js": "document.getElementById('qr-modal-overlay').classList.contains('active')",
        "viewport": {"width": 360, "height": 780},
        "desc": "정비 현장 화면 공유 모달 (온디바이스 상태 뱃지 및 공유 목적 안내)"
    },
    {
        "name": "fix_4_report_mobile.png",
        "url": "http://localhost:5050/report.html",
        "wait_js": "document.querySelector('.mobile-back-bar') !== null",
        "viewport": {"width": 360, "height": 780},
        "desc": "해설서(엔지니어링 백서) 모바일 뷰어: 상단 진단 복귀 바 및 5대 탭 정상 렌더링"
    }
]

msg_id = 0

async def call_cdp(ws, method, params=None):
    global msg_id
    msg_id += 1
    cid = msg_id
    payload = {"id": cid, "method": method, "params": params or {}}
    await ws.send(json.dumps(payload))
    while True:
        raw = await ws.recv()
        data = json.loads(raw)
        if data.get("id") == cid:
            return data

async def capture_scenario(ws, sc):
    vp = sc.get("viewport", {"width": 360, "height": 780})
    await call_cdp(ws, "Emulation.setDeviceMetricsOverride", {
        "width": vp["width"],
        "height": vp["height"],
        "deviceScaleFactor": 2,
        "mobile": True
    })

    # Navigate
    await call_cdp(ws, "Page.navigate", {"url": sc["url"]})

    # Wait for condition or timeout
    for _ in range(40):
        await asyncio.sleep(0.2)
        res = await call_cdp(ws, "Runtime.evaluate", {"expression": sc["wait_js"], "returnByValue": True})
        val = res.get("result", {}).get("result", {}).get("value")
        if val:
            break

    # Optional action JS
    if "action_js" in sc:
        await call_cdp(ws, "Runtime.evaluate", {"expression": sc["action_js"], "returnByValue": True})
        await asyncio.sleep(0.5)

    # Extra settle time
    await asyncio.sleep(0.6)

    # Capture screenshot
    shot_res = await call_cdp(ws, "Page.captureScreenshot", {"format": "png"})
    img_b64 = shot_res["result"]["data"]

    out_file = ARTIFACT_DIR / sc["name"]
    with open(out_file, "wb") as f:
        f.write(base64.b64decode(img_b64))
    print(f"Captured {sc['name']} ({out_file.stat().st_size:,} bytes)", flush=True)

async def main():
    port = 9448
    temp_profile = Path(os.environ.get("TEMP", r"C:\Windows\Temp")) / "edge_cdp_profile_fix"
    proc = subprocess.Popen([
        EDGE_EXE,
        "--headless=new",
        "--disable-gpu",
        "--window-size=360,780",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={temp_profile}",
        "about:blank"
    ])

    ws_url = None
    for _ in range(25):
        await asyncio.sleep(0.4)
        try:
            req = urllib.request.urlopen(f"http://127.0.0.1:{port}/json")
            tabs = json.loads(req.read().decode())
            page_tabs = [t for t in tabs if t.get("type") == "page"]
            if page_tabs:
                ws_url = page_tabs[0]["webSocketDebuggerUrl"]
                break
        except Exception:
            pass

    if not ws_url:
        print("Failed to get WebSocket debugger URL!", flush=True)
        proc.terminate()
        return

    try:
        async with websockets.connect(ws_url, max_size=50*1024*1024) as ws:
            await call_cdp(ws, "Page.enable")
            for sc in SCENARIOS:
                print(f"Starting capture for {sc['name']}...", flush=True)
                await capture_scenario(ws, sc)
    finally:
        proc.terminate()
        print("CDP capture complete.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
