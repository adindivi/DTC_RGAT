# -*- coding: utf-8 -*-
"""
dtc_knowledge_graph.json 데이터를 다중 시트의 세련된 엑셀 보고서(.xlsx)로 변환하는 스크립트
"""
import json
from collections import defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE_DIR = Path(__file__).parent.resolve()
JSON_PATH = BASE_DIR / "dtc_knowledge_graph.json"
EXCEL_PATH = BASE_DIR / "dtc_knowledge_graph.xlsx"

print("[1/4] Reading dtc_knowledge_graph.json...")
with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

nodes = data.get("nodes", [])
edges = data.get("edges", [])

# 노드 맵핑
node_by_id = {n["id"]: n for n in nodes}
dtc_nodes = [n for n in nodes if n.get("node_type") == "DTC"]
ecu_nodes = [n for n in nodes if n.get("node_type") == "ECU"]
conn_nodes = [n for n in nodes if n.get("node_type") == "Connector"]

# 엣지 맵핑
dtc_to_ecu = defaultdict(set)
dtc_to_direct_conns = defaultdict(set)
ecu_to_conns = defaultdict(set)
conn_to_ecus = defaultdict(set)
conn_to_direct_dtcs = defaultdict(set)

for e in edges:
    rel = e.get("rel")
    src = e.get("source")
    dst = e.get("target")
    if rel == "SW_IN":
        dtc_to_ecu[src].add(dst)
    elif rel == "HW_MAP":
        dtc_to_direct_conns[src].add(dst)
        conn_to_direct_dtcs[dst].add(src)
    elif rel == "HW_WIRE":
        ecu_to_conns[src].add(dst)
        conn_to_ecus[dst].add(src)

print(f"  Loaded: DTC={len(dtc_nodes)}, ECU={len(ecu_nodes)}, Connector={len(conn_nodes)}, Edges={len(edges)}")

# 워크북 생성
wb = openpyxl.Workbook()
# 기본 시트 제거
wb.remove(wb.active)

# 스타일 정의
font_title = Font(name="맑은 고딕", size=14, bold=True, color="1F4E79")
font_subtitle = Font(name="맑은 고딕", size=10, color="595959")
font_header = Font(name="맑은 고딕", size=10, bold=True, color="FFFFFF")
font_data = Font(name="맑은 고딕", size=9, color="1D1D1F")
font_bold_data = Font(name="맑은 고딕", size=9, bold=True, color="1D1D1F")
font_code = Font(name="Consolas", size=9, bold=True, color="0071E3")

fill_header = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
fill_sub_header = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
fill_zebra = PatternFill(start_color="F7F9FB", end_color="F7F9FB", fill_type="solid")
fill_accent = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
fill_verified = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid") # 연한 초록

align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
align_right = Alignment(horizontal="right", vertical="center")

thin_border = Side(style="thin", color="D9D9D9")
border_all = Border(left=thin_border, right=thin_border, top=thin_border, bottom=thin_border)
header_border = Border(
    left=Side(style="thin", color="FFFFFF"),
    right=Side(style="thin", color="FFFFFF"),
    top=Side(style="medium", color="1F4E79"),
    bottom=Side(style="medium", color="1F4E79")
)

def style_table(ws, start_row, headers, data_rows, col_alignments=None, code_cols=None):
    """표 스타일링 공통 함수"""
    code_cols = code_cols or []
    col_alignments = col_alignments or {}

    # 헤더 작성
    ws.row_dimensions[start_row].height = 26
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = header_border

    # 데이터 작성
    for r_idx, row_data in enumerate(data_rows, start=start_row + 1):
        ws.row_dimensions[r_idx].height = 21
        is_zebra = (r_idx % 2 == 0)
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=r_idx, column=col_idx, value=val)
            cell.border = border_all

            # 정렬
            align_type = col_alignments.get(col_idx, "center")
            if align_type == "left":
                cell.alignment = align_left
            elif align_type == "right":
                cell.alignment = align_right
            else:
                cell.alignment = align_center

            # 폰트
            if col_idx in code_cols:
                cell.font = font_code
            else:
                cell.font = font_data

            # 배경
            if is_zebra:
                cell.fill = fill_zebra

    # 자동 필터
    last_col_letter = get_column_letter(len(headers))
    ws.auto_filter.ref = f"A{start_row}:{last_col_letter}{start_row + len(data_rows)}"
    ws.freeze_panes = f"A{start_row + 1}"

    # 컬럼 너비 자동 조정
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            # 한글/영문 대략적 너비 계산
            l = sum(2 if ord(c) > 128 else 1 for c in val_str)
            if l > max_len:
                max_len = l
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 11), 55)


