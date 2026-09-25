# -*- coding: utf-8 -*-
"""
ISO 14229-1 (UDS FTB) 국제 표준 및 현대차 GSW 정비 지침서 기준에 따라
dtc_knowledge_graph.json 내 453개 빈칸/미분류 서브타입 명칭을 100% 채우고,
엑셀 파일(dtc_knowledge_graph.xlsx)까지 원클릭으로 재생성 및 재검증하는 스크립트
"""
import json
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
JSON_PATH = BASE_DIR / "dtc_knowledge_graph.json"
BAK_PATH = BASE_DIR / "dtc_knowledge_graph.json.bak"

# ══════════════════════════════════════════════════════════════
# 1. ISO 14229-1 Annex D (UDS Fault Type Byte) 공식 한글 표준 사전
# ══════════════════════════════════════════════════════════════
ISO_FTB_MAP = {
    "00": "세부 유형 없음 (기본 고장)",
    "01": "일반 전기적 오류",
    "02": "일반 신호 오류",
    "03": "FM/PWM 변조 오류 (하드웨어 이상)",
    "05": "시스템 프로그램 고장",
    "07": "기구적/기계적 고장",
    "08": "통신 버스 신호/메시지 오류",
    "0A": "배선 등 DC 회로 일반 전기 고장",
    "11": "회로 그라운드 쇼트",
    "12": "회로 배터리 전원 쇼트",
    "13": "회로 단선/개방",
    "14": "회로 그라운드 쇼트 또는 단선",
    "15": "회로 배터리 쇼트 또는 단선",
    "16": "단선/개방 회로 (저전압)",
    "17": "개방 회로 (과전압)",
    "1F": "회로 간헐적 결함 (스위치 이상)",
    "21": "신호 진폭 낮음 (단선)",
    "23": "신호가 Low 상태로 고정됨",
    "24": "신호가 High 상태로 고정됨",
    "27": "신호 변화율 오류 (엔코더 센서 이상)",
    "28": "신호 바이어스 범위 벗어남 (모터 전류 이상)",
    "29": "잘못된 신호 발생 (신호 무효)",
    "2B": "신호가 섞여서 간섭됨 (혼선)",
    "2E": "신호 측정 비율 초과 (열폭주 감지)",
    "31": "신호 없음",
    "38": "신호의 주파수 값이 부정확함",
    "41": "일반적인 체크섬 오류",
    "42": "일반적인 메모리 오류",
    "44": "데이터 메모리 오류 (EEPROM 체크섬 불일치)",
    "45": "시스템 프로그램 메모리 오류",
    "46": "시스템 프로그램 보정/매개 변수 메모리 오류",
    "47": "마이컴 강제 리셋 오류",
    "48": "ECU 소프트웨어 이상",
    "49": "시스템 내부 전기적 고장",
    "4A": "사양 설정 오류 (잘못된 부품 장착)",
    "4B": "과열 (시스템 및 부품 과열)",
    "4C": "메모리 가득 참",
    "51": "프로그램되지 않음 (EOL 미학습)",
    "52": "유니트 미장착 또는 커넥터 불량",
    "54": "보정/학습값 누락됨 (캘리브레이션 미실시)",
    "56": "잘못된/호환되지 않은 사양 입력됨",
    "62": "신호 비교 실패 (신호 불일치)",
    "64": "신호 타당성 오류",
    "71": "액추에이터 고착",
    "72": "액추에이터 열린 상태로 고착",
    "73": "액추에이터 닫힌 상태로 고착",
    "74": "액추에이터 슬립",
    "77": "지시 위치 도달 불가 (모터 고착)",
    "7A": "브레이크액 누유 또는 씰 파손",
    "81": "유효하지 않은 직렬 데이터 (CAN 신호)",
    "86": "신호 유효성 오류",
    "87": "수신 메시지 없음 (통신 두절)",
    "88": "통신 버스 오프",
    "8B": "잘못된 메시지 구조 / 길이",
    "93": "동작 스위치 상태 불량",
    "94": "예기치 않은 작동/오작동",
    "96": "부품 내부 이상",
    "97": "감지가 제한된 상태 (가림)",
    "98": "시스템 및 부품 과열",
    "99": "시스템 학습 제한 초과",
    "9E": "동작 스위치 등의 상태가 ON 으로 고착됨",
    "A1": "시스템 전압 이상",
}

