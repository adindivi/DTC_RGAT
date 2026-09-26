# -*- coding: utf-8 -*-
"""
지식 그래프 및 RGAT 링크 예측 추론 서비스
단일 책임 원칙(SRP) 준수 및 데드 코드/중복 제거 적용
"""
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("DTC_RGAT.Service")


class KnowledgeGraphService:
    """차량 전장 DTC 및 배선 커넥터 지식 그래프 분석 서비스"""

    def __init__(
        self,
        graph_path: Path,
        embed_path: Path,
        alpha: float = 0.7,
        beta: float = 0.3,
        top_k: int = 20,
    ):
        self.alpha = alpha
        self.beta = beta
        self.top_k = top_k

        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self.embeddings: np.ndarray = np.empty((0, 64))

        self.node_id_to_idx: dict[str, int] = {}
        self.node_by_id: dict[str, dict[str, Any]] = {}
        self.dtc_to_ecus: dict[str, set[str]] = defaultdict(set)
        self.dtc_to_conns: dict[str, set[str]] = defaultdict(set)
        self.ecu_to_conns: dict[str, set[str]] = defaultdict(set)
        self.code_to_nids: dict[str, list[str]] = defaultdict(list)
        self.conn_ids: list[str] = []
        self.conn_id_to_idx: dict[str, int] = {}
        self.conn_embs: np.ndarray = np.empty((0, 64))
        self.dtc_master_dedup: list[dict[str, str]] = []
        self.base_dir: Path = graph_path.parent
        self._latent_points_cache: list[dict[str, Any]] | None = None

        self._load_data(graph_path, embed_path)

    def _load_data(self, graph_path: Path, embed_path: Path) -> None:
        """그래프 JSON 및 RGAT 임베딩 적재 및 고속 인덱스 생성"""
        logger.info(f"Loading knowledge graph from {graph_path}...")
        if not graph_path.exists():
            raise FileNotFoundError(f"Knowledge graph file not found: {graph_path}")
        if not embed_path.exists():
            raise FileNotFoundError(f"Embeddings file not found: {embed_path}")

        with open(graph_path, "r", encoding="utf-8") as f:
            gdata = json.load(f)

        self.nodes = gdata.get("nodes", [])
        self.edges = gdata.get("edges", [])
        self.embeddings = np.load(str(embed_path))

        self.node_id_to_idx = {n["id"]: i for i, n in enumerate(self.nodes)}
        self.node_by_id = {n["id"]: n for n in self.nodes}
        self.conn_to_ecus: dict[str, set[str]] = defaultdict(set)

        for e in self.edges:
            rel = e.get("rel", "")
            src = e.get("source", "")
            dst = e.get("target", "")
            if rel in ("SW_IN", "SW_LOGIC"):
                self.dtc_to_ecus[src].add(dst)
            elif rel == "HW_MAP":
                self.dtc_to_conns[src].add(dst)
            elif rel == "HW_WIRE":
                self.ecu_to_conns[src].add(dst)
                src_node = self.node_by_id.get(src, {})
                if src_node.get("node_type") == "ECU":
                    self.conn_to_ecus[dst].add(src_node.get("name", "?"))

        for n in self.nodes:
            if n.get("node_type") == "DTC":
                code = n.get("code", "").upper().strip()
                if code:
                    self.code_to_nids[code].append(n["id"])

        self.conn_ids = [
            n["id"] for n in self.nodes if n.get("node_type") == "Connector"
        ]
        # O(1) 고속 조회를 위한 매핑 딕셔너리 (list.index 대체)
        self.conn_id_to_idx = {cid: idx for idx, cid in enumerate(self.conn_ids)}

        conn_indices = [self.node_id_to_idx.get(c, 0) for c in self.conn_ids]
        self.conn_embs = self.embeddings[conn_indices]

        # 자동완성용 DTC 마스터 목록 (코드 기준 중복 제거)
        dtc_master: list[dict[str, str]] = []
        for n in self.nodes:
            if n.get("node_type") == "DTC":
                dtc_master.append(
                    {
                        "code": n.get("code", ""),
                        "ecu": n.get("ecu_name", ""),
                        "desc": (n.get("description", "") or "")[:60],
                        "cat": n.get("fault_category", ""),
                    }
                )

        seen_codes: dict[str, dict[str, str]] = {}
        for d in dtc_master:
            c = d["code"]
            if c not in seen_codes or d["desc"]:
                seen_codes[c] = d
        self.dtc_master_dedup = sorted(seen_codes.values(), key=lambda x: x["code"])

        logger.info(
            f"Knowledge graph initialized successfully. Nodes: {len(self.nodes)}, "
            f"Connectors: {len(self.conn_ids)}, Unique DTC Codes: {len(self.dtc_master_dedup)}"
        )

    def search_dtc(self, query: str, limit: int = 20) -> list[dict[str, str]]:
        """DTC 코드 자동완성 검색"""
        q = query.upper().strip()
        if not q:
            return []
        return [d for d in self.dtc_master_dedup if q in d["code"]][:limit]

    def _get_conn_ecus(self, cid: str) -> list[str]:
        """특정 커넥터와 물리 배선(HW_WIRE)으로 연결된 ECU 이름 목록 O(1) 고속 조회"""
        return sorted(self.conn_to_ecus.get(cid, set()))

    def get_latent_space_points(self) -> list[dict[str, Any]]:
        """64차원 노드 임베딩의 2D t-SNE 투영 좌표 목록 반환 (인메모리 캐싱 적용)"""
        if self._latent_points_cache is not None:
            return self._latent_points_cache

        latent_file = self.base_dir / "rgat_latent_2d.json"
        if latent_file.exists():
            try:
                with open(latent_file, "r", encoding="utf-8") as f:
                    self._latent_points_cache = json.load(f)
                    return self._latent_points_cache
            except Exception as e:
                logger.error(f"Failed to load latent space cache from {latent_file}: {e}")
        return []

    def analyze(
        self,
        input_codes: list[str],
        topology_mask: bool = True,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        """
        입력된 다중 DTC 코드를 기반으로 하이브리드 근본원인 랭킹 및 시각화 데이터 도출
        - topology_mask=True: 2-Hop 배선 도달 가능 커넥터에 집중하여 360개 비연결 노이즈 차단
        """
        target_top_k = top_k if top_k is not None else self.top_k
        dtc_info: list[dict[str, Any]] = []
        unknown: list[str] = []

        for code in input_codes:
            code_upper = code.upper().strip()
            nids = self.code_to_nids.get(code_upper, [])
            if not nids:
                unknown.append(code_upper)
                continue

            reached_ecus: set[str] = set()
            reached_conns: set[str] = set()
            for nid in nids:
                for eid in self.dtc_to_ecus.get(nid, ()):
                    reached_ecus.add(eid)
                    for cid in self.ecu_to_conns.get(eid, ()):
                        reached_conns.add(cid)
                for cid in self.dtc_to_conns.get(nid, ()):
                    reached_conns.add(cid)

            embs = [
                self.embeddings[self.node_id_to_idx[nid]]
                for nid in nids
                if nid in self.node_id_to_idx
            ]
            dim = self.embeddings.shape[1] if self.embeddings.ndim > 1 else 64
            mean_emb = np.mean(embs, axis=0) if embs else np.zeros(dim)

            first_node = self.node_by_id.get(nids[0], {})
            dtc_info.append(
                {
                    "code": code_upper,
                    "nids": nids,
                    "ecu_names": sorted(
                        {self.node_by_id[e].get("name", "?") for e in reached_ecus}
                    ),
                    "struct_conns": reached_conns,
                    "mean_emb": mean_emb,
                    "has_struct": bool(reached_conns),
                    "desc": (first_node.get("description", "") or "")[:70],
                    "cat": first_node.get("fault_category", ""),
                    "system_code": first_node.get("system_code", ""),
                    "system_name": first_node.get("system_name", ""),
                    "mfr_specific": first_node.get("mfr_specific", ""),
                    "subtype_code": first_node.get("subtype_code", ""),
                    "subtype_name": first_node.get("subtype_name", ""),
                    "position": first_node.get("position", ""),
                }
            )

        n_valid = len(dtc_info)
        if n_valid == 0:
            return {
                "error": "유효한 DTC 코드가 없습니다.",
                "unknown": unknown,
                "dtc_info": [],
                "results": [],
                "vis_nodes": [],
                "vis_edges": [],
                "topology_mask_applied": False,
                "reachable_conns_count": 0,
            }

        # ── 1. 마스터 검증 직결 HW_MAP 매핑 집계 ───────────────────────
        verified_conn_codes: dict[str, set[str]] = defaultdict(set)
        for info in dtc_info:
            for nid in info["nids"]:
                for cid in self.dtc_to_conns.get(nid, ()):
                    verified_conn_codes[cid].add(info["code"])

        # ── 2. 구조 점수 (2-Hop 배선 도달 비율) 계산 ─────────────────
        struct_hit: dict[str, set[str]] = defaultdict(set)
        all_reachable_conns: set[str] = set()
        for info in dtc_info:
            for cid in info["struct_conns"]:
                struct_hit[cid].add(info["code"])
                all_reachable_conns.add(cid)

        struct_norm = np.array(
            [len(struct_hit.get(c, ())) / n_valid for c in self.conn_ids]
        )

        # ── 3. RGAT 임베딩 유사도 점수 계산 ──────────────────────────
        sum_emb = np.sum([d["mean_emb"] for d in dtc_info], axis=0)
        rgat_raw = self.conn_embs @ sum_emb
        min_v, max_v = rgat_raw.min(), rgat_raw.max()
        rgat_norm = (rgat_raw - min_v) / (max_v - min_v + 1e-9)

        # ── 4. 하이브리드 점수 산출 및 토폴로지 마스킹 ────────────────
        final_scores = self.alpha * struct_norm + self.beta * rgat_norm

        mask_active = bool(topology_mask and all_reachable_conns)
        effective_scores = final_scores.copy()
        if mask_active:
            # 2-Hop 물리 배선 도달이 불가능한 커넥터(순수 노이즈) 마스킹 격리
            for conn_idx, conn_id in enumerate(self.conn_ids):
                if conn_id not in all_reachable_conns:
                    effective_scores[conn_idx] = -1e9

        # ── 5. 순위 리스트 조립 ──────────────────────────────────────
        results: list[dict[str, Any]] = []
        verified_added: set[str] = set()

        # 1순위: 마스터 직접 매핑 검증 커넥터 (최고 점수 2.0 고정)
        sorted_verified = sorted(
            verified_conn_codes, key=lambda c: -len(verified_conn_codes[c])
        )
        for conn_id in sorted_verified:
            if len(results) >= target_top_k:
                break
            conn_idx = self.conn_id_to_idx.get(conn_id, -1)
            conn_node = self.node_by_id.get(conn_id, {})
            hit_codes = sorted(verified_conn_codes[conn_id])
            results.append(
                {
                    "rank": len(results) + 1,
                    "conn_id": conn_id,
                    "name": conn_node.get("name", conn_id),
                    "location": conn_node.get("location", ""),
                    "final_score": 2.0,
                    "struct_score": 2.0,
                    "rgat_score": float(rgat_norm[conn_idx]) if conn_idx >= 0 else 0.0,
                    "n_hit": len(hit_codes),
                    "n_valid": n_valid,
                    "hit_codes": hit_codes,
                    "conn_ecus": self._get_conn_ecus(conn_id),
                    "verified": True,
                    "is_reachable": True,
                }
            )
            verified_added.add(conn_id)

        # 2순위: 하이브리드 점수 기반 커넥터 (마스킹 적용)
        ranked_indices = np.argsort(effective_scores)[::-1]
        for conn_idx in ranked_indices:
            if len(results) >= target_top_k:
                break
            if mask_active and effective_scores[conn_idx] < -1e8:
                # 도달 가능한 후보군을 모두 채웠으면 비연결 노이즈 커넥터 배제
                break
            conn_id = self.conn_ids[conn_idx]
            if conn_id in verified_added:
                continue
            conn_node = self.node_by_id.get(conn_id, {})
            hit_codes = sorted(struct_hit.get(conn_id, ()))
            results.append(
                {
                    "rank": len(results) + 1,
                    "conn_id": conn_id,
                    "name": conn_node.get("name", conn_id),
                    "location": conn_node.get("location", ""),
                    "final_score": round(float(final_scores[conn_idx]), 4),
                    "struct_score": round(float(struct_norm[conn_idx]), 4),
                    "rgat_score": round(float(rgat_norm[conn_idx]), 4),
                    "n_hit": len(hit_codes),
                    "n_valid": n_valid,
                    "hit_codes": hit_codes,
                    "conn_ecus": self._get_conn_ecus(conn_id),
                    "verified": False,
                    "is_reachable": bool(conn_id in all_reachable_conns),
                }
            )


        # ── 6. vis.js 계층형 그래프 데이터 빌드 ──────────────────────
        vis_nodes, vis_edges = self._build_vis_graph(
            dtc_info, results[:5], n_valid
        )

        # JSON 직렬화 안전성 처리 (Numpy 배열 및 내부 객체 제외)
        safe_dtc_info = [
            {k: v for k, v in d.items() if k not in ("mean_emb", "struct_conns", "nids")}
            for d in dtc_info
        ]

        return {
            "input_codes": input_codes,
            "unknown": unknown,
            "dtc_info": safe_dtc_info,
            "results": results,
            "vis_nodes": vis_nodes,
            "vis_edges": vis_edges,
            "topology_mask_applied": mask_active,
            "reachable_conns_count": len(all_reachable_conns),
        }

    def _build_vis_graph(
        self,
        dtc_info: list[dict[str, Any]],
        top5_results: list[dict[str, Any]],
        n_valid: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        Top-5 커넥터와 관련된 3계층(DTC -> ECU -> Connector) 시각화 노드 및 엣지 생성
        - SRP 준수: 커넥터 노드, DTC/ECU 계층, AI 가상 경로 생성을 독립 함수로 분리
        """
        vis_nodes: list[dict[str, Any]] = []
        vis_edges: list[dict[str, Any]] = []
        added_node_ids: set[str] = set()
        added_edge_keys: set[tuple[str, str, str]] = set()

        def add_node(
            node_id: str,
            label: str,
            group: str,
            title: str,
            size: int = 18,
            shape: str = "dot",
            level: int = 0,
        ) -> None:
            if node_id not in added_node_ids:
                added_node_ids.add(node_id)
                vis_nodes.append(
                    {
                        "id": node_id,
                        "label": label,
                        "group": group,
                        "title": title,
                        "size": size,
                        "shape": shape,
                        "level": level,
                    }
                )

        def add_edge(
            from_node: str,
            to_node: str,
            color: str,
            title: str,
            width: float = 1.5,
            dashes: bool = False,
        ) -> None:
            key = (from_node, to_node, title)
            if key not in added_edge_keys:
                added_edge_keys.add(key)
                vis_edges.append(
                    {
                        "from": from_node,
                        "to": to_node,
                        "color": {"color": color},
                        "width": width,
                        "arrows": {"to": {"scaleFactor": 0.5}},
                        "title": title,
                        "dashes": dashes,
                    }
                )

        # 1. Level 2: 커넥터 노드 등록 (오른쪽 종단)
        top5_conn_ids = self._create_connector_nodes(top5_results, n_valid, add_node)

        # 2. Level 0 (DTC) -> Level 1 (ECU) -> Level 2 (Connector) 계층 및 물리 배선 구축
        self._create_dtc_and_ecu_hierarchy(dtc_info, top5_conn_ids, add_node, add_edge)

        # 3. AI_HW_WIRE 가상 추천 배선 등록
        self._create_ai_inferred_wires(vis_nodes, vis_edges, dtc_info, top5_results, add_edge)

        return vis_nodes, vis_edges

    def _create_connector_nodes(
        self,
        top5_results: list[dict[str, Any]],
        n_valid: int,
        add_node: Any,
    ) -> set[str]:
        """Level 2: 커넥터 노드 등록 (오른쪽 종단)"""
        top5_conn_ids: set[str] = {r["conn_id"] for r in top5_results}
        for result in top5_results:
            conn_id = result["conn_id"]
            conn_name = result["name"]
            rank_num = result["rank"]
            n_hit = result["n_hit"]
            verified_tag = "[검증] " if result.get("verified") else ""
            group = (
                "conn_top1"
                if rank_num == 1
                else ("conn_top" if rank_num <= 3 else "conn")
            )
            size = 32 if rank_num == 1 else (24 if rank_num <= 3 else 18)
            short_name = conn_name.split("/")[0].strip() if "/" in conn_name else conn_name
            display_name = short_name[:18] + ("…" if len(short_name) > 18 else "")

            add_node(
                node_id=conn_id,
                label=display_name,
                group=group,
                title=(
                    f"{verified_tag}커넥터: {conn_name}\n"
                    f"연결 DTC: {n_hit}/{n_valid}개\n"
                    f"순위: #{rank_num}\n"
                    f"점수: {result['final_score']}"
                ),
                size=size,
                shape="box",
                level=2,
            )
        return top5_conn_ids

    def _create_dtc_and_ecu_hierarchy(
        self,
        dtc_info: list[dict[str, Any]],
        top5_conn_ids: set[str],
        add_node: Any,
        add_edge: Any,
    ) -> None:
        """Level 0 (DTC) -> Level 1 (ECU) -> Level 2 (Connector) 인과 계층 및 물리 배선 구축"""
        for info in dtc_info:
            code = info["code"]
            cat = info.get("cat", "") or "기타"
            dtc_vis_id = f"VIS_DTC::{code}"
            dtc_title = f"DTC: {code}\n카테고리: {cat}\n{info.get('desc', '')}"

            # 1. Level 0: DTC 노드 전수 표기 보장
            add_node(
                node_id=dtc_vis_id,
                label=code,
                group="dtc_input",
                title=dtc_title,
                size=22,
                shape="box",
                level=0,
            )

            # 이 코드에 속한 지식 그래프 내부 DTC 인스턴스 nids 수집
            nids = self.code_to_nids.get(code, [])
            all_ecus: list[str] = []
            for nid in nids:
                for ecu_id in self.dtc_to_ecus.get(nid, ()):
                    if ecu_id not in all_ecus:
                        all_ecus.append(ecu_id)

            # Top 5 커넥터와 물리 배선(HW_WIRE)이 닿는 ECU를 최우선 선택
            connected_ecus = [
                ecu_id for ecu_id in all_ecus
                if (self.ecu_to_conns.get(ecu_id, set()) & top5_conn_ids)
            ]
            target_ecus = connected_ecus if connected_ecus else (all_ecus[:1] if all_ecus else [])

            for ecu_id in target_ecus:
                ecu_name = self.node_by_id.get(ecu_id, {}).get("name", "?")
                add_node(
                    node_id=ecu_id,
                    label=ecu_name,
                    group="ecu",
                    title=f"ECU: {ecu_name}",
                    size=20,
                    shape="box",
                    level=1,
                )
                # DTC -> ECU (SW_LOGIC 로직관계)
                add_edge(
                    from_node=dtc_vis_id,
                    to_node=ecu_id,
                    color="#64748b",
                    title="SW_LOGIC (로직관계)",
                    width=1.5,
                    dashes=False,
                )

                # ECU -> Top 5 커넥터 (HW_WIRE 물리관계)
                connecting_conns = self.ecu_to_conns.get(ecu_id, set()) & top5_conn_ids
                for conn_id in connecting_conns:
                    add_edge(
                        from_node=ecu_id,
                        to_node=conn_id,
                        color="#3b82f6",
                        title="HW_WIRE (물리관계)",
                        width=2.5,
                        dashes=False,
                    )

            # DTC -> Connector 직접 연결 (HW_MAP 마스터 직접 검증 링크 보존)
            for nid in nids:
                direct_conns = self.dtc_to_conns.get(nid, set()) & top5_conn_ids
                for conn_id in direct_conns:
                    add_edge(
                        from_node=dtc_vis_id,
                        to_node=conn_id,
                        color="#2563eb",
                        title="HW_MAP (검증매핑)",
                        width=2.5,
                        dashes=False,
                    )

    def _create_ai_inferred_wires(
        self,
        vis_nodes: list[dict[str, Any]],
        vis_edges: list[dict[str, Any]],
        dtc_info: list[dict[str, Any]],
        top5_results: list[dict[str, Any]],
        add_edge: Any,
    ) -> None:
        """회로도상 물리 배선이 없지만 AI(RGAT)가 유사도로 추천한 가상 경로 (AI_HW_WIRE: 연하늘 점선)"""
        # C-1. 회로도상 물리 배선이 확인되지 않는 비도달 커넥터 (is_reachable == False)
        vis_node_ids = {n["id"] for n in vis_nodes}
        for result in top5_results:
            conn_id = result["conn_id"]
            if not result.get("is_reachable", True):
                linked = False
                for info in dtc_info:
                    for nid in self.code_to_nids.get(info["code"], []):
                        for ecu_id in self.dtc_to_ecus.get(nid, ()):
                            if ecu_id in vis_node_ids:
                                add_edge(
                                    from_node=ecu_id,
                                    to_node=conn_id,
                                    color="#93c5fd",
                                    title="AI_HW_WIRE (추론물리관계)",
                                    width=2.0,
                                    dashes=True,
                                )
                                linked = True
                                break
                        if linked:
                            break

        # C-2. 활성화된 제어기 중 Top 5 커넥터와 물리 배선이 하나도 없는 제어기
        ecus_with_hw = {
            e["from"] for e in vis_edges if e.get("title") and "HW_WIRE" in e["title"] and not e.get("dashes")
        }
        vis_ecus = [n["id"] for n in vis_nodes if n.get("group") == "ecu"]
        unlinked_ecus = [ecu_id for ecu_id in vis_ecus if ecu_id not in ecus_with_hw]

        if top5_results:
            target_conns = [r["conn_id"] for r in top5_results[:2]]
            for ecu_id in unlinked_ecus:
                for target_conn_id in target_conns:
                    add_edge(
                        from_node=ecu_id,
                        to_node=target_conn_id,
                        color="#93c5fd",
                        title="AI_HW_WIRE (추론물리관계)",
                        width=2.0,
                        dashes=True,
                    )
