# -*- coding: utf-8 -*-
"""
KnowledgeGraphService 비즈니스 로직 테스트 슈트
- 클로드 프롬프트 팩(스킬) 표준: 정상 케이스 3개, 엣지 케이스 3개, 에러 케이스 2개
"""
from graph_service import KnowledgeGraphService


# ══════════════════════════════════════════════════════════════
# 1. 정상 케이스 (Normal Cases - 3개)
# ══════════════════════════════════════════════════════════════

def test_analyze_single_code_returns_ranking_and_ecus(service: KnowledgeGraphService):
    """[정상 1] 단일 제동 고장 코드 분석 시 연관 ECU 및 순위 정상 산출 검증"""
    res = service.analyze(["C128387"])
    assert "error" not in res
    assert len(res["dtc_info"]) == 1
    assert res["dtc_info"][0]["code"] == "C128387"
    assert "ABS/ESC" in res["dtc_info"][0]["ecu_names"]
    assert len(res["results"]) > 0
    assert res["results"][0]["rank"] == 1


def test_analyze_cluster_acu_b_returns_verified_top1(service: KnowledgeGraphService):
    """[정상 2] 4개 제어기 다발 연쇄 고장 입력 시 ACU_B 마스터 검증 1위 도출 검증"""
    codes = ["B100552", "C128387", "C164387", "C166987"]
    res = service.analyze(codes)
    assert "error" not in res
    assert len(res["dtc_info"]) == 4
    top1 = res["results"][0]
    assert "ACU_B" in top1["conn_id"]
    assert top1["verified"] is True
    assert top1["final_score"] == 2.0


def test_analyze_hybrid_generates_both_hw_wire_and_ai_hw_wire(service: KnowledgeGraphService):
    """[정상 3] 제동·공조 복합 다발 시 HW_WIRE(실선)와 AI_HW_WIRE(점선) 공존 생성 검증"""
    codes = ["C128387", "B122901", "B234301", "B240301"]
    res = service.analyze(codes)
    assert "error" not in res
    edges = res["vis_edges"]

    hw_wires = [
        e for e in edges
        if e.get("title") and "HW_WIRE" in e["title"] and not e.get("dashes")
    ]
    ai_wires = [
        e for e in edges
        if e.get("title") and "AI_HW_WIRE" in e["title"] and e.get("dashes")
    ]
    assert len(hw_wires) > 0, "Expected solid HW_WIRE edges to exist"
    assert len(ai_wires) > 0, "Expected dashed AI_HW_WIRE edges to exist"


# ══════════════════════════════════════════════════════════════
# 2. 엣지 케이스 (Edge Cases - 3개)
# ══════════════════════════════════════════════════════════════

def test_analyze_empty_codes_list_handled_gracefully(service: KnowledgeGraphService):
    """[엣지 1] 빈 코드 리스트 전달 시 예외 발생 없이 안전한 에러 딕셔너리 반환"""
    res = service.analyze([])
    assert "error" in res
    assert res["dtc_info"] == []
    assert res["results"] == []
    assert res["vis_nodes"] == []


def test_analyze_case_insensitive_and_whitespace_trimming(service: KnowledgeGraphService):
    """[엣지 2] 소문자 및 앞뒤 공백/줄바꿈이 섞인 입력의 정규화 처리 검증"""
    res = service.analyze([" c128387 \n", "  b122901\t"])
    assert "error" not in res
    assert len(res["dtc_info"]) == 2
    codes = [d["code"] for d in res["dtc_info"]]
    assert "C128387" in codes
    assert "B122901" in codes


def test_analyze_unlinked_sensor_ecus_fallback_to_ai_wire(service: KnowledgeGraphService):
    """[엣지 3] CAD 회로도상 물리 배선이 없는 센서 제어기(LCC)의 AI_HW_WIRE Fallback 검증"""
    res = service.analyze(["B122901", "B234301"])
    assert "error" not in res
    edges = res["vis_edges"]
    ai_wires = [e for e in edges if e.get("dashes") is True]
    assert len(ai_wires) > 0, "Sensor-only cluster must generate AI_HW_WIRE fallback edges"


# ══════════════════════════════════════════════════════════════
# 3. 에러 케이스 (Error Cases - 2개)
# ══════════════════════════════════════════════════════════════

def test_analyze_all_unknown_codes_returns_unknown_and_error(service: KnowledgeGraphService):
    """[에러 1] 마스터에 존재하지 않는 임의의 코드만 입력되었을 때의 격리 검증"""
    res = service.analyze(["INVALID_DTC_999", "UNKNOWN_XYZ_888"])
    assert "error" in res
    assert len(res["unknown"]) == 2
    assert "INVALID_DTC_999" in res["unknown"]
    assert "UNKNOWN_XYZ_888" in res["unknown"]
    assert res["results"] == []


def test_analyze_mixed_valid_and_invalid_codes_filters_unknown(service: KnowledgeGraphService):
    """[에러 2] 유효 코드와 미등록 코드가 혼합되었을 때 미등록 격리 및 정상 분석 진행 검증"""
    res = service.analyze(["C128387", "FAKE_CODE_123"])
    assert "error" not in res
    assert res["unknown"] == ["FAKE_CODE_123"]
    assert len(res["dtc_info"]) == 1
    assert res["dtc_info"][0]["code"] == "C128387"
    assert len(res["results"]) > 0