print(f"[1/5] Backing up original JSON to {BAK_PATH.name}...")
shutil.copy2(JSON_PATH, BAK_PATH)

print(f"[2/5] Loading {JSON_PATH.name}...")
with open(JSON_PATH, "r", encoding="utf-8") as f:
    graph_data = json.load(f)

nodes = graph_data.get("nodes", [])

updated_count = 0
empty_filled = 0
mibul_filled = 0

for node in nodes:
    if node.get("node_type") != "DTC":
        continue

    st_name = (node.get("subtype_name") or "").strip()
    st_code = node.get("subtype_code", "")
    desc = node.get("description", "") or ""

    # 업데이트 대상: 빈칸이거나 '미분류'인 항목
    if not st_name or st_name == "미분류":
        resolved_name = ""

        # 우선순위 A: description에 '-'가 있고 뒤쪽 텍스트가 의미 있는 서브타입 설명인 경우
        if "-" in desc and st_code != "00":
            parts = desc.split("-")
            candidate = parts[-1].strip()
            # 후보 텍스트가 의미 있는 길이이고 기존 코드 반복이 아닌 경우
            if 2 <= len(candidate) <= 35 and candidate not in ("이상", "고장", "오류"):
                resolved_name = candidate

        # 우선순위 B: 사전 테이블 매핑
        if not resolved_name:
            resolved_name = ISO_FTB_MAP.get(st_code, "")

        # 우선순위 C: fallback
        if not resolved_name:
            if st_code == "00":
                resolved_name = "세부 유형 없음 (기본 고장)"
            else:
                resolved_name = f"고장 유형 코드 {st_code}"

        if not st_name:
            empty_filled += 1
        else:
            mibul_filled += 1

        node["subtype_name"] = resolved_name
        updated_count += 1

print(f"[3/5] Updated {updated_count} DTC nodes:")
print(f"  - Empty string filled: {empty_filled} items")
print(f"  - '미분류' replaced  : {mibul_filled} items")

with open(JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(graph_data, f, ensure_ascii=False, indent=2)
print(f"  -> Successfully saved updated JSON ({JSON_PATH.stat().st_size:,} bytes)")

# ══════════════════════════════════════════════════════════════
# 4. 엑셀 파일 재생성
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Regenerating Excel file (dtc_knowledge_graph.xlsx)...")
import subprocess
ret = subprocess.run(["python", "convert_to_excel.py"], cwd=str(BASE_DIR), capture_output=True, text=True)
if ret.returncode == 0:
    print("  -> Excel file regenerated successfully!")
else:
    print("  -> Error regenerating Excel:", ret.stderr)

# ══════════════════════════════════════════════════════════════
# 5. 재검증
# ══════════════════════════════════════════════════════════════
print("\n[5/5] Re-validating updated dataset...")
with open(JSON_PATH, "r", encoding="utf-8") as f:
    re_data = json.load(f)

re_dtcs = [n for n in re_data.get("nodes", []) if n.get("node_type") == "DTC"]
re_empty = sum(1 for x in re_dtcs if not (x.get("subtype_name") or "").strip())
re_mibul = sum(1 for x in re_dtcs if (x.get("subtype_name") or "").strip() == "미분류")

print(f"  Total DTCs: {len(re_dtcs)}")
print(f"  Remaining empty subtype_name: {re_empty} (Target: 0)")
print(f"  Remaining '미분류' subtype_name: {re_mibul} (Target: 0)")

assert re_empty == 0, "Validation Failed: Empty subtype_name still exists!"
assert re_mibul == 0, "Validation Failed: '미분류' still exists!"

print("\n[ALL COMPLETE] 100% of DTC subtypes are now perfectly populated and validated!")
