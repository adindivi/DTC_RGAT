# -*- coding: utf-8 -*-
"""
DTC Knowledge Graph - Galaxy Mobile Dedicated Web Application Server
=====================================================================
Clean Architecture & SRP compliant implementation:
- Strictly isolated under /mobile directory (Original root repository files untouched)
- Mobile-first responsive UI, PWA support, touch gesture optimization
- Dynamic local IP detection for 1-second Galaxy mobile connection
- Standardized RESTful error responses and mtime-based template caching
"""
import argparse
import io
import logging
import os
import re
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Optional

try:
    import qrcode
except ImportError:
    qrcode = None

# Ensure parent directory is in sys.path for core module imports
PARENT_DIR = Path(__file__).parent.parent.resolve()
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from flask import Flask, Response, jsonify, make_response, request, send_from_directory

import config
from graph_service import KnowledgeGraphService

# ──────────────────────────────────────────────────────────────
# 1. Constants & Directory Paths
# ──────────────────────────────────────────────────────────────
DEFAULT_PORT: int = 5050
DEFAULT_HOST: str = "0.0.0.0"
LAN_PROBE_TARGET: tuple[str, int] = ("8.8.8.8", 80)
FALLBACK_LOOPBACK_IP: str = "127.0.0.1"

MOBILE_DIR: Path = Path(__file__).parent.resolve()
TEMPLATES_DIR: Path = MOBILE_DIR / "templates"
STATIC_DIR: Path = MOBILE_DIR / "static"

# ──────────────────────────────────────────────────────────────
# 2. Logging Setup
# ──────────────────────────────────────────────────────────────
logger = logging.getLogger("DTC_MOBILE")
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# ──────────────────────────────────────────────────────────────
# 3. KnowledgeGraphService Provider (Singleton Pattern)
# ──────────────────────────────────────────────────────────────
_graph_service_instance: Optional[KnowledgeGraphService] = None


def get_graph_service() -> KnowledgeGraphService:
    """Provides a singleton instance of KnowledgeGraphService for mobile endpoints."""
    global _graph_service_instance
    if _graph_service_instance is None:
        try:
            _graph_service_instance = KnowledgeGraphService(
                graph_path=config.GRAPH_JSON_PATH,
                embed_path=config.EMBED_NPY_PATH,
                alpha=config.DEFAULT_ALPHA,
                beta=config.DEFAULT_BETA,
                top_k=config.DEFAULT_TOP_K,
            )
            logger.info("KnowledgeGraphService loaded successfully for Mobile Web App.")
        except Exception as e:
            logger.critical(f"Failed to initialize KnowledgeGraphService: {e}", exc_info=True)
            raise RuntimeError(f"Could not initialize KnowledgeGraphService: {e}") from e
    return _graph_service_instance


# ──────────────────────────────────────────────────────────────
# 4. Helper Utilities (SRP)
# ──────────────────────────────────────────────────────────────
_mobile_index_cache: dict[str, Any] = {"mtime": 0.0, "content": ""}


def get_mobile_index_html() -> str:
    """Reads mobile index.html with mtime-based in-memory caching."""
    template_path = TEMPLATES_DIR / "index.html"
    if template_path.exists():
        mtime = template_path.stat().st_mtime
        if mtime != _mobile_index_cache["mtime"]:
            with open(template_path, "r", encoding="utf-8") as f:
                _mobile_index_cache["content"] = f.read()
            _mobile_index_cache["mtime"] = mtime
        return _mobile_index_cache["content"]
    return ""


_mobile_report_cache: dict[str, Any] = {"mtime": 0.0, "content": ""}


