# -*- coding: utf-8 -*-
"""
DTC 지식 그래프 진단 웹 애플리케이션
- 단일 책임 원칙(SRP) 준수 및 데드 코드/중복 제거
- 표준 에러 로깅 (콘솔 및 webapp.log)
- 사용자 친화적 예외 안내 모달 팝업 및 상태별 토스트 시스템
"""
import argparse
import logging
import re
import sys
import threading
import time
import webbrowser
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify

import config
from graph_service import KnowledgeGraphService

# ══════════════════════════════════════════════════════════════
# 1. 로깅 시스템 설정 (표준 포맷터 및 콘솔/파일 핸들러)
# ══════════════════════════════════════════════════════════════
logger = logging.getLogger("DTC_RGAT")
logger.setLevel(logging.INFO)

# 기존 핸들러 중복 방지
if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러 (UTF-8 인코딩)
    file_handler = logging.FileHandler(str(config.LOG_FILE_PATH), encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# ══════════════════════════════════════════════════════════════
# 2. 데이터 서비스 초기화
# ══════════════════════════════════════════════════════════════
try:
    graph_service = KnowledgeGraphService(
        graph_path=config.GRAPH_JSON_PATH,
        embed_path=config.EMBED_NPY_PATH,
        alpha=config.DEFAULT_ALPHA,
        beta=config.DEFAULT_BETA,
        top_k=config.DEFAULT_TOP_K,
    )
    logger.info("KnowledgeGraphService loaded successfully.")
except Exception as e:
    logger.critical(f"Failed to initialize KnowledgeGraphService: {e}", exc_info=True)
    sys.exit(1)

# ══════════════════════════════════════════════════════════════
# 3. Flask 애플리케이션 정의
# ══════════════════════════════════════════════════════════════
app = Flask(__name__)

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route("/report")
@app.route("/guide")
def report():
    """최종 완결 정리 보고서 제공 라우트"""
    report_path = Path(__file__).resolve().parent / "최종정리.html"
    if report_path.exists():
        with open(report_path, "r", encoding="utf-8") as f:
            return f.read()
    return "Report not found", 404

@app.route("/api/search")
def search():
    """DTC 코드 자동완성 검색 API"""
    try:
        query = request.args.get("q", "").strip()
        hits = graph_service.search_dtc(query, limit=20)
        return jsonify(hits)
    except Exception as e:
        logger.error(f"Error during search with query '{request.args.get('q')}': {e}", exc_info=True)
        return jsonify([]), 500

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """
    DTC 코드 목록 분석 API
    - 입력값 유효성 검증 (400 Bad Request 방어)
    - 알 수 없는 코드 검출 시 명확한 경고 로깅
    """
    start_time = time.perf_counter()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        logger.warning(f"Invalid JSON payload received from {request.remote_addr}")
        return jsonify({
            "error": "요청 형식이 잘못되었습니다. 올바른 JSON 데이터를 전달하세요.",
            "detail": "JSON Object with 'codes' array expected"
        }), 400

    raw_codes = data.get("codes", [])
    if not isinstance(raw_codes, list):
        return jsonify({
            "error": "'codes' 필드는 배열(Array) 형태여야 합니다.",
            "detail": f"Received type: {type(raw_codes).__name__}"
        }), 400

    # 유효한 문자열 코드 추출 및 정제 (쉼표/공백 다중 입력 방어)
    codes = []
    for c in raw_codes:
        for sub_c in re.split(r"[\s,;\n\r\t]+", str(c)):
            clean_c = sub_c.upper().strip()
            if clean_c and clean_c not in codes:
                codes.append(clean_c)
    if not codes:
        return jsonify({
            "error": "분석할 DTC 코드를 1개 이상 입력해주세요.",
            "detail": "No valid non-empty DTC codes provided"
        }), 400

    logger.info(f"Incoming analysis request for {len(codes)} codes: {codes}")

    try:
        use_mask = bool(data.get("topology_mask", True))
        result = graph_service.analyze(codes, topology_mask=use_mask)
        elapsed = (time.perf_counter() - start_time) * 1000

        if result.get("unknown"):
            logger.warning(f"Unregistered DTC codes detected in request: {result['unknown']}")

        if result.get("error"):
            logger.warning(f"Analysis completed with validation error: {result['error']}")
            return jsonify(result), 400

        top1 = result["results"][0]["name"] if result.get("results") else "None"
        logger.info(f"Analysis completed in {elapsed:.1f}ms. Top root-cause candidate: {top1}")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Unexpected error while analyzing codes {codes}: {e}", exc_info=True)
        return jsonify({
            "error": "서버 내부 처리 중 오류가 발생했습니다.",
            "detail": str(e)
        }), 500

# ══════════════════════════════════════════════════════════════
# 4. 프론트엔드 HTML 템플릿 (모달 팝업 및 최적화 UI)
# ══════════════════════════════════════════════════════════════
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DTC 지식 그래프 분석기</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/dist/vis-network.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/dist/dist/vis-network.min.css">
<style>
:root{
  --primary:#0071e3; --link:#0066cc; --brand-dark:#000000; --fog:#f5f5f7; --surface:#ffffff;
  --fg:#1d1d1f; --muted:#6e6e73; --secondary:#515154; --on-primary:#ffffff;
  --hairline:rgba(0,0,0,.08); --hairline-strong:rgba(0,0,0,.14);
  --danger:#ff3b30; --warning:#ff9500; --success:#34c759;
}
*{box-sizing:border-box;margin:0;padding:0;}
html,body{height:100%;overflow:hidden;}
body{
  font-family:"SF Pro Text",-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  background:var(--fog);color:var(--fg);display:flex;flex-direction:column;
  font-size:14px;line-height:1.4;-webkit-font-smoothing:antialiased;
}
.display{font-family:"SF Pro Display",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}

/* ── 헤더 ── */
header{background:var(--surface);border-bottom:1px solid var(--hairline);padding:12px 20px;display:flex;align-items:center;gap:12px;flex-shrink:0;}
.logo{font-size:15px;font-weight:600;color:var(--fg);white-space:nowrap;letter-spacing:-.1px;}
.logo .mark{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--primary);margin-right:7px;vertical-align:middle;}
.input-area{display:flex;flex:1;gap:8px;align-items:center;flex-wrap:wrap;position:relative;}
.tag-input-wrap{flex:1;min-width:260px;background:var(--fog);border:1px solid var(--hairline-strong);border-radius:10px;padding:6px 10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;cursor:text;min-height:40px;}
.tag-input-wrap:focus-within{border-color:var(--primary);box-shadow:0 0 0 3px rgba(0,113,227,.12);}
.dtc-tag{background:rgba(0,113,227,.1);border:1px solid rgba(0,113,227,.25);color:var(--primary);padding:3px 10px;border-radius:980px;font-size:12px;font-weight:600;display:flex;align-items:center;gap:5px;}
.dtc-tag .rm{cursor:pointer;color:var(--muted);width:15px;height:15px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;transition:all .15s ease;margin-left:2px;}
.dtc-tag .rm:hover{background:rgba(255,59,48,.12);color:var(--danger);}
.tag-input-wrap input{border:none;background:transparent;color:var(--fg);font-size:13px;outline:none;min-width:140px;flex:1;font-family:inherit;}
.tag-input-wrap input::placeholder{color:var(--muted);}
.btn-analyze{background:var(--primary);color:var(--on-primary);border:none;border-radius:980px;padding:10px 22px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;transition:background .15s ease;font-family:inherit;display:inline-flex;align-items:center;justify-content:center;gap:6px;}
.btn-analyze:hover{background:#0077ed;}
.btn-analyze:disabled{background:#c7c7cc;color:#8e8e93;cursor:not-allowed;}
.btn-clear{background:transparent;color:var(--link);border:1px solid var(--link);border-radius:980px;padding:9px 16px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;transition:background .15s ease;display:inline-flex;align-items:center;justify-content:center;gap:6px;}
.btn-clear:hover{background:rgba(0,102,204,.06);}

/* 자동완성 드롭다운 */
.autocomplete{position:absolute;top:100%;left:0;right:80px;background:var(--surface);border:1px solid var(--hairline-strong);border-radius:12px;z-index:999;max-height:220px;overflow-y:auto;display:none;margin-top:6px;box-shadow:0 6px 16px rgba(0,0,0,.08);}
.ac-item{padding:9px 14px;cursor:pointer;font-size:13px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--hairline);}
.ac-item:last-child{border-bottom:none;}
.ac-item:hover,.ac-item.active{background:var(--fog);}
.ac-code{color:var(--primary);font-weight:600;min-width:80px;font-family:monospace;}
.ac-ecu{color:var(--secondary);font-size:11px;min-width:70px;font-weight:600;}
.ac-desc{color:var(--muted);font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}

/* 예시 버튼 바 */
.examples-bar{background:var(--surface);border-bottom:1px solid var(--hairline);padding:8px 20px;display:flex;align-items:center;gap:8px;flex-shrink:0;}
.examples{display:flex;gap:6px;flex-wrap:wrap;}
.ex-btn{background:var(--surface);border:1px solid var(--hairline-strong);color:var(--secondary);border-radius:980px;padding:6px 14px;font-size:12px;font-weight:500;cursor:pointer;transition:all .15s ease;font-family:inherit;}
.ex-btn:hover{border-color:var(--primary);color:var(--primary);}

/* ── 메인 레이아웃 ── */
.main{display:flex;flex:1;overflow:hidden;}
.left-panel{width:310px;min-width:310px;background:var(--surface);border-right:1px solid var(--hairline);display:flex;flex-direction:column;overflow:hidden;}
.tabs-wrap{display:flex;border-bottom:1px solid var(--hairline);}
.tab-btn{flex:1;padding:11px;text-align:center;font-size:12px;font-weight:600;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;display:flex;align-items:center;justify-content:center;gap:6px;}
.tab-btn.active{color:var(--primary);border-bottom-color:var(--primary);}
.panel-body{flex:1;overflow-y:auto;padding:12px;}
.panel-body::-webkit-scrollbar{width:4px;}
.panel-body::-webkit-scrollbar-thumb{background:var(--hairline-strong);border-radius:2px;}

/* 근본원인 카드 */
.rc-card{background:var(--surface);border-radius:12px;padding:12px 14px;margin-bottom:8px;cursor:pointer;border:1px solid var(--hairline-strong);transition:border-color .15s ease,background .15s ease;}
.rc-card:hover{border-color:var(--primary);}
.rc-card.rank1{border-color:var(--primary);background:rgba(0,113,227,.04);}
.rc-rank{font-size:11px;font-weight:600;color:var(--muted);margin-bottom:4px;}
.rc-rank.r1{color:var(--primary);}
.rc-name{font-size:13px;font-weight:600;word-break:break-all;margin-bottom:6px;color:var(--fg);}
.rc-bar-wrap{display:flex;align-items:center;gap:8px;}
.rc-bar{flex:1;background:var(--fog);border-radius:4px;height:6px;overflow:hidden;}
.rc-bar-fill{height:100%;border-radius:4px;background:var(--primary);transition:width .6s ease;}
.rc-score{font-size:11px;font-weight:600;color:var(--primary);min-width:36px;text-align:right;}
.rc-dots{display:flex;gap:3px;margin-top:6px;flex-wrap:wrap;}
.rc-dot{font-size:10px;padding:2px 7px;border-radius:980px;font-weight:600;}
.rc-dot.hit{background:rgba(0,113,227,.1);color:var(--primary);}
.rc-dot.miss{background:var(--fog);color:var(--muted);}
.rc-ecu{font-size:10px;color:var(--muted);margin-top:4px;}

/* DTC 정보 카드 */
.dtc-info-card{background:var(--surface);border-radius:12px;padding:10px 12px;margin-bottom:6px;border:1px solid var(--hairline-strong);border-left:3px solid var(--primary);}
.dtc-code{font-size:13px;font-weight:600;color:var(--fg);font-family:monospace;}
.dtc-cat{font-size:10px;color:var(--muted);margin:2px 0;}
.dtc-ecu{font-size:11px;color:var(--secondary);font-weight:600;}
.dtc-desc{font-size:11px;color:var(--muted);margin-top:3px;}

/* ── 중앙: 마인드맵 ── */
.map-area{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0;min-height:0;background:#f8fafc;}
.map-toolbar{padding:8px 16px;background:var(--surface);border-bottom:1px solid var(--hairline);display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.map-toolbar span{font-size:12px;color:var(--muted);}
.tb-btn{background:var(--surface);border:1px solid var(--hairline-strong);color:var(--fg);border-radius:980px;padding:6px 14px;font-size:12px;font-weight:500;cursor:pointer;font-family:inherit;transition:all .15s ease;display:inline-flex;align-items:center;justify-content:center;gap:6px;}
.tb-btn:hover{border-color:var(--primary);color:var(--primary);}
.legend{display:flex;gap:12px;flex-wrap:wrap;margin-left:auto;}
.leg-item{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);font-weight:500;}
.leg-pill{width:14px;height:8px;border-radius:980px;display:inline-block;}
#network{flex:1;}

.state-msg{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:8px;color:var(--muted);text-align:center;padding:20px;}
.state-msg p{font-size:13px;}

/* ── 로딩 오버레이 ── */
.loading{position:fixed;inset:0;background:rgba(245,245,247,.85);display:flex;align-items:center;justify-content:center;z-index:9999;flex-direction:column;gap:12px;display:none;}
.spinner{width:30px;height:30px;border:3px solid var(--hairline-strong);border-top-color:var(--primary);border-radius:50%;animation:spin .8s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}

/* ── 사용자 친화적 모달 팝업 ── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;z-index:10000;opacity:0;pointer-events:none;transition:opacity .2s ease;}
.modal-overlay.active{opacity:1;pointer-events:auto;}
.modal-card{background:var(--surface);width:90%;max-width:440px;border-radius:16px;padding:24px;box-shadow:0 12px 32px rgba(0,0,0,.15);display:flex;flex-direction:column;gap:16px;}
.modal-header{display:flex;align-items:center;gap:10px;}
.modal-icon{display:flex;align-items:center;justify-content:center;}
.modal-title{font-size:16px;font-weight:600;color:var(--fg);flex:1;}
.modal-close{background:none;border:none;color:var(--muted);cursor:pointer;padding:6px;border-radius:50%;display:flex;align-items:center;justify-content:center;transition:all .15s ease;}
.modal-close:hover{background:var(--fog);color:var(--fg);}
.modal-body{font-size:13px;color:var(--secondary);line-height:1.5;}
.modal-highlight-box{background:var(--fog);border:1px solid var(--hairline-strong);border-radius:8px;padding:10px 12px;margin-top:8px;font-family:monospace;color:var(--danger);font-size:12px;word-break:break-all;}
.modal-footer{display:flex;gap:8px;justify-content:flex-end;margin-top:6px;}
.modal-btn{padding:8px 18px;border-radius:980px;font-size:13px;font-weight:600;cursor:pointer;font-family:inherit;border:none;transition:all .15s ease;}
.modal-btn.primary{background:var(--primary);color:#fff;}
.modal-btn.primary:hover{background:#0077ed;}
.modal-btn.secondary{background:var(--fog);color:var(--fg);border:1px solid var(--hairline-strong);}
.modal-btn.secondary:hover{background:#e8e8ed;}

/* ── 상태별 토스트 ── */
.toast-container{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);display:flex;flex-direction:column;gap:8px;z-index:9998;pointer-events:none;}
.toast{background:var(--fg);color:#fff;padding:10px 20px;border-radius:980px;font-size:13px;font-weight:500;opacity:0;transform:translateY(10px);transition:all .25s ease;display:flex;align-items:center;gap:8px;}
.toast.show{opacity:1;transform:translateY(0);}
.toast.warn{background:#ff9500;}
.toast.error{background:#ff3b30;}
.toast.success{background:#34c759;}
</style>
</head>
<body>

<!-- 로딩 -->
<div class="loading" id="loading">
  <div class="spinner"></div>
  <p style="font-size:13px;color:var(--secondary);">RGAT 링크 분석 중...</p>
</div>

<!-- 사용자 친화적 알림 모달 -->
<div class="modal-overlay" id="app-modal">
  <div class="modal-card">
    <div class="modal-header">
      <div class="modal-icon" id="modal-icon"></div>
      <h3 class="modal-title" id="modal-title">알림</h3>
      <button class="modal-close" onclick="closeModal()" aria-label="닫기">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>
    </div>
    <div class="modal-body" id="modal-body"></div>
    <div class="modal-footer" id="modal-footer">
      <button class="modal-btn primary" onclick="closeModal()">확인</button>
    </div>
  </div>
</div>

<!-- 토스트 컨테이너 -->
<div class="toast-container" id="toast-wrap"></div>

<!-- 헤더 -->
<header>
  <div class="logo display"><span class="mark"></span>DTC Knowledge Graph</div>
  <div class="input-area">
    <div class="tag-input-wrap" id="tag-wrap" onclick="document.getElementById('dtc-input').focus()">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--muted);flex-shrink:0;margin-left:2px;"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
      <input id="dtc-input" placeholder="DTC 코드 입력 (예: C136887, Enter 추가)" autocomplete="off" spellcheck="false">
    </div>
    <div class="autocomplete" id="ac-dropdown"></div>
    <button class="btn-analyze" id="btn-analyze" onclick="doAnalyze()">분석하기</button>
    <button class="btn-clear" onclick="clearAll()">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path></svg>
      초기화
    </button>
    <a href="/report" target="_blank" style="text-decoration:none;">
      <button class="btn-clear" style="color:var(--primary);font-weight:700;">
        원리해설서
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="7" y1="17" x2="17" y2="7"></line><polyline points="7 7 17 7 17 17"></polyline></svg>
      </button>
    </a>
  </div>
</header>

<!-- 예시 버튼 바 -->
<div class="examples-bar">
  <span style="font-size:11px;color:var(--muted);font-weight:600;">예시</span>
  <div class="examples">
    <button class="ex-btn" style="border-color:#2563eb;color:#2563eb;font-weight:700;" onclick="setExample(['B100552','C128387','C164387','C166987'])">ACU_B 연쇄 고장 (4개 제어기)</button>
    <button class="ex-btn" onclick="setExample(['C136887','B160300','C128387','U029387'])">B-CAN 통신 다발</button>
    <button class="ex-btn" onclick="setExample(['C162887','C161487','C128387','C161C86'])">C-CAN 관련 다발</button>
    <button class="ex-btn" onclick="setExample(['B160300','C110216','C110117'])">배터리 전원 관련</button>
    <button class="ex-btn" onclick="setExample(['C136887','C136987','C137087','C137187'])">초음파 센서 다발</button>
  </div>
</div>

<!-- 메인 레이아웃 -->
<div class="main">
  <!-- 좌측 패널 -->
  <div class="left-panel">
    <div class="tabs-wrap">
      <div id="tab-rc" class="tab-btn active" onclick="switchTab('rc')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
        근본원인 순위
      </div>
      <div id="tab-dtc" class="tab-btn" onclick="switchTab('dtc')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
        DTC 정보
      </div>
    </div>
    <div class="panel-body" id="panel-rc">
      <div style="color:var(--muted);font-size:13px;margin-top:20px;text-align:center;">DTC 코드를 입력하고<br>분석하기를 눌러주세요</div>
    </div>
    <div class="panel-body" id="panel-dtc" style="display:none;">
      <div style="color:var(--muted);font-size:13px;margin-top:20px;text-align:center;">DTC 코드를 입력하고<br>분석하기를 눌러주세요</div>
    </div>
  </div>

  <!-- 중앙 마인드맵 -->
  <div class="map-area">
    <div class="map-toolbar">
      <button class="tb-btn" onclick="fitNetwork()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"></polyline><polyline points="9 21 3 21 3 15"></polyline><line x1="21" y1="3" x2="14" y2="10"></line><line x1="3" y1="21" x2="10" y2="14"></line></svg>
        전체 보기
      </button>
      <button class="tb-btn" id="layout-btn" onclick="toggleLayout()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"></line><circle cx="18" cy="6" r="3"></circle><circle cx="6" cy="18" r="3"></circle><path d="M18 9a9 9 0 0 1-9 9"></path></svg>
        <span>계층형 마인드맵</span>
      </button>
      <button class="tb-btn" onclick="togglePhysics()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>
        물리엔진 켜기/끄기
      </button>
      <span id="node-count-info">노드 0개 · 엣지 0개</span>
      <div class="legend">
        <div class="leg-item"><div class="leg-pill" style="background:#fee2e2;border:1.5px solid #f87171;"></div>증상 DTC</div>
        <div class="leg-item"><div class="leg-pill" style="background:#ffedd5;border:1.5px solid #fb923c;"></div>담당 ECU</div>
        <div class="leg-item"><div class="leg-pill" style="background:#e0f2fe;border:1.5px solid #7dd3fc;"></div>커넥터</div>
        <div class="leg-item"><div class="leg-pill" style="background:#1e293b;border:1.5px solid #0f172a;"></div>#1 근본원인</div>
        <div class="leg-item"><div style="width:16px;height:0;border-top:2px solid #8e8e93;"></div>SW_LOGIC</div>
        <div class="leg-item"><div style="width:16px;height:0;border-top:2px solid #0071e3;"></div>검증 배선</div>
        <div class="leg-item"><div style="width:16px;height:0;border-top:2px dashed #8e8e93;"></div>추론 배선</div>
      </div>
    </div>
    <div id="network-wrap" style="flex:1;position:relative;min-height:0;">
      <div class="state-msg" id="state-msg" style="position:absolute;inset:0;display:flex;">
        <div style="width:48px;height:48px;border-radius:14px;background:rgba(0,113,227,0.06);border:1px solid rgba(0,113,227,0.14);display:flex;align-items:center;justify-content:center;margin-bottom:6px;">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <line x1="6" y1="3" x2="6" y2="15"></line>
            <circle cx="18" cy="6" r="3"></circle>
            <circle cx="6" cy="18" r="3"></circle>
            <path d="M18 9a9 9 0 0 1-9 9"></path>
          </svg>
        </div>
        <p style="font-weight:600;color:var(--fg);font-size:14px;">DTC 진단 코드를 입력하고 분석하세요</p>
        <p style="font-size:12px;color:var(--muted);">상단 예시 버튼을 클릭하면 3단계 계층 마인드맵이 즉시 펼쳐집니다</p>
      </div>
      <div id="network" style="position:absolute;inset:0;display:none;"></div>
    </div>
  </div>
</div>

<script>
let tags = [];
let acData = [];
let acIdx  = -1;
let network = null;
let physicsOn = false;
let hierarchicalOn = true;
let lastResult = null;

// ── 탭 전환 ──────────────────────────────────────────────────
function switchTab(t) {
  document.getElementById('tab-rc').className  = 'tab-btn' + (t==='rc' ? ' active' : '');
  document.getElementById('tab-dtc').className = 'tab-btn' + (t==='dtc' ? ' active' : '');
  document.getElementById('panel-rc').style.display  = t==='rc'  ? 'block' : 'none';
  document.getElementById('panel-dtc').style.display = t==='dtc' ? 'block' : 'none';
}

// ── 태그 입력 및 관리 ──────────────────────────────────────────
const inp = document.getElementById('dtc-input');
const wrap = document.getElementById('tag-wrap');
const acd  = document.getElementById('ac-dropdown');

function addTag(inputStr) {
  if (!inputStr) return;
  // 쉼표(,), 세미콜론(;), 공백, 줄바꿈, 탭 등으로 다중 코드 분리
  const rawCodes = inputStr.split(/[\s,;\n\r\t]+/);
  rawCodes.forEach(c => {
    const code = c.toUpperCase().trim();
    if (code && !tags.includes(code)) {
      tags.push(code);
      const span = document.createElement('span');
      span.className = 'dtc-tag';
      span.dataset.code = code;
      span.innerHTML = `${code} <span class="rm" onclick="removeTag('${code}')"><svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></span>`;
      wrap.insertBefore(span, inp);
    }
  });
  inp.value = '';
  closeAC();
}

function removeTag(code) {
  tags = tags.filter(t => t !== code);
  document.querySelectorAll('.dtc-tag').forEach(el => {
    if (el.dataset.code === code) el.remove();
  });
}

function clearAll() {
  tags = [];
  document.querySelectorAll('.dtc-tag').forEach(el => el.remove());
  inp.value = '';
  closeAC();
  document.getElementById('panel-rc').innerHTML = '<div style="color:var(--muted);font-size:13px;margin-top:20px;text-align:center;">DTC 코드를 입력하고<br>분석하기를 눌러주세요</div>';
  document.getElementById('panel-dtc').innerHTML = '<div style="color:var(--muted);font-size:13px;margin-top:20px;text-align:center;">DTC 코드를 입력하고<br>분석하기를 눌러주세요</div>';
  document.getElementById('state-msg').style.display = 'flex';
  document.getElementById('network').style.display = 'none';
  document.getElementById('node-count-info').textContent = '노드 0개 · 엣지 0개';
  if (network) { network.destroy(); network = null; }
  lastResult = null;
}

function setExample(codes) {
  clearAll();
  codes.forEach(addTag);
  doAnalyze();
}

// 자동완성 및 다중 입력 감지
let acTimer = null;
inp.addEventListener('input', () => {
  clearTimeout(acTimer);
  const q = inp.value.trim();
  // 쉼표나 세미콜론이 포함되어 있으면 즉시 태그들로 자동 분리
  if (q.includes(',') || q.includes(';')) {
    addTag(q);
    return;
  }
  if (q.length < 1) { closeAC(); return; }
  acTimer = setTimeout(async () => {
    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      acData = await res.json();
      renderAC();
    } catch(err) {
      console.error("Autocomplete failed:", err);
    }
  }, 120);
});

// 복사 붙여넣기로 여러 개 코드가 들어올 때 자동 분리 처리
inp.addEventListener('paste', e => {
  const pasteData = (e.clipboardData || window.clipboardData).getData('text');
  if (pasteData && /[\s,;\n\r\t]/.test(pasteData)) {
    e.preventDefault();
    addTag(pasteData);
  }
});

inp.addEventListener('keydown', e => {
  if (e.key === ',' || e.key === ';') {
    e.preventDefault();
    if (inp.value.trim()) {
      addTag(inp.value.trim());
    }
    return;
  }
  if (e.key === 'ArrowDown') { acIdx = Math.min(acIdx+1, acData.length-1); renderAC(); e.preventDefault(); }
  else if (e.key === 'ArrowUp') { acIdx = Math.max(acIdx-1, -1); renderAC(); e.preventDefault(); }
  else if (e.key === 'Enter') {
    e.preventDefault();
    if (acIdx >= 0 && acData[acIdx]) { addTag(acData[acIdx].code); acIdx=-1; }
    else if (inp.value.trim()) { addTag(inp.value.trim()); }
    else if (tags.length > 0) doAnalyze();
  } else if (e.key === 'Backspace' && !inp.value && tags.length) {
    removeTag(tags[tags.length-1]);
  } else if (e.key === 'Escape') closeAC();
});

function renderAC() {
  if (!acData.length) { closeAC(); return; }
  acd.style.display = 'block';
  acd.innerHTML = acData.map((d,i) =>
    `<div class="ac-item${i===acIdx?' active':''}" onmousedown="addTag('${d.code}')">
      <span class="ac-code">${d.code}</span>
      <span class="ac-ecu">${d.ecu}</span>
      <span class="ac-desc">${d.desc}</span>
    </div>`).join('');
}

function closeAC() { acd.style.display='none'; acData=[]; acIdx=-1; }
document.addEventListener('click', e => { if (!wrap.contains(e.target)) closeAC(); });

// ── 분석 및 에러 핸들링 ───────────────────────────────────────
async function doAnalyze() {
  if (!tags.length) {
    showToast('DTC 코드를 1개 이상 입력하세요.', 'warn');
    return;
  }
  document.getElementById('loading').style.display = 'flex';
  document.getElementById('btn-analyze').disabled = true;

  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({codes: tags})
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      handleApiError(data);
      return;
    }

    // 알 수 없는 미등록 코드가 일부 포함된 경우 사용자 친화적 팝업 안내
    if (data.unknown && data.unknown.length > 0) {
      showUnknownCodesModal(data.unknown, data);
    }

    lastResult = data;
    renderResult(data);
    showToast('분석이 성공적으로 완료되었습니다.', 'success');

  } catch(e) {
    showModal({
      title: '네트워크 연결 오류',
      type: 'error',
      body: `서버와 통신할 수 없습니다.<br><small style="color:var(--muted);">${e.message}</small>`,
      confirmText: '확인'
    });
  } finally {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('btn-analyze').disabled = false;
  }
}

function handleApiError(data) {
  if (data.unknown && data.unknown.length > 0) {
    showModal({
      title: '미등록 DTC 코드 안내',
      type: 'warn',
      body: `입력하신 다음 코드는 지식 그래프 마스터 데이터에 등록되어 있지 않습니다:
             <div class="modal-highlight-box">${data.unknown.join(', ')}</div>
             <p style="margin-top:8px;">입력창의 자동완성 추천 목록에서 올바른 표준 코드를 선택해주세요.</p>`,
      confirmText: '확인'
    });
  } else {
    showModal({
      title: '분석 요청 실패',
      type: 'error',
      body: `<p>${data.error || '요청을 처리할 수 없습니다.'}</p>${data.detail ? `<div class="modal-highlight-box">${data.detail}</div>` : ''}`,
      confirmText: '확인'
    });
  }
}

function showUnknownCodesModal(unknownCodes, validData) {
  showModal({
    title: '미등록 코드 안내',
    type: 'info',
    body: `다음 코드는 마스터 데이터에 없어 분석에서 제외되었습니다:
           <div class="modal-highlight-box">${unknownCodes.join(', ')}</div>
           <p style="margin-top:8px;">나머지 유효한 <strong>${validData.dtc_info.length}개 코드</strong>로 정상 분석을 수행했습니다.</p>`,
    confirmText: '확인'
  });
}

// ── 결과 렌더링 ───────────────────────────────────────────────
function renderResult(data) {
  renderRCPanel(data);
  renderDTCPanel(data);
  buildNetwork(data);
  document.getElementById('node-count-info').textContent =
    `노드 ${data.vis_nodes.length}개 · 엣지 ${data.vis_edges.length}개 · 분석 DTC ${data.dtc_info.length}개`;
}

function renderRCPanel(data) {
  const top = data.results[0];
  const n   = data.dtc_info.length;
  let html = '';
  if (top) {
    const vbadge = top.verified ? ' <span style="font-size:10px;background:rgba(0,113,227,.1);color:var(--primary);padding:2px 8px;border-radius:980px;font-weight:600;display:inline-flex;align-items:center;gap:3px;"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><polyline points="9 12 11 14 15 10"></polyline></svg>마스터 검증</span>' : '';
    html += `<div style="background:rgba(0,113,227,.05);border:1px solid rgba(0,113,227,.2);border-radius:12px;padding:12px 14px;margin-bottom:12px;">
      <div style="font-size:10px;font-weight:600;color:var(--primary);text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;">1순위 근본원인 후보</div>
      <div style="font-size:14px;font-weight:600;word-break:break-all;color:var(--fg);">${top.name}${vbadge}</div>
      <div style="font-size:12px;color:var(--muted);margin-top:4px;">${top.n_hit}/${n}개 DTC 계통 연결${top.verified ? ' · 마스터 직접 매핑' : ' · 점수 ' + top.final_score.toFixed(3)}</div>
    </div>`;
  }
  data.results.forEach(r => {
    const cls = r.rank===1 ? 'rank1' : '';
    const rnk = r.rank===1 ? 'r1' : '';
    const dots = data.dtc_info.map(d =>
      `<span class="rc-dot ${r.hit_codes.includes(d.code)?'hit':'miss'}">${d.code}</span>`).join('');
    const vmark = r.verified ? '<span style="font-size:10px;background:rgba(0,113,227,.1);color:var(--primary);padding:1px 7px;border-radius:980px;margin-left:6px;font-weight:600;display:inline-flex;align-items:center;gap:3px;"><svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><polyline points="9 12 11 14 15 10"></polyline></svg>검증</span>' : '';
    const reachBadge = (!r.verified && r.is_reachable) ? '<span style="font-size:10px;background:rgba(52,199,89,.12);color:#2e7d32;padding:1px 7px;border-radius:980px;margin-left:6px;font-weight:600;">배선일치</span>' : '';
    const scoreStr = r.verified ? '<span style="font-size:11px;color:var(--primary);font-weight:600;">마스터 직접 매핑</span>' : r.final_score.toFixed(3);
    html += `<div class="rc-card ${cls}" onclick="focusConn('${r.conn_id}')">
      <div class="rc-rank ${rnk}">#${r.rank}  ${r.location||''}</div>
      <div class="rc-name">${r.name}${vmark}${reachBadge}</div>
      <div class="rc-bar-wrap">
        <div class="rc-bar"><div class="rc-bar-fill" style="width:${Math.min(r.final_score/2,1)*100}%;"></div></div>
        <div class="rc-score">${scoreStr}</div>
      </div>
      <div class="rc-dots">${dots}</div>
      <div class="rc-ecu">연결 ECU: ${r.conn_ecus.slice(0,4).join(', ')}${r.conn_ecus.length>4?' ...':''}</div>
    </div>`;
  });
  document.getElementById('panel-rc').innerHTML = html;
}

function renderDTCPanel(data) {
  let html = '';
  data.dtc_info.forEach(d => {
    const border = d.has_struct ? 'var(--primary)' : 'var(--muted)';
    const sysBadge = d.system_name
      ? `<span style="font-size:10px;padding:1px 7px;border-radius:980px;font-weight:600;margin-right:4px;background:var(--fog);color:var(--secondary);">${d.system_code}: ${d.system_name}</span>`
      : '';
    const mfrBadge = d.mfr_specific==='True'
      ? `<span style="font-size:10px;padding:1px 7px;border-radius:980px;font-weight:600;margin-right:4px;background:rgba(0,113,227,.08);color:var(--primary);">제조사 전용</span>`
      : `<span style="font-size:10px;padding:1px 7px;border-radius:980px;font-weight:600;margin-right:4px;background:var(--fog);color:var(--muted);">SAE 표준</span>`;
    const stBadge = d.subtype_name
      ? `<span style="font-size:10px;padding:1px 7px;border-radius:980px;font-weight:600;background:var(--fog);color:var(--secondary);">${d.subtype_code}: ${d.subtype_name}</span>`
      : (d.subtype_code ? `<span style="font-size:10px;padding:1px 7px;border-radius:980px;background:var(--fog);color:var(--muted);">${d.subtype_code}</span>` : '');
    const posBadge = d.position
      ? `<span style="font-size:10px;padding:1px 7px;border-radius:980px;font-weight:600;background:rgba(0,113,227,.08);color:var(--primary);">${d.position}</span>`
      : '';

    html += `<div class="dtc-info-card" style="border-left-color:${border}">
      <div class="dtc-code">${d.code}</div>
      <div style="margin:4px 0;">${sysBadge}${mfrBadge}</div>
      <div style="margin:3px 0;">${stBadge} ${posBadge}</div>
      <div class="dtc-cat" style="margin-top:4px;">${d.cat || '기타'}</div>
      <div class="dtc-ecu">ECU: ${d.ecu_names.slice(0,3).join(', ')}</div>
      <div class="dtc-desc">${d.desc || '설명 없음'}</div>
      <div style="font-size:10px;margin-top:4px;color:${d.has_struct?'var(--primary)':'var(--muted)'};font-weight:600;">
        ${d.has_struct ? '구조 경로 있음' : 'RGAT 예측 사용'}
      </div>
    </div>`;
  });
  document.getElementById('panel-dtc').innerHTML = html;
}

// ── vis.js 마인드맵 스타일 시각화 ─────────────────────────────
const GROUPS = {
  dtc_input: {
    shape: 'box',
    shapeProperties: { borderRadius: 20 },
    margin: { top: 9, bottom: 9, left: 18, right: 18 },
    color: {
      background: '#fee2e2',
      border: '#fca5a5',
      highlight: { background: '#fecaca', border: '#f87171' }
    },
    borderWidth: 1.5,
    font: {
      color: '#991b1b',
      size: 13,
      bold: true,
      face: 'Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    },
    shadow: { enabled: true, color: 'rgba(0,0,0,0.04)', size: 6, x: 0, y: 2 }
  },
  ecu: {
    shape: 'box',
    shapeProperties: { borderRadius: 20 },
    margin: { top: 9, bottom: 9, left: 18, right: 18 },
    color: {
      background: '#ffedd5',
      border: '#fdba74',
      highlight: { background: '#fed7aa', border: '#fb923c' }
    },
    borderWidth: 1.5,
    font: {
      color: '#9a3412',
      size: 13,
      bold: true,
      face: 'Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    },
    shadow: { enabled: true, color: 'rgba(0,0,0,0.04)', size: 6, x: 0, y: 2 }
  },
  conn_top1: {
    shape: 'box',
    shapeProperties: { borderRadius: 22 },
    margin: { top: 11, bottom: 11, left: 22, right: 22 },
    color: {
      background: '#1e293b',
      border: '#0f172a',
      highlight: { background: '#0f172a', border: '#020617' }
    },
    borderWidth: 2,
    font: {
      color: '#ffffff',
      size: 14,
      bold: true,
      face: 'Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    },
    shadow: { enabled: true, color: 'rgba(30,41,59,0.35)', size: 10, x: 0, y: 3 }
  },
  conn_top: {
    shape: 'box',
    shapeProperties: { borderRadius: 20 },
    margin: { top: 8, bottom: 8, left: 16, right: 16 },
    color: {
      background: '#e0f2fe',
      border: '#7dd3fc',
      highlight: { background: '#bae6fd', border: '#38bdf8' }
    },
    borderWidth: 1.5,
    font: {
      color: '#0369a1',
      size: 12,
      bold: true,
      face: 'Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    },
    shadow: { enabled: true, color: 'rgba(0,0,0,0.04)', size: 5, x: 0, y: 2 }
  },
  conn: {
    shape: 'box',
    shapeProperties: { borderRadius: 20 },
    margin: { top: 7, bottom: 7, left: 14, right: 14 },
    color: {
      background: '#f1f5f9',
      border: '#cbd5e1',
      highlight: { background: '#e2e8f0', border: '#94a3b8' }
    },
    borderWidth: 1,
    font: {
      color: '#475569',
      size: 11,
      face: 'Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    }
  }
};

function buildNetwork(data) {
  const vn = new vis.DataSet(data.vis_nodes.map(n => ({
    id: n.id,
    label: n.label,
    title: n.title,
    shape: 'box',
    shapeProperties: { borderRadius: n.group === 'conn_top1' ? 22 : 18 },
    margin: n.group === 'conn_top1' ? { top: 11, bottom: 11, left: 22, right: 22 } : { top: 8, bottom: 8, left: 16, right: 16 },
    level: n.level,
    group: n.group
  })));

  const ve = new vis.DataSet(data.vis_edges.map((e,i) => {
    const isDirect = e.title && e.title.includes('HW_MAP');
    const isWire = e.title && e.title.includes('HW_WIRE');
    let edgeColor = '#94a3b8';
    if (isDirect) edgeColor = '#2563eb';
    else if (isWire) edgeColor = e.dashes ? '#93c5fd' : '#3b82f6';
    else edgeColor = '#cbd5e1';

    return {
      id: i, from: e.from, to: e.to,
      color: { color: edgeColor, highlight: '#2563eb', hover: '#2563eb' },
      width: isDirect ? 2.8 : (isWire ? 2.2 : 1.8),
      arrows: { to: { enabled: false } },
      title: e.title,
      dashes: e.dashes || false,
      smooth: { type: 'cubicBezier', forceDirection: 'horizontal', roundness: 0.6 },
    };
  }));

  const container = document.getElementById('network');
  document.getElementById('state-msg').style.display = 'none';
  container.style.display = 'block';

  if (network) { network.destroy(); network = null; }

  requestAnimationFrame(() => {
    network = new vis.Network(container, {nodes: vn, edges: ve}, {
      groups: GROUPS,
      layout: {
        hierarchical: {
          enabled: hierarchicalOn,
          direction: 'LR',
          sortMethod: 'directed',
          levelSeparation: 260,
          nodeSpacing: 70,
          treeSpacing: 90,
          blockShifting: true,
          edgeMinimization: true,
        },
      },
      physics: {
        enabled: !hierarchicalOn,
        barnesHut: {gravitationalConstant:-4000, centralGravity:.3, springLength:200, damping:.1},
        stabilization: {iterations:350, fit:true},
      },
      interaction: {hover:true, tooltipDelay:60, navigationButtons:false, keyboard:true},
      nodes: {borderWidth:1.5},
      edges: {shadow:false, hoverWidth:2.5},
    });

    physicsOn = !hierarchicalOn;
    if (!hierarchicalOn) {
      network.on('stabilizationIterationsDone', () => {
        network.setOptions({physics:{enabled:false}});
        physicsOn = false;
        network.fit({animation:{duration:400}});
      });
    } else {
      network.once('afterDrawing', () => network.fit({animation:{duration:400}}));
    }
  });
}

function fitNetwork() { if (network) network.fit({animation:{duration:400}}); }
function togglePhysics() {
  if (!network) return;
  physicsOn = !physicsOn;
  network.setOptions({physics:{enabled:physicsOn}});
}
function toggleLayout() {
  hierarchicalOn = !hierarchicalOn;
  const label = hierarchicalOn ? '계층형 마인드맵' : '자유 방사형';
  const span = document.querySelector('#layout-btn span');
  if (span) {
    span.textContent = label;
  } else {
    document.getElementById('layout-btn').textContent = label;
  }
  if (lastResult) buildNetwork(lastResult);
}
function focusConn(connId) {
  if (!network) return;
  switchTab('rc');
  try {
    network.selectNodes([connId]);
    network.focus(connId, {scale:1.6, animation:{duration:500}});
  } catch(e) {}
}

// ── 모달 & 토스트 시스템 ──────────────────────────────────────
function showModal({title, type = 'info', icon, body, confirmText}) {
  document.getElementById('modal-title').textContent = title || '알림';
  
  // 핀테크 스타일 고정밀 벡터 아이콘 렌더링
  let iconSvg = '';
  if (type === 'warn' || icon === '⚠️') {
    iconSvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;
  } else if (type === 'error' || icon === '❌' || icon === '🔌') {
    iconSvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;
  } else {
    iconSvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
  }
  document.getElementById('modal-icon').innerHTML = iconSvg;
  document.getElementById('modal-body').innerHTML = body || '';
  const footer = document.getElementById('modal-footer');
  footer.innerHTML = `<button class="modal-btn primary" onclick="closeModal()">${confirmText || '확인'}</button>`;
  document.getElementById('app-modal').classList.add('active');
}

function closeModal() {
  document.getElementById('app-modal').classList.remove('active');
}

function showToast(msg, type = 'info') {
  const wrap = document.getElementById('toast-wrap');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  wrap.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => {
    t.classList.remove('show');
    setTimeout(() => t.remove(), 300);
  }, 2800);
}
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════
# 5. 실행 엔트리포인트 (CLI 옵션 및 브라우저 제어)
# ══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="DTC Knowledge Graph Analysis Web Server")
    parser.add_argument("--port", type=int, default=config.DEFAULT_PORT, help=f"Server port (default: {config.DEFAULT_PORT})")
    parser.add_argument("--host", type=str, default=config.DEFAULT_HOST, help=f"Bind host (default: {config.DEFAULT_HOST})")
    parser.add_argument("--prod", action="store_true", help="Run with production WSGI server (Waitress)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    url = f"http://localhost:{args.port}"
    logger.info(f"Starting server on {args.host}:{args.port} -> {url} (Production WSGI: {args.prod})")

    if not args.no_browser and not config.IS_PRODUCTION:
        def open_browser():
            time.sleep(1.2)
            try:
                webbrowser.open(url)
            except Exception as e:
                logger.warning(f"Could not open browser automatically: {e}")
        threading.Thread(target=open_browser, daemon=True).start()

    if args.prod:
        try:
            from waitress import serve
            logger.info(f"Serving with Waitress WSGI on {args.host}:{args.port} (threads=8)...")
            serve(app, host=args.host, port=args.port, threads=8)
        except ImportError:
            logger.error("Waitress is not installed. Falling back to Flask dev server. Run: pip install waitress")
            app.run(debug=False, port=args.port, host=args.host)
    else:
        app.run(debug=False, port=args.port, host=args.host)


if __name__ == "__main__":
    main()