# ══════════════════════════════════════════════════════════════
# Sheet 1: 요약 대시보드
# ══════════════════════════════════════════════════════════════
print("[2/4] Generating Sheet 1: Summary Dashboard...")
ws1 = wb.create_sheet(title="1. 요약 대시보드")
ws1.views.sheetView[0].showGridLines = True

ws1.cell(row=2, column=2, value="차량 전장 DTC-하네스 지식 그래프 종합 요약").font = font_title
ws1.cell(row=3, column=2, value="Diagnostic Trouble Code Knowledge Graph Summary Report").font = font_subtitle

# 지표 요약 카드
metric_headers = ["항목", "구분", "수량 (개)", "비고"]
metric_data = [
    ["노드 (Nodes)", "고장 진단 코드 (DTC)", len(dtc_nodes), "SAE 표준 및 제조사 전용 DTC"],
    ["노드 (Nodes)", "전자제어장치 (ECU)", len(ecu_nodes), "차량 전장 제어기 (바디/섀시/파워트레인)"],
    ["노드 (Nodes)", "하네스 커넥터 (Connector)", len(conn_nodes), "차체 와이어링 하네스 연결 커넥터"],
    ["노드 (Nodes)", "전체 노드 합계", len(nodes), "총 지식 그래프 노드 수"],
    ["관계 (Edges)", "DTC ➔ ECU (SW_IN)", 1290, "소프트웨어/제어기 고장 검출 관계"],
    ["관계 (Edges)", "DTC ➔ Connector (HW_MAP)", 356, "기존 정비지침서 검증 직결 매핑 (13.5%)"],
    ["관계 (Edges)", "ECU ➔ Connector (HW_WIRE)", 226, "제어기-하네스 물리 배선 연결 관계"],
    ["관계 (Edges)", "전체 엣지 합계", len(edges), "총 관계 엣지 수"],
]

for col_idx, h in enumerate(metric_headers, 2):
    cell = ws1.cell(row=5, column=col_idx, value=h)
    cell.font = font_header
    cell.fill = fill_header
    cell.alignment = align_center

for r_idx, row in enumerate(metric_data, start=6):
    ws1.row_dimensions[r_idx].height = 20
    is_sum = "합계" in row[1]
    for c_idx, val in enumerate(row, start=2):
        cell = ws1.cell(row=r_idx, column=c_idx, value=val)
        cell.border = border_all
        cell.alignment = align_left if c_idx == 2 or c_idx == 5 else align_center
        cell.font = font_bold_data if is_sum else font_data
        if is_sum:
            cell.fill = fill_accent

# 시스템별 DTC 통계 (P, B, C, U)
sys_count = defaultdict(int)
cat_count = defaultdict(int)
for n in dtc_nodes:
    code = n.get("code", "")
    sys_code = code[0] if code else "기타"
    sys_count[sys_code] += 1
    cat = n.get("fault_category", "기타")
    cat_count[cat] += 1

sys_names = {"P": "파워트레인 (Powertrain)", "B": "바디 (Body)", "C": "섀시 (Chassis)", "U": "네트워크 통신 (Network)"}
sys_rows = []
for sc in ["P", "B", "C", "U"]:
    cnt = sys_count.get(sc, 0)
    pct = f"{(cnt / len(dtc_nodes) * 100):.1f}%" if dtc_nodes else "0%"
    sys_rows.append([sc, sys_names.get(sc, sc), cnt, pct])

ws1.cell(row=16, column=2, value="[시스템 분류별 DTC 현황]").font = Font(name="맑은 고딕", size=11, bold=True, color="1F4E79")
for col_idx, h in enumerate(["코드", "시스템 명칭", "DTC 개수", "점유율"], 2):
    cell = ws1.cell(row=17, column=col_idx, value=h)
    cell.font = font_header
    cell.fill = fill_sub_header
    cell.alignment = align_center

