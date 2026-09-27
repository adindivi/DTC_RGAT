# -*- coding: utf-8 -*-
"""
Capture all 9 feature executions of DTC Knowledge Graph Mobile.
Saves high-res screenshots for visual analysis & optimization.
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

FEATURE_SCENARIOS = [
    {
        "name": "feat_1_home_initial.png",
        "url": "http://localhost:5050/",
        "wait_js": "document.querySelector('.app-header') !== null",
        "desc": "기능 1: 초기 대기 화면 (DTC 검색 입력, 추천 프리셋 칩, 빈 상태 안내)"
    },
    {
        "name": "feat_2_autocomplete.png",
        "url": "http://localhost:5050/?ac=C128",
        "wait_js": "document.querySelectorAll('.ac-item').length > 0",
        "desc": "기능 2: 스마트 자동완성 (실시간 일치 하이라이트 및 배경 딤)"
    },
    {
        "name": "feat_3_ranking_diagnosis.png",
        "url": "http://localhost:5050/?codes=B100552,C128387,C164387,C166987&tab=ranking",
        "wait_js": "document.querySelectorAll('.rc-card-mobile').length > 0",
        "desc": "기능 3: 1순위 원인 랭킹 카드 (최우선 점검 뱃지, 부품 가이드, 원인 기여도)"
    },
    {
        "name": "feat_4_knowledge_graph.png",
        "url": "http://localhost:5050/?codes=B100552,C128387,C164387,C166987&tab=map",
        "wait_js": "window.network && window.network.body && Object.keys(window.network.body.nodes).length > 0",
        "action_js": "restoreMobileStyles(); fitMobileNetwork();",
        "desc": "기능 4: 지식 그래프 캔버스 (상단 고정 토폴로지 바, 컴팩트 HW_MAP 버튼 및 2-Hop GNN 추론망)"
    },
    {
        "name": "feat_4b_hw_map_toggled.png",
        "url": "http://localhost:5050/?codes=B100552,C128387,C164387,C166987&tab=map",
        "wait_js": "window.network && window.network.body && Object.keys(window.network.body.nodes).length > 0",
        "action_js": "restoreMobileStyles(); toggleMobileHwMap();",
        "desc": "기능 4b: HW_MAP 토글 (노드 위치 100% 동결 및 DTC-커넥터 직결 검증선만 숨김)"
    },
    {
        "name": "feat_5_graph_xray.png",
        "url": "http://localhost:5050/?codes=B100552,C128387,C164387,C166987&tab=map&focus=FLRS_MAIN51",
        "wait_js": "window.network && window.network.body && Object.keys(window.network.body.nodes).length > 0",
        "action_js": "applyMobileXRay('FLRS_MAIN51'); fitMobileNetwork();",
        "desc": "기능 5: X-Ray 결함 전파 경로 모드 (고대비 딤 및 인과 전파 경로)"
    },
    {
        "name": "feat_6_dtc_details.png",
        "url": "http://localhost:5050/?codes=B100552,C128387,C164387,C166987&tab=dtc",
        "wait_js": "document.querySelectorAll('.dtc-card-mobile').length > 0",
        "desc": "기능 6: DTC 상세 분석 탭 (계통별 시맨틱 컬러 액센트 및 ISO 서브타입)"
    },
    {
        "name": "feat_7_latent_sheet.png",
        "url": "http://localhost:5050/?codes=B100552,C128387,C164387,C166987&tab=map&sheet=latent&focus=FLRS_MAIN51",
        "wait_js": "document.getElementById('latent-sheet-overlay').classList.contains('active')",
        "action_js": "filterLatentCategory('CONN')",
        "desc": "기능 7: 64D 잠재공간 바텀시트 (안전영역 패딩 및 계통 필터 토글)"
    },
    {
        "name": "feat_8_qr_sharing.png",
        "url": "http://localhost:5050/?codes=B100552,C128387,C164387,C166987&qr=1",
        "wait_js": "document.getElementById('qr-modal-overlay').classList.contains('active')",
        "action_js": "copyMobileUrl()",
        "desc": "기능 8: 정비 현장 화면 공유 모달 (촉각 피드백 복사 완료 상태)"
    },
    {
        "name": "feat_9_offline_report.png",
        "url": "http://localhost:5050/report.html",
        "wait_js": "document.querySelector('.mobile-back-bar') !== null",
        "desc": "기능 9: 오프라인 해설서 백서 뷰어 (상단 복귀 바 및 5대 세그먼트 탭)"
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
    await asyncio.sleep(0.8)

    # Capture screenshot
    shot_res = await call_cdp(ws, "Page.captureScreenshot", {"format": "png"})
    img_b64 = shot_res["result"]["data"]

    out_file = ARTIFACT_DIR / sc["name"]
    with open(out_file, "wb") as f:
        f.write(base64.b64decode(img_b64))
    print(f"Captured {sc['name']} ({out_file.stat().st_size:,} bytes)", flush=True)

async def main():
    port = 9470
    temp_profile = Path(os.environ.get("TEMP", r"C:\Windows\Temp")) / "edge_cdp_profile_all_features"
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
            for sc in FEATURE_SCENARIOS:
                print(f"Starting capture for {sc['name']}...", flush=True)
                await capture_scenario(ws, sc)
    finally:
        proc.terminate()
        print("All 9 feature captures complete.", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
