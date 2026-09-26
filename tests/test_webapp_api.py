# -*- coding: utf-8 -*-
"""
웹 애플리케이션 REST API 및 엔드포인트 통합 테스트 슈트
- HTTP 상태 코드 (200, 400, 404) 및 JSON 계약(Contract) 검증
"""
import json


def test_index_page_returns_200(client):
    """메인 대시보드 HTML 제공 확인"""
    res = client.get("/")
    assert res.status_code == 200
    assert b"DTC Knowledge Graph" in res.data


def test_report_page_returns_200(client):
    """원리해설서(/report) 라우트 200 응답 확인"""
    res = client.get("/report")
    assert res.status_code == 200
    assert "Engineering Whitepaper" in res.data.decode("utf-8") or "DTC_RGAT" in res.data.decode("utf-8")


def test_search_autocomplete_valid_query(client):
    """자동완성 검색 API 정상 동작 확인"""
    res = client.get("/api/search?q=C128")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert any("C128387" in item.get("code", "") for item in data)


def test_search_autocomplete_empty_query_returns_empty_list(client):
    """빈 쿼리 검색 시 빈 배열 반환 확인"""
    res = client.get("/api/search?q=")
    assert res.status_code == 200
    assert res.get_json() == []


def test_analyze_api_valid_codes_returns_200(client):
    """정상 DTC 코드 목록 전달 시 200 OK 및 분석 결과 계약 확인"""
    payload = {"codes": ["C128387", "B122901"]}
    res = client.post(
        "/api/analyze",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert res.status_code == 200
    data = res.get_json()
    assert "results" in data
    assert "vis_nodes" in data
    assert "vis_edges" in data
    assert len(data["results"]) > 0


def test_analyze_api_invalid_json_payload_returns_400(client):
    """JSON 형식이 아닌 잘못된 본문 전달 시 400 Bad Request 방어 확인"""
    res = client.post(
        "/api/analyze",
        data="This is not JSON",
        content_type="application/json"
    )
    assert res.status_code == 400
    data = res.get_json()
    assert "error" in data


def test_analyze_api_empty_codes_returns_400(client):
    """빈 codes 배열 전달 시 400 Bad Request 방어 확인"""
    payload = {"codes": []}
    res = client.post(
        "/api/analyze",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert res.status_code == 400
    data = res.get_json()
    assert "error" in data


def test_analyze_api_all_unknown_codes_returns_400(client):
    """전부 미등록 코드인 경우 400 Bad Request 및 unknown 리스트 반환 확인"""
    payload = {"codes": ["NON_EXISTENT_CODE_1", "NON_EXISTENT_CODE_2"]}
    res = client.post(
        "/api/analyze",
        data=json.dumps(payload),
        content_type="application/json"
    )
    assert res.status_code == 400
    data = res.get_json()
    assert "unknown" in data
    assert len(data["unknown"]) == 2


def test_analyze_api_exceeds_max_codes_limit_returns_400(client):
    """[보안] 50개 초과 대량 DTC 코드 요청 시 DoS 방어 400 확인"""
    excess_codes = [f"C{100000 + i}" for i in range(55)]
    res = client.post(
        "/api/analyze",
        data=json.dumps({"codes": excess_codes}),
        content_type="application/json"
    )
    assert res.status_code == 400
    data = res.get_json()
    assert "1회 최대 분석 가능 코드" in data.get("error", "")


def test_latent_space_api_returns_points(client):
    """64차원 잠재 공간 t-SNE 2D 프로젝션 API 계약 및 데이터 정합성 확인"""
    res = client.get("/api/latent-space")
    assert res.status_code == 200
    data = res.get_json()
    assert "count" in data
    assert "points" in data
    assert data["count"] == 1705
    assert len(data["points"]) == 1705
    first = data["points"][0]
    assert "id" in first and "x" in first and "y" in first and "domain" in first