def get_mobile_report_html() -> str:
    """Reads engineering report HTML with mtime-based in-memory caching and mobile enhancements."""
    report_path = config.REPORT_HTML_PATH
    if report_path.exists():
        mtime = report_path.stat().st_mtime
        if mtime != _mobile_report_cache["mtime"]:
            with open(report_path, "r", encoding="utf-8") as f:
                raw_html = f.read()
            mobile_enhancements = """
<style>
@media (max-width: 600px) {
  body { padding: 14px 10px !important; font-size: 13.5px !important; line-height: 1.6 !important; }
  header { padding: 26px 16px !important; margin-bottom: 20px !important; border-radius: 14px !important; }
  header h1 { font-size: 20px !important; line-height: 1.35 !important; }
  header p { font-size: 12.5px !important; }
  .container { padding: 0 !important; width: 100% !important; max-width: 100% !important; }
  table { display: block !important; width: 100% !important; overflow-x: auto !important; -webkit-overflow-scrolling: touch !important; }
  pre, code { word-break: break-all !important; }
  img { max-width: 100% !important; height: auto !important; }
  .grid-2, .grid-3, .grid-4 { grid-template-columns: 1fr !important; }
}
</style>
</head>
"""
            if "</head>" in raw_html:
                enhanced_html = raw_html.replace("</head>", mobile_enhancements, 1)
            else:
                enhanced_html = raw_html
            _mobile_report_cache["content"] = enhanced_html
            _mobile_report_cache["mtime"] = mtime
        return _mobile_report_cache["content"]
    return ""