for r_idx, row in enumerate(sys_rows, start=18):
    ws1.row_dimensions[r_idx].height = 20
    for c_idx, val in enumerate(row, start=2):
        cell = ws1.cell(row=r_idx, column=c_idx, value=val)
        cell.border = border_all
        cell.alignment = align_left if c_idx == 3 else align_center
        cell.font = font_data

# 컬럼 너비 지정
ws1.column_dimensions["A"].width = 4
ws1.column_dimensions["B"].width = 16
ws1.column_dimensions["C"].width = 28
ws1.column_dimensions["D"].width = 16
ws1.column_dimensions["E"].width = 38


# ══════════════════════════════════════════════════════════════
# Sheet 2: DTC 종합 마스터
# ══════════════════════════════════════════════════════════════
print("[3/4] Generating Sheet 2: DTC Master...")
ws2 = wb.create_sheet(title="2. DTC 종합 마스터")
ws2.views.sheetView[0].showGridLines = True

dtc_headers = [
    "DTC 코드", "시스템", "규격 구분", "담당 ECU", "고장 카테고리",
    "서브타입 코드", "서브타입 명칭", "부품 위치", "고장 상세 설명",
    "마스터 검증 커넥터 (HW_MAP)", "제어기 물리배선 커넥터 수", "연계 가능 커넥터 목록 (HW_WIRE)"
]

dtc_rows = []
for n in dtc_nodes:
    nid = n["id"]
    code = n.get("code", "")
    sys_name = f"{n.get('system_code', '')} ({n.get('system_name', '')})"
    mfr = "제조사 전용" if str(n.get("mfr_specific")).lower() in ("true", "1") else "SAE 표준"
    ecu = n.get("ecu_name", "")
    cat = n.get("fault_category", "")
    st_code = n.get("subtype_code", "")
    st_name = n.get("subtype_name", "")
    pos = n.get("position", "")
    desc = n.get("description", "")

    # 직결 커넥터
    direct_conns = [node_by_id[c].get("name", c) for c in dtc_to_direct_conns.get(nid, [])]
    direct_str = ", ".join(direct_conns) if direct_conns else "미매핑 (RGAT 예측 대상)"

    # 연계 제어기를 통한 물리 배선 커넥터
    ecus = dtc_to_ecu.get(nid, set())
    wire_conns = set()
    for eid in ecus:
        for cid in ecu_to_conns.get(eid, set()):
            wire_conns.add(node_by_id[cid].get("name", cid))
    wire_str = ", ".join(sorted(wire_conns)) if wire_conns else "배선 정보 없음"

    dtc_rows.append([
        code, sys_name, mfr, ecu, cat,
        st_code, st_name, pos, desc,
        direct_str, len(wire_conns), wire_str
    ])

dtc_rows.sort(key=lambda x: x[0])
style_table(
    ws2, start_row=1, headers=dtc_headers, data_rows=dtc_rows,
    col_alignments={1: "center", 2: "center", 3: "center", 4: "center", 5: "center",
                    6: "center", 7: "center", 8: "center", 9: "left", 10: "left", 11: "right", 12: "left"},
    code_cols=[1, 6]
)


# ══════════════════════════════════════════════════════════════
# Sheet 3: ECU 제어기 현황
# ══════════════════════════════════════════════════════════════
print("  Generating Sheet 3: ECU List...")
ws3 = wb.create_sheet(title="3. ECU 제어기 현황")
ws3.views.sheetView[0].showGridLines = True

ecu_headers = ["ECU 명칭", "제어기 설명", "관할 DTC 수", "물리 연결 커넥터 수", "연결 하네스 커넥터 목록"]
ecu_rows = []
for n in ecu_nodes:
    nid = n["id"]
    name = n.get("name", "")
    info = n.get("ecu_info", "")

    # 관할 DTC
    dtc_count = sum(1 for d in dtc_nodes if d.get("ecu_name") == name)

    # 물리 연결 커넥터
    conns = [node_by_id[c].get("name", c) for c in ecu_to_conns.get(nid, [])]
    conn_str = ", ".join(sorted(conns)) if conns else "연결 배선 없음"

    ecu_rows.append([name, info, dtc_count, len(conns), conn_str])

