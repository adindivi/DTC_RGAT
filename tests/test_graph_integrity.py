# -*- coding: utf-8 -*-
"""
지식 그래프 및 엑셀 데이터 무결성 검증 테스트
- ISO 14229-1 FTB 서브타입 빈칸 0건 검증
- '미분류' 잔존 데이터 0건 검증
- 대표 샘플 코드 정상 매핑 검증
"""
from validate_update import (
    validate_json_subtypes,
    validate_excel_subtypes,
    verify_sample_codes,
    SAMPLE_TEST_CODES,
    DEFAULT_JSON_PATH,
    DEFAULT_EXCEL_PATH,
)


def test_json_subtypes_integrity():
    """JSON 파일 내 서브타입 빈칸 및 '미분류' 0건 검증"""
    summary, dtc_nodes = validate_json_subtypes(DEFAULT_JSON_PATH)
    assert summary.total_nodes > 1000, f"Expected >1000 DTC nodes, got {summary.total_nodes}"
    assert summary.empty_subtypes == 0, f"Found {summary.empty_subtypes} empty subtypes in JSON"
    assert summary.unclassified_subtypes == 0, f"Found {summary.unclassified_subtypes} '미분류' subtypes in JSON"
    assert summary.is_valid is True


def test_excel_subtypes_integrity():
    """엑셀 마스터 파일 내 서브타입 빈칸 및 '미분류' 0건 검증"""
    summary = validate_excel_subtypes(DEFAULT_EXCEL_PATH)
    assert summary.total_nodes > 1000, f"Expected >1000 Excel master rows, got {summary.total_nodes}"
    assert summary.empty_subtypes == 0, f"Found {summary.empty_subtypes} empty subtypes in Excel"
    assert summary.unclassified_subtypes == 0, f"Found {summary.unclassified_subtypes} '미분류' in Excel"
    assert summary.is_valid is True


def test_sample_codes_resolution():
    """과거 빈칸/미분류였던 대표 8건 샘플 코드의 정상 해석 검증"""
    _, dtc_nodes = validate_json_subtypes(DEFAULT_JSON_PATH)
    verified_samples = verify_sample_codes(dtc_nodes, SAMPLE_TEST_CODES)
    assert len(verified_samples) == len(SAMPLE_TEST_CODES)
    for sample in verified_samples:
        assert sample["subtype_name"] != "", f"Code {sample['code']} has empty subtype"
        assert sample["subtype_name"] != "미분류", f"Code {sample['code']} is still '미분류'"
