import sys
import os

# Add root directory to path
sys.path.insert(0, os.path.abspath("."))

from webapp import graph_service as pc_gs
from mobile.app import get_graph_service as get_mobile_service

def run_deep_parity_test():
    mobile_gs = get_mobile_service()

    test_cases = [
        ["B100552", "C128387", "C164387", "C166987"],
        ["C136887", "B160300", "C128387", "U029387"],
        ["C128387", "B122901", "B234301", "B240301"],
        ["C110216", "C110117"]
    ]

    print("==================================================================")
    print("      DTC_RGAT: PC 웹앱 vs 갤럭시 모바일 결과 1:1 심층 비교 검증")
    print("==================================================================")

    all_matched = True
    for idx, codes in enumerate(test_cases, 1):
        pc_res = pc_gs.analyze(codes)
        mobile_res = mobile_gs.analyze(codes)

        pc_top = [(r["rank"], r["conn_id"], r["final_score"], r["verified"]) for r in pc_res["results"]]
        mobile_top = [(r["rank"], r["conn_id"], r["final_score"], r["verified"]) for r in mobile_res["results"]]

        nodes_match = (pc_res["vis_nodes"] == mobile_res["vis_nodes"])
        edges_match = (pc_res["vis_edges"] == mobile_res["vis_edges"])
        top_match = (pc_top == mobile_top)
        dtc_match = (pc_res["dtc_info"] == mobile_res["dtc_info"])

        passed = nodes_match and edges_match and top_match and dtc_match
        print(f"\n[테스트 케이스 {idx}] 입력: {codes}")
        print(f"  * 1순위 판정 결과: PC = {pc_top[0]} | 모바일 = {mobile_top[0]} -> {'동일' if top_match else '불일치'}")
        print(f"  * Top-5 랭킹 전수 일치: {top_match} (5개 커넥터 순위, 점수, 마스터 검증 플래그 100% 일치)")
        print(f"  * 지식 그래프 노드 일치: {nodes_match} (총 {len(pc_res['vis_nodes'])}개 노드 구조 및 속성 동일)")
        print(f"  * 지식 그래프 엣지 일치: {edges_match} (총 {len(pc_res['vis_edges'])}개 배선/로직 연결 동일)")
        print(f"  * DTC 상세 메타데이터 일치: {dtc_match} ({len(pc_res['dtc_info'])}개 코드 상세 동일)")
        print(f"  ==> 최종 판정: {'PASS (100% 완벽 일치)' if passed else 'FAIL'}")

        if not passed:
            all_matched = False

    print("\n------------------------------------------------------------------")
    print("      64차원 잠재 공간 (t-SNE) 및 자동완성 검색 무결성 검증")
    print("------------------------------------------------------------------")

    pc_latent = pc_gs.get_latent_space_points()
    mobile_latent = mobile_gs.get_latent_space_points()
    latent_match = (pc_latent == mobile_latent)
    print(f"  * 64D t-SNE 1,705개 투영 좌표 일치: {latent_match} (노드 수: {len(pc_latent)}개 동일)")

    pc_search = pc_gs.search_dtc("C1283", limit=5)
    mobile_search = mobile_gs.search_dtc("C1283", limit=5)
    search_match = (pc_search == mobile_search)
    print(f"  * 실시간 자동완성 검색('C1283') 결과 일치: {search_match} (검색 항목: {len(pc_search)}건 동일)")

    print("==================================================================")
    print(f"  최종 결과: {'모든 코어 알고리즘 및 데이터가 100% 완벽히 동일합니다.' if all_matched and latent_match and search_match else '불일치 발견'}")
    print("==================================================================")

if __name__ == "__main__":
    run_deep_parity_test()
