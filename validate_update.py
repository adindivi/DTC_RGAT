# -*- coding: utf-8 -*-
import json
import openpyxl
from pathlib import Path

BASE = Path(__file__).parent.resolve()
JSON_PATH = BASE / "dtc_knowledge_graph.json"
EXCEL_PATH = BASE / "dtc_knowledge_graph_updated.xlsx"

print("=" * 60)
print(" 1. JSON 검증 (dtc_knowledge_graph.json)")
print("=" * 60)
with open(JSON_PATH, "r", encoding="utf-8") as f:
    g = json.load(f)

dtcs = [n for n in g.get("nodes", []) if n.get("node_type") == "DTC"]
empty_json = [d for d in dtcs if not (d.get("subtype_name") or "").strip()]
mibul_json = [d for d in dtcs if (d.get("subtype_name") or "").strip() == "미분류"]

print(f"  - 총 DTC 노드 수       : {len(dtcs)}개")
print(f"  - 빈칸('') 서브타입 수 : {len(empty_json)}개 (목표: 0)")
print(f"  - '미분류' 서브타입 수 : {len(mibul_json)}개 (목표: 0)")

print("\n" + "=" * 60)
print(f" 2. 엑셀 파일 검증 ({EXCEL_PATH.name})")
print("=" * 60)
wb = openpyxl.load_workbook(str(EXCEL_PATH), data_only=True)
ws = wb["2. DTC 종합 마스터"]

empty_excel = 0
mibul_excel = 0
total_excel = 0

for row in ws.iter_rows(min_row=2, min_col=1, max_col=12, values_only=True):
    total_excel += 1
    st_name = str(row[6] or "").strip()
    if not st_name:
        empty_excel += 1
    elif st_name == "미분류":
        mibul_excel += 1

print(f"  - 총 마스터 데이터 행   : {total_excel}개")
print(f"  - 엑셀 내 빈칸 서브타입 : {empty_excel}개 (목표: 0)")
print(f"  - 엑셀 내 '미분류'      : {mibul_excel}개 (목표: 0)")

print("\n" + "=" * 60)
print(" 3. 신규 매핑된 대표 샘플 확인 (상위 8건)")
print("=" * 60)
# 이전 문제였던 코드들 샘플
test_codes = ["C133A00", "B151114", "B132656", "P0D0972", "P0D2498", "C120102", "C139846", "B100252"]
for tc in test_codes:
    match = next((d for d in dtcs if d.get("code") == tc), None)
    if match:
        print(f"  [{match.get('code')}] FTB: {match.get('subtype_code'):<2} -> 서브타입명: '{match.get('subtype_name')}'")

assert len(empty_json) == 0, "JSON 빈칸 검증 실패"
assert len(mibul_json) == 0, "JSON 미분류 검증 실패"
assert empty_excel == 0, "Excel 빈칸 검증 실패"
assert mibul_excel == 0, "Excel 미분류 검증 실패"

print("\n" + "=" * 60)
print(" [SUCCESS] JSON 및 Excel 전수 재검증 100% 정상 통과!")
print("=" * 60)