ecu_rows.sort(key=lambda x: -x[2])  # DTC 수 많은 순
style_table(
    ws3, start_row=1, headers=ecu_headers, data_rows=ecu_rows,
    col_alignments={1: "left", 2: "left", 3: "right", 4: "right", 5: "left"}
)


# ══════════════════════════════════════════════════════════════
# Sheet 4: 하네스 커넥터 목록
# ══════════════════════════════════════════════════════════════
print("  Generating Sheet 4: Connector List...")
ws4 = wb.create_sheet(title="4. 하네스 커넥터 목록")
ws4.views.sheetView[0].showGridLines = True

conn_headers = ["커넥터 명칭", "차체 설치 위치", "연결 ECU 수", "연결 제어기 목록", "직접 매핑 DTC 수 (HW_MAP)", "직접 매핑 DTC 코드 목록"]
conn_rows = []
for n in conn_nodes:
    nid = n["id"]
    name = n.get("name", "")
    loc = n.get("location", "") or "위치 미정"

    ecus = [node_by_id[e].get("name", e) for e in conn_to_ecus.get(nid, [])]
    ecu_str = ", ".join(sorted(ecus)) if ecus else "배선 제어기 없음"

    mapped_dtcs = [node_by_id[d].get("code", d) for d in conn_to_direct_dtcs.get(nid, [])]
    mapped_str = ", ".join(sorted(mapped_dtcs)) if mapped_dtcs else "-"

    conn_rows.append([name, loc, len(ecus), ecu_str, len(mapped_dtcs), mapped_str])

conn_rows.sort(key=lambda x: -x[4])  # 매핑 DTC 많은 순
style_table(
    ws4, start_row=1, headers=conn_headers, data_rows=conn_rows,
    col_alignments={1: "left", 2: "center", 3: "right", 4: "left", 5: "right", 6: "left"}
)


# ══════════════════════════════════════════════════════════════
# Sheet 5: 전체 엣지 관계망
# ══════════════════════════════════════════════════════════════
print("  Generating Sheet 5: Edges Relationship...")
ws5 = wb.create_sheet(title="5. 전체 엣지 관계망")
ws5.views.sheetView[0].showGridLines = True

edge_headers = ["관계 타입", "관계 설명", "출발 노드 유형", "출발 노드 라벨/코드", "도착 노드 유형", "도착 노드 라벨/명칭", "출발 ID", "도착 ID"]
rel_desc = {
    "SW_IN": "소프트웨어 고장 검출 (DTC ➔ ECU)",
    "HW_MAP": "정비지침서 검증 직결 매핑 (DTC ➔ Connector)",
    "HW_WIRE": "차량 물리 배선 하네스 (ECU ➔ Connector)",
}

edge_rows = []
for e in edges:
    rel = e.get("rel", "")
    src = e.get("source", "")
    dst = e.get("target", "")

    src_nd = node_by_id.get(src, {})
    dst_nd = node_by_id.get(dst, {})

    src_type = src_nd.get("node_type", "Unknown")
    dst_type = dst_nd.get("node_type", "Unknown")

    src_label = src_nd.get("code") or src_nd.get("name") or src_nd.get("label", src)
    dst_label = dst_nd.get("code") or dst_nd.get("name") or dst_nd.get("label", dst)

    edge_rows.append([
        rel, rel_desc.get(rel, rel),
        src_type, src_label,
        dst_type, dst_label,
        src, dst
    ])

edge_rows.sort(key=lambda x: (x[0], x[3]))
style_table(
    ws5, start_row=1, headers=edge_headers, data_rows=edge_rows,
    col_alignments={1: "center", 2: "left", 3: "center", 4: "left", 5: "center", 6: "left", 7: "left", 8: "left"}
)

print(f"[4/4] Saving workbook to {EXCEL_PATH}...")
try:
    wb.save(str(EXCEL_PATH))
    print(f"[SUCCESS] Excel file generated successfully! Size: {EXCEL_PATH.stat().st_size:,} bytes")
except PermissionError:
    fallback_path = BASE_DIR / "dtc_knowledge_graph_updated.xlsx"
    print(f"[WARNING] {EXCEL_PATH.name} is currently open in Excel.")
    print(f"          Saving to {fallback_path.name} instead...")
    wb.save(str(fallback_path))
    print(f"[SUCCESS] Excel file saved as {fallback_path.name}! Size: {fallback_path.stat().st_size:,} bytes")
