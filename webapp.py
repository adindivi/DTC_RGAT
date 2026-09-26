# -*- coding: utf-8 -*-
"""
DTC 지식 그래프 진단 웹 애플리케이션
- 단일 책임 원칙(SRP) 준수 및 클린 아키텍처
- REST API 라우팅 및 표준 에러 로깅
- mtime 기반 프론트엔드 템플릿 및 리포트 캐싱
"""
import argparse
import logging
import re
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

import config
from graph_service import KnowledgeGraphService

# ══════════════════════════════════════════════════════════════
# 1. 로깅 시스템 설정 (표준 포맷터 및 콘솔/파일 핸들러)
# ══════════════════════════════════════════════════════════════
logger = logging.getLogger("DTC_RGAT")
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

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
# 3. Flask 애플리케이션 및 템플릿 캐시 정의
# ══════════════════════════════════════════════════════════════
app = Flask(__name__, template_folder=str(config.TEMPLATES_DIR))

_index_cache: dict[str, Any] = {"mtime": 0.0, "content": ""}
_report_cache: dict[str, Any] = {"mtime": 0.0, "content": ""}


def get_index_html() -> str:
    """메인 대시보드 HTML mtime 기반 동적 캐싱 (핫 리로드 및 고속 서빙)"""
    template_path = config.TEMPLATES_DIR / "index.html"
    if template_path.exists():
        mtime = template_path.stat().st_mtime
        if mtime != _index_cache["mtime"]:
            with open(template_path, "r", encoding="utf-8") as f:
                _index_cache["content"] = f.read()
            _index_cache["mtime"] = mtime
        return _index_cache["content"]
    return ""


def get_report_html() -> str:
    """원리해설서 HTML mtime 기반 동적 캐싱 (핫 리로드 및 고속 서빙)"""
    report_path = config.REPORT_HTML_PATH
    if report_path.exists():
        mtime = report_path.stat().st_mtime
        if mtime != _report_cache["mtime"]:
            with open(report_path, "r", encoding="utf-8") as f:
                _report_cache["content"] = f.read()
            _report_cache["mtime"] = mtime
        return _report_cache["content"]
    return ""


# 하위 호환성을 위한 전역 모듈 변수 제공
HTML_TEMPLATE: str = get_index_html()


def _sanitize_dtc_codes(raw_codes: Any) -> list[str]:
    """
    입력된 원시 DTC 코드 배열을 공백, 쉼표, 세미콜론 기준으로 분리하고 정규화
    - 단일 책임 원칙(SRP): 입력 코드 정제 및 중복 제거
    """
    if not isinstance(raw_codes, list):
        return []

    codes: list[str] = []
    for item in raw_codes:
        for sub_code in re.split(r"[\s,;\n\r\t]+", str(item)):
            clean_code = sub_code.upper().strip()
            if clean_code and clean_code not in codes:
                codes.append(clean_code)
    return codes


# ══════════════════════════════════════════════════════════════
# 4. REST API 라우트 정의
# ══════════════════════════════════════════════════════════════
@app.route("/")
def index():
    """메인 진단 마인드맵 대시보드 뷰"""
    content = get_index_html()
    if content:
        return content
    return "Template index.html not found", 404


@app.route("/report")
@app.route("/guide")
def report():
    """최종 완결 정리 보고서 (엔지니어링 화이트페이퍼) 라우트"""
    content = get_report_html()
    if content:
        return content
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


@app.route("/api/latent-space")
def latent_space():
    """64차원 잠재 공간 t-SNE 2D 프로젝션 좌표 반환 API"""
    try:
        points = graph_service.get_latent_space_points()
        return jsonify({
            "count": len(points),
            "points": points,
        })
    except Exception as e:
        logger.error(f"Error retrieving latent space: {e}", exc_info=True)
        return jsonify({"error": "잠재 공간 좌표를 로드하는 중 오류가 발생했습니다.", "detail": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """
    DTC 코드 목록 분석 API
    - 입력값 유효성 검증 (400 Bad Request 방어)
    - DoS 방어를 위한 상한 검사
    - 하이브리드(구조+RGAT) 근본원인 랭킹 반환
    """
    start_time = time.perf_counter()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        logger.warning(f"Invalid JSON payload received from {request.remote_addr}")
        return jsonify({
            "error": "요청 형식이 잘못되었습니다. 올바른 JSON 데이터를 전달하세요.",
            "detail": "JSON Object with 'codes' array expected",
        }), 400

    raw_codes = data.get("codes", [])
    if not isinstance(raw_codes, list):
        return jsonify({
            "error": "'codes' 필드는 배열(Array) 형태여야 합니다.",
            "detail": f"Received type: {type(raw_codes).__name__}",
        }), 400

    codes = _sanitize_dtc_codes(raw_codes)
    if not codes:
        return jsonify({
            "error": "분석할 DTC 코드를 1개 이상 입력해주세요.",
            "detail": "No valid non-empty DTC codes provided",
        }), 400

    # [보안/DoS 방어] 단일 요청 최대 분석 가능 코드 개수 상한 제한
    if len(codes) > config.MAX_DTC_CODES_LIMIT:
        return jsonify({
            "error": f"1회 최대 분석 가능 코드는 {config.MAX_DTC_CODES_LIMIT}개입니다.",
            "detail": f"Submitted: {len(codes)} codes (exceeds limit: {config.MAX_DTC_CODES_LIMIT})",
        }), 400

    logger.info(f"Incoming analysis request for {len(codes)} codes: {codes}")

    try:
        use_mask = bool(data.get("topology_mask", config.USE_TOPOLOGY_MASK))
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
            "detail": str(e),
        }), 500


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