def get_local_lan_ip() -> str:
    """Automatically detects the host LAN IP accessible by Galaxy mobile devices."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(LAN_PROBE_TARGET)
        detected_ip = sock.getsockname()[0]
        sock.close()
        return detected_ip
    except Exception:
        return FALLBACK_LOOPBACK_IP


def _sanitize_dtc_codes(raw_codes: Any) -> list[str]:
    """
    Sanitizes, splits, deduplicates (order-preserving), and normalizes raw DTC codes.
    Handles comma, semicolon, newline, whitespace delimited inputs safely.
    """
    if not raw_codes:
        return []
    if isinstance(raw_codes, str):
        raw_items = [raw_codes]
    elif isinstance(raw_codes, (list, tuple, set)):
        raw_items = list(raw_codes)
    else:
        return []

    split_codes: list[str] = []
    for item in raw_items:
        if not isinstance(item, str):
            continue
        parts = re.split(r"[\s,;\n\r\t]+", item.strip())
        for p in parts:
            clean = p.strip().upper()
            if clean:
                split_codes.append(clean)

    # Order-preserving deduplication
    seen: set[str] = set()
    sanitized: list[str] = []
    for code in split_codes:
        if code not in seen:
            seen.add(code)
            sanitized.append(code)
    return sanitized


def error_response(message: str, status_code: int = 400, **kwargs: Any) -> tuple[Response, int]:
    """Builds a standardized JSON error response."""
    payload = {"error": message, **kwargs}
    return jsonify(payload), status_code


# ──────────────────────────────────────────────────────────────
# 5. Flask Mobile Application Factory & Setup
# ──────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder=str(TEMPLATES_DIR),
    static_folder=str(STATIC_DIR),
)

# Initialize service on startup
graph_service = get_graph_service()


@app.route("/")
def index() -> Response | tuple[str, int]:
    """Serves the mobile-first diagnostics dashboard with no-cache headers."""
    content = get_mobile_index_html()
    if not content:
        return "Mobile template not found.", 404
    response = make_response(content)
    response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@app.route("/report")
def report() -> Response | tuple[str, int]:
    """Serves the engineering principle report (mobile compatible)."""
    content = get_mobile_report_html()
    if not content:
        return "Report file not found.", 404
    response = make_response(content)
    response.headers["Cache-Control"] = "public, max-age=1800"
    return response


@app.route("/manifest.json")
def manifest() -> Response:
    """Serves the PWA manifest specification."""
    response = send_from_directory(
        STATIC_DIR, "manifest.json", mimetype="application/manifest+json"
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.route("/sw.js")
def service_worker() -> Response:
    """Serves the PWA Service Worker script with immediate revalidation."""
    response = send_from_directory(
        STATIC_DIR, "sw.js", mimetype="application/javascript"
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route("/dtc_ondevice_engine.js")
def ondevice_engine() -> Response:
    """Serves the standalone on-device DTC graph diagnosis engine."""
    return send_from_directory(
        STATIC_DIR, "dtc_ondevice_engine.js", mimetype="application/javascript"
    )


@app.route("/vis-network.min.js")
def vis_network_js() -> Response:
    """Serves the local bundled vis-network JavaScript library."""
    return send_from_directory(
        STATIC_DIR, "vis-network.min.js", mimetype="application/javascript"
    )


@app.route("/api/server-info")
def server_info() -> Response:
    """Provides LAN IP and connection guidance for Galaxy mobile onboarding."""
    lan_ip = get_local_lan_ip()
    port = request.environ.get("SERVER_PORT", DEFAULT_PORT)
    return jsonify({
        "lan_ip": lan_ip,
        "port": port,
        "mobile_url": f"http://{lan_ip}:{port}",
        "device_hint": "삼성 갤럭시(삼성 인터넷 / 크롬)에서 위 주소로 접속하세요.",
    })


@app.route("/api/qr-code")
def qr_code() -> Response | tuple[str, int]:
    """Generates and serves a pure offline local QR code PNG for the mobile URL."""
    if not qrcode:
        return "qrcode library not available", 501
    lan_ip = get_local_lan_ip()
    port = request.environ.get("SERVER_PORT", DEFAULT_PORT)
    mobile_url = f"http://{lan_ip}:{port}"
    img = qrcode.make(mobile_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    response = make_response(buf.getvalue())
    response.headers["Content-Type"] = "image/png"
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.route("/api/search")
def search() -> Response:
    """Provides DTC autocomplete search results."""
    query = request.args.get("q", "").strip()
    return jsonify(graph_service.search_dtc(query))


@app.route("/api/latent-space")
def latent_space() -> Response:
    """Provides 64-dimensional t-SNE 2D latent space coordinates."""
    points = graph_service.get_latent_space_points()
    return jsonify({
        "count": len(points),
        "points": points,
    })


@app.route("/api/analyze", methods=["POST"])
def analyze() -> tuple[Response, int] | Response:
    """
    Main diagnostic API endpoint:
    Analyzes input DTC codes and returns Top-5 root causes, knowledge graph, and explanation.
    """
    try:
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return error_response("유효한 JSON 요청 형식이 아닙니다.", 400)

        codes = _sanitize_dtc_codes(data.get("codes", []))
        if not codes:
            return error_response("분석할 DTC 코드를 최소 1개 이상 입력하세요.", 400)

        if len(codes) > config.MAX_DTC_CODES_LIMIT:
            return error_response(
                f"1회 최대 분석 가능 코드는 {config.MAX_DTC_CODES_LIMIT}개입니다.",
                400,
                count=len(codes),
            )

        start_time = time.perf_counter()
        result = graph_service.analyze(codes)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if result.get("error"):
            return jsonify(result), 400

        top1 = result["results"][0]["name"] if result.get("results") else "None"
        logger.info(f"[Mobile] Analysis completed in {elapsed_ms:.1f}ms. Top: {top1}")
        return jsonify(result)

    except Exception as e:
        logger.error(f"[Mobile] Unexpected error: {e}", exc_info=True)
        return error_response("서버 내부 처리 중 오류가 발생했습니다.", 500, detail=str(e))


# ──────────────────────────────────────────────────────────────
# 6. Main CLI Entrypoint
# ──────────────────────────────────────────────────────────────
def main() -> None:
    """CLI launcher for mobile development and production servers."""
    parser = argparse.ArgumentParser(description="DTC Knowledge Graph Galaxy Mobile Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port (default: 5050)")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--prod", action="store_true", help="Run with Waitress WSGI")
    parser.add_argument("--no-browser", action="store_true", help="Do not open local browser automatically")
    args = parser.parse_args()

    lan_ip = get_local_lan_ip()
    mobile_url = f"http://{lan_ip}:{args.port}"
    local_url = f"http://localhost:{args.port}"

    print("=" * 68)
    print("  DTC Knowledge Graph - Galaxy Mobile Web App Server Started")
    print("=" * 68)
    print(f"  [PC Local Access]    : {local_url}")
    print(f"  [Galaxy Mobile URL]  : {mobile_url}")
    print("=" * 68)
    print("  TIP: Connect Galaxy phone to the same Wi-Fi / Hotspot,")
    print(f"       and open: {mobile_url}")
    print("=" * 68)

    if not args.no_browser:
        def open_browser():
            time.sleep(1.2)
            try:
                webbrowser.open(local_url)
            except Exception:
                pass
        threading.Thread(target=open_browser, daemon=True).start()

    if args.prod:
        try:
            from waitress import serve
            logger.info(f"Serving mobile app with Waitress on {args.host}:{args.port}...")
            serve(app, host=args.host, port=args.port, threads=8)
        except ImportError:
            logger.error("Waitress not installed. Falling back to Flask dev server.")
            app.run(debug=False, port=args.port, host=args.host)
    else:
        app.run(debug=False, port=args.port, host=args.host)


if __name__ == "__main__":
    main()
