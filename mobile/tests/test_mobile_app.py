# -*- coding: utf-8 -*-
"""
DTC Knowledge Graph - Galaxy Mobile Web App Tests
- Comprehensive automated test suite for mobile HTTP routes, PWA manifest,
  service worker caching, and REST API contracts.
"""
import json
import pytest
from pathlib import Path
import sys

# Register mobile and root folders into sys.path
MOBILE_DIR = Path(__file__).parent.parent.resolve()
ROOT_DIR = MOBILE_DIR.parent.resolve()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(MOBILE_DIR) not in sys.path:
    sys.path.insert(0, str(MOBILE_DIR))

from mobile.app import app, _sanitize_dtc_codes


@pytest.fixture
def mobile_client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_mobile_index_returns_200_and_cache_headers(mobile_client):
    """모바일 대시보드 200 응답 및 모바일 메타/PWA/캐시 헤더 검증"""
    res = mobile_client.get("/")
    assert res.status_code == 200
    assert "no-cache" in res.headers.get("Cache-Control", "")
    html = res.data.decode("utf-8")
    assert "DTC Mobile" in html
    assert "manifest.json" in html
    assert "viewport" in html
    assert "segmented-tabs-bar" in html


def test_manifest_json_returns_200_and_standalone(mobile_client):
    """PWA 매니페스트 서빙 및 standalone 설정 검증"""
    res = mobile_client.get("/manifest.json")
    assert res.status_code == 200
    assert "max-age=3600" in res.headers.get("Cache-Control", "")
    data = json.loads(res.data)
    assert data.get("display") == "standalone"
    assert "DTC" in data.get("name", "")


def test_service_worker_returns_200_and_no_store(mobile_client):
    """PWA 서비스 워커 JS 서빙 및 no-store 캐시 무결성 검증"""
    res = mobile_client.get("/sw.js")
    assert res.status_code == 200
    assert "no-store" in res.headers.get("Cache-Control", "")
    assert b"addEventListener" in res.data


def test_server_info_api_returns_lan_ip(mobile_client):
    """갤럭시 모바일 접속 안내 API 정합성 검증"""
    res = mobile_client.get("/api/server-info")
    assert res.status_code == 200
    data = res.get_json()
    assert "lan_ip" in data
    assert "mobile_url" in data
    assert data["lan_ip"].count(".") == 3  # Valid IPv4 format


def test_mobile_search_api_valid_and_empty_query(mobile_client):
    """모바일 자동완성 검색 API 검증"""
    res_valid = mobile_client.get("/api/search?q=C1283")
    assert res_valid.status_code == 200
    results = res_valid.get_json()
    assert isinstance(results, list)
    assert any("C128387" in r["code"] for r in results)

    res_empty = mobile_client.get("/api/search?q=")
    assert res_empty.status_code == 200
    assert res_empty.get_json() == []


def test_mobile_analyze_api_valid_codes(mobile_client):
    """모바일 분석 API 200 계약 및 결과 검증"""
    res = mobile_client.post(
        "/api/analyze",
        data=json.dumps({"codes": ["C128387", "B122901"]}),
        content_type="application/json"
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "results" in data
    assert len(data["results"]) > 0


def test_mobile_analyze_api_empty_codes_returns_400(mobile_client):
    """빈 코드 분석 요청 시 400 방어 검증"""
    res = mobile_client.post(
        "/api/analyze",
        data=json.dumps({"codes": []}),
        content_type="application/json"
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_mobile_analyze_api_invalid_json_returns_400(mobile_client):
    """비정상 JSON 페이로드 요청 시 400 방어 검증"""
    res = mobile_client.post(
        "/api/analyze",
        data="INVALID_NOT_JSON",
        content_type="application/json"
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_mobile_analyze_api_exceeds_limit_returns_400(mobile_client):
    """50개 초과 코드 요청 시 DoS 방어 400 검증"""
    over_codes = [f"DTC_{i:04d}" for i in range(60)]
    res = mobile_client.post(
        "/api/analyze",
        data=json.dumps({"codes": over_codes}),
        content_type="application/json"
    )
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_mobile_latent_space_api(mobile_client):
    """64D 잠재공간 데이터 1705개 포인트 검증"""
    res = mobile_client.get("/api/latent-space")
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 1705


def test_mobile_sanitize_dtc_codes_helper():
    """모바일 입력 정제 헬퍼 단위 테스트"""
    assert _sanitize_dtc_codes("C128387, B122901\nC128387") == ["C128387", "B122901"]
    assert _sanitize_dtc_codes(None) == []
    assert _sanitize_dtc_codes(["  c128387  ", "b122901"]) == ["C128387", "B122901"]


def test_mobile_report_page_returns_200(mobile_client):
    """모바일 원리해설서 서빙 엔드포인트 200 검증"""
    res = mobile_client.get("/report")
    assert res.status_code == 200
    assert len(res.data) > 0


def test_mobile_qr_code_api(mobile_client):
    """모바일 로컬 오프라인 QR 코드 이미지 서빙 검증"""
    res = mobile_client.get("/api/qr-code")
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "image/png"
    assert len(res.data) > 100


