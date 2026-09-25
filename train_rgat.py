# -*- coding: utf-8 -*-
"""
RGAT (Relational Graph Attention Network) — DTC 지식 그래프 링크 예측
======================================================================
그래프 구조:
  - 노드: DTC (1290) | ECU (40) | Connector (375)
  - 엣지 타입 5개 (물리/논리 양방향 + self-loop):
      r=0  SW_IN       (DTC→ECU)        ← 논리 관계
      r=1  SW_IN_REV   (ECU→DTC)
      r=2  HW_WIRE     (ECU→Conn)       ← 물리 배선
      r=3  HW_WIRE_REV (Conn→ECU)
      r=4  SELF_LOOP   (노드→자기자신)   ← 자기 피처 보존용 (필수)

노드 입력 임베딩(64차원) = 학습형 임베딩(32) + DTC 코드 구조 피처 투영(32)
  - 피처(38차원): 노드타입(3) + 시스템P/B/C/U(4) + 제조사전용(1)
                 + 서브타입(14) + 고장카테고리(10) + 커넥터위치(6)
  - self-loop이 없으면 같은 ECU에 속한 DTC끼리는 이웃이 완전히 같아
    RGATConv가 자기 피처를 무시하고 이웃 정보만 집계하는 특성 때문에
    서로 다른 코드인데도 임베딩이 코사인 유사도 1.0000으로 동일해진다
    (예: C224077이 검증된 C163887의 결과를 그대로 복제).
    self-loop 추가로 이 문제를 해결했다.

학습 과제: 링크 예측 (Link Prediction)
  - 목표: 마스터에 없는 DTC→Connector 링크(HW_MAP, 86.5%) 추론
  - 입력 그래프: SW_IN + HW_WIRE + SELF_LOOP (HW_MAP은 학습 대상이라 제외)
  - 양성 샘플: 기존 HW_MAP 356건(174쌍) → 80/20 학습/테스트
  - 음성 샘플: (DTC, Connector) 무작위 비연결 쌍

출력:
  - rgat_model.pt            — 학습된 모델 가중치
  - rgat_embeddings.npy      — 전체 노드 임베딩 행렬 (64차원)
  - rgat_predictions.csv     — 연결 없는 DTC의 상위 커넥터 예측
  - training_curve.png       — 학습/검증 손실 곡선
"""

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import RGATConv
from sklearn.metrics import roc_auc_score

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

BASE   = Path(__file__).parent
GRAPH_JSON = BASE / "dtc_knowledge_graph.json"
OUT_MODEL  = BASE / "rgat_model.pt"
OUT_EMBED  = BASE / "rgat_embeddings.npy"
OUT_PRED   = BASE / "rgat_predictions.csv"
OUT_CURVE  = BASE / "training_curve.png"

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Device: {DEVICE}")

# ══════════════════════════════════════════════════════════════
# 하이퍼파라미터
# ══════════════════════════════════════════════════════════════
EMBED_DIM    = 64     # 노드 임베딩 차원 (피처32 + 학습32)
HIDDEN_DIM   = 64     # RGAT hidden 차원
OUT_DIM      = 64     # 최종 임베딩 차원
HEADS        = 4      # attention heads (layer 1)
DROPOUT      = 0.3
LR           = 1e-3
WEIGHT_DECAY = 5e-4
EPOCHS       = 200
NEG_RATIO    = 3      # 양성 1개당 음성 샘플 수
TEST_RATIO   = 0.2
TOPK         = 10     # 예측 출력 top-K
FEAT_DIM     = 38     # DTC 코드 구조 피처 차원

# ══════════════════════════════════════════════════════════════
# 1. 그래프 JSON 로드 → 인덱스 매핑
# ══════════════════════════════════════════════════════════════
print("\n[1/6] Loading graph JSON...")
with open(GRAPH_JSON, "r", encoding="utf-8") as f:
    graph_data = json.load(f)

nodes = graph_data["nodes"]
edges = graph_data["edges"]

# 노드 ID → 정수 인덱스
node_id_to_idx: dict[str, int] = {n["id"]: i for i, n in enumerate(nodes)}
idx_to_node_id: dict[int, str] = {i: n["id"] for i, n in enumerate(nodes)}
N = len(nodes)

# 노드 타입 인덱스
node_type_map: dict[int, str] = {}
type_to_nodes: dict[str, list[int]] = {"DTC": [], "ECU": [], "Connector": []}
for i, n in enumerate(nodes):
    nt = n.get("node_type", "Unknown")
    node_type_map[i] = nt
    if nt in type_to_nodes:
        type_to_nodes[nt].append(i)

dtc_set  = set(type_to_nodes["DTC"])
conn_set = set(type_to_nodes["Connector"])

print(f"  Total nodes: {N}")
for t, ids in type_to_nodes.items():
    print(f"    {t:<12}: {len(ids)}")

# ══════════════════════════════════════════════════════════════
# DTC 코드 구조 피처 인코딩 (38차원)
#   노드타입(3) + 시스템(4) + 제조사전용(1) + 서브타입(14)
#   + 고장카테고리(10) + 커넥터위치(6) = 38
# ══════════════════════════════════════════════════════════════
SYSTEM_MAP   = {"P": 0, "B": 1, "C": 2, "U": 3}
TOP_SUBTYPES = ["00", "87", "11", "12", "88", "86", "01", "13",
                "8C", "96", "16", "82", "17"]
FAULT_MAP    = {"기타": 0, "통신": 1, "단락": 2, "전원/전압": 3, "센서": 4,
                 "단선/개방": 5, "범위/타당성": 6, "액추에이터": 7,
                 "온도": 8, "내부이상": 9}
LOC_MAP      = {"프론트": 0, "플로어": 1, "도어": 2, "리어": 3, "루프": 4}

def build_dtc_features(nodes: list) -> torch.Tensor:
    feat = np.zeros((len(nodes), FEAT_DIM), dtype=np.float32)
    for i, n in enumerate(nodes):
        nt = n.get("node_type", "")
        if nt == "DTC":
            feat[i, 0] = 1
        elif nt == "ECU":
            feat[i, 1] = 1
        elif nt == "Connector":
            feat[i, 2] = 1

        if nt == "DTC":
            code = n.get("code", "")
            sys_idx = SYSTEM_MAP.get(code[0] if code else "", -1)
            if sys_idx >= 0:
                feat[i, 3 + sys_idx] = 1
            try:
                if int(code[1], 16) != 0:
                    feat[i, 7] = 1
            except (ValueError, IndexError):
                pass
            st = code[-2:].upper() if len(code) >= 2 else ""
            st_idx = TOP_SUBTYPES.index(st) if st in TOP_SUBTYPES else len(TOP_SUBTYPES)
            feat[i, 8 + st_idx] = 1
            cat = n.get("fault_category", "기타")
            feat[i, 22 + FAULT_MAP.get(cat, 0)] = 1
        elif nt == "Connector":
            loc = n.get("location", "")
            feat[i, 32 + LOC_MAP.get(loc, 5)] = 1
    return torch.tensor(feat, dtype=torch.float32)

DTC_FEATURES = build_dtc_features(nodes)
print(f"  DTC structure features: {DTC_FEATURES.shape} (38-dim per node)")

# ══════════════════════════════════════════════════════════════
# 2. 엣지 분리: 배경 그래프 vs 학습 대상 (HW_MAP)
# ══════════════════════════════════════════════════════════════
print("\n[2/6] Building edge sets...")

# 관계 타입 정의 (5개: 2 base + 2 reverse + self-loop)
REL = {
    "SW_IN":         0,   # DTC→ECU  (논리 관계)
    "SW_IN_REV":     1,   # ECU→DTC
    "HW_WIRE":      2,   # ECU→Connector (물리 배선)
    "HW_WIRE_REV":  3,   # Connector→ECU
    "SELF_LOOP":    4,   # 노드 자기 자신 → 자신
}
NUM_RELS = 5

bg_src, bg_dst, bg_rel = [], [], []   # 배경 그래프 엣지
lp_pos_edges: list[tuple[int,int]] = []  # HW_MAP 양성 샘플

for e in edges:
    rel = e.get("rel", "")
    src = node_id_to_idx.get(e["source"])
    dst = node_id_to_idx.get(e["target"])
    if src is None or dst is None:
        continue

    if rel == "HW_MAP":
        lp_pos_edges.append((src, dst))
    elif rel in ("SW_IN", "HW_WIRE"):
        bg_src.append(src);  bg_dst.append(dst);  bg_rel.append(REL[rel])
        # 역방향 엣지 추가
        rev_key = rel + "_REV"
        bg_src.append(dst);  bg_dst.append(src);  bg_rel.append(REL[rev_key])

# self-loop 추가: GNN 컨볼루션은 in-edge로 들어오는 이웃 정보만 집계하므로,
# 이게 없으면 같은 이웃을 가진 노드들은 자기 피처가 달라도 출력이 완전히 동일해진다
# (예: 같은 ECU 소속 DTC끼리 서브타입이 달라도 임베딩이 코사인 1.0000으로 동일해지는 문제)
for i in range(N):
    bg_src.append(i); bg_dst.append(i); bg_rel.append(REL["SELF_LOOP"])

# 배경 그래프 텐서
bg_edge_index = torch.tensor([bg_src, bg_dst], dtype=torch.long)
bg_edge_type  = torch.tensor(bg_rel,           dtype=torch.long)

print(f"  Background edges: {bg_edge_index.size(1):,}")
print(f"  HW_MAP (positive): {len(lp_pos_edges)}")

# ══════════════════════════════════════════════════════════════
# 3. 학습/테스트 분리 + 음성 샘플링
# ══════════════════════════════════════════════════════════════
print("\n[3/6] Train/test split + negative sampling...")

random.shuffle(lp_pos_edges)
n_test  = int(len(lp_pos_edges) * TEST_RATIO)
n_train = len(lp_pos_edges) - n_test
pos_train = lp_pos_edges[:n_train]
pos_test  = lp_pos_edges[n_train:]

# 기존 연결 집합 (음성 샘플 필터링용)
pos_set = set(lp_pos_edges)
dtc_list  = list(dtc_set)
conn_list = list(conn_set)

def sample_negatives(n: int, exclude: set) -> list[tuple[int, int]]:
    negs = []
    seen = set(exclude)
    while len(negs) < n:
        d = random.choice(dtc_list)
        c = random.choice(conn_list)
        pair = (d, c)
        if pair not in seen:
            seen.add(pair)
            negs.append(pair)
    return negs

neg_train = sample_negatives(len(pos_train) * NEG_RATIO, pos_set)
neg_test  = sample_negatives(len(pos_test)  * NEG_RATIO, pos_set | set(neg_train))

def to_edge_label_tensor(pos, neg):
    edges = pos + neg
    labels = [1.0] * len(pos) + [0.0] * len(neg)
    src = torch.tensor([e[0] for e in edges], dtype=torch.long)
    dst = torch.tensor([e[1] for e in edges], dtype=torch.long)
    lbl = torch.tensor(labels, dtype=torch.float)
    return src, dst, lbl

tr_src, tr_dst, tr_lbl = to_edge_label_tensor(pos_train, neg_train)
te_src, te_dst, te_lbl = to_edge_label_tensor(pos_test,  neg_test)

print(f"  Train pos/neg: {len(pos_train)} / {len(neg_train)}")
print(f"  Test  pos/neg: {len(pos_test)}  / {len(neg_test)}")

# ══════════════════════════════════════════════════════════════
# 4. RGAT 모델 정의
# ══════════════════════════════════════════════════════════════
class RGAT(nn.Module):
    """
    2층 RGAT + 도트-프로덕트 링크 스코어러

    각 관계 타입(r)별로 독립적인 attention 행렬 W_r, a_r 학습:
      - r=0,1: 논리 관계 (SW_IN ↔)   ← DTC-ECU 소프트웨어 정의
      - r=2,3: 물리 배선 (HW_WIRE ↔) ← ECU-Connector 하네스

    입력 임베딩(embed_dim) = 학습형 임베딩(half) + DTC 코드 구조 피처 투영(half)
      - 같은 ECU에 속한 DTC끼리 이웃이 완전히 같아 임베딩이 동일해지는
        문제(예: C224077이 C163887을 그대로 복제)를 피처로 구분해 완화한다.
    """
    def __init__(self, num_nodes: int, embed_dim: int,
                 hidden_dim: int, out_dim: int,
                 num_rels: int, heads: int, dropout: float,
                 feat_dim: int):
        super().__init__()
        half = embed_dim // 2
        # 학습 가능한 노드 임베딩 (그래프 구조를 end-to-end 학습)
        self.node_emb  = nn.Embedding(num_nodes, half)
        # DTC 코드 구조 피처 → half 차원으로 투영
        self.feat_proj = nn.Linear(feat_dim, embed_dim - half)

        # Layer 1: embed_dim → hidden_dim × heads
        self.conv1 = RGATConv(
            in_channels=embed_dim,
            out_channels=hidden_dim,
            num_relations=num_rels,
            heads=heads,
            concat=True,
            dropout=dropout,
        )
        # Layer 2: (hidden_dim × heads) → out_dim
        self.conv2 = RGATConv(
            in_channels=hidden_dim * heads,
            out_channels=out_dim,
            num_relations=num_rels,
            heads=1,
            concat=False,
            dropout=dropout,
        )
        self.dropout = nn.Dropout(dropout)

        nn.init.xavier_uniform_(self.node_emb.weight)

    def encode(self, edge_index: torch.Tensor, edge_type: torch.Tensor,
               feats: torch.Tensor) -> torch.Tensor:
        x_emb  = self.node_emb.weight        # [N, half]        그래프 구조 학습
        x_feat = self.feat_proj(feats)       # [N, embed-half]  코드 구조 신호
        x = torch.cat([x_emb, x_feat], dim=-1)  # [N, embed_dim]
        x = self.dropout(x)
        x = self.conv1(x, edge_index, edge_type)   # [N, hidden×heads]
        x = F.elu(x)
        x = self.dropout(x)
        x = self.conv2(x, edge_index, edge_type)   # [N, out_dim]
        return x

    def decode(self, z: torch.Tensor,
               src: torch.Tensor, dst: torch.Tensor) -> torch.Tensor:
        # 도트 프로덕트 스코어
        return (z[src] * z[dst]).sum(dim=-1)

    def forward(self, edge_index, edge_type, feats, src, dst):
        z = self.encode(edge_index, edge_type, feats)
        return self.decode(z, src, dst), z


# ══════════════════════════════════════════════════════════════
# 5. 학습 루프
# ══════════════════════════════════════════════════════════════
print("\n[4/6] Training RGAT...")

model = RGAT(
    num_nodes=N,
    embed_dim=EMBED_DIM,
    hidden_dim=HIDDEN_DIM,
    out_dim=OUT_DIM,
    num_rels=NUM_RELS,
    heads=HEADS,
    dropout=DROPOUT,
    feat_dim=FEAT_DIM,
).to(DEVICE)

bg_edge_index = bg_edge_index.to(DEVICE)
bg_edge_type  = bg_edge_type.to(DEVICE)
DTC_FEATURES  = DTC_FEATURES.to(DEVICE)
tr_src = tr_src.to(DEVICE); tr_dst = tr_dst.to(DEVICE); tr_lbl = tr_lbl.to(DEVICE)
te_src = te_src.to(DEVICE); te_dst = te_dst.to(DEVICE); te_lbl = te_lbl.to(DEVICE)

optimizer = torch.optim.Adam(
    model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY
)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
criterion = nn.BCEWithLogitsLoss()

train_losses, val_aucs = [], []
best_auc, best_epoch = 0.0, 0

for epoch in range(1, EPOCHS + 1):
    # ── 학습 ──
    model.train()
    optimizer.zero_grad()
    logits, _ = model(bg_edge_index, bg_edge_type, DTC_FEATURES, tr_src, tr_dst)
    loss = criterion(logits, tr_lbl)
    loss.backward()
    nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
    optimizer.step()
    scheduler.step()
    train_losses.append(loss.item())

    # ── 검증 ──
    if epoch % 10 == 0 or epoch == EPOCHS:
        model.eval()
        with torch.no_grad():
            te_logits, _ = model(bg_edge_index, bg_edge_type, DTC_FEATURES, te_src, te_dst)
            te_probs = torch.sigmoid(te_logits).cpu().numpy()
            te_true  = te_lbl.cpu().numpy()
        auc = roc_auc_score(te_true, te_probs)
        val_aucs.append((epoch, auc))

        if auc > best_auc:
            best_auc, best_epoch = auc, epoch
            torch.save(model.state_dict(), OUT_MODEL)

        print(f"  Epoch {epoch:>4}  loss={loss.item():.4f}  AUC={auc:.4f}"
              + (" <-- best" if auc == best_auc else ""))

print(f"\n  Best AUC: {best_auc:.4f} @ epoch {best_epoch}")

# ══════════════════════════════════════════════════════════════
# 6. 추가 평가: Hits@K
# ══════════════════════════════════════════════════════════════
print("\n[5/6] Evaluating Hits@K...")
model.load_state_dict(torch.load(OUT_MODEL, map_location=DEVICE, weights_only=True))
model.eval()
with torch.no_grad():
    _, z = model(bg_edge_index, bg_edge_type, DTC_FEATURES, te_src, te_dst)

z_np = z.cpu().numpy()   # [N, out_dim]
z_conn_eval = z_np[conn_list]  # [|Conn|, out_dim] 루프 밖에서 1회만 슬라이싱
conn_to_local_idx = {c: i for i, c in enumerate(conn_list)}

def hits_at_k(k: int) -> float:
    hits = 0
    for (dtc_idx, conn_idx) in pos_test:
        z_dtc  = z_np[dtc_idx]
        scores = z_conn_eval @ z_dtc
        top_k  = np.argsort(scores)[::-1][:k]
        true_conn_local = conn_to_local_idx.get(conn_idx, -1)
        if true_conn_local in top_k:
            hits += 1
    return hits / len(pos_test) if pos_test else 0.0

for k in [1, 5, 10, 20, 50]:
    h = hits_at_k(k)
    print(f"  Hits@{k:<3}: {h:.4f}  ({h*100:.1f}%)")

# ══════════════════════════════════════════════════════════════
# 7. 커넥터 없는 DTC에 대한 Top-K 커넥터 예측
# ══════════════════════════════════════════════════════════════
print(f"\n[6/6] Predicting top-{TOPK} connectors for unlinked DTCs...")

# DTC → 알려진 커넥터 연결 맵
known_dtc_conn: dict[int, set] = {}
for (d, c) in lp_pos_edges:
    known_dtc_conn.setdefault(d, set()).add(c)

# 커넥터 인덱스 → 이름 맵
conn_name_map = {i: nodes[i].get("name", nodes[i]["id"]) for i in conn_list}
dtc_code_map  = {i: nodes[i].get("code", nodes[i]["id"]) for i in dtc_set}

z_conn_all = z_np[conn_list]   # [|Conn|, out_dim]

rows = []
unlinked_dtcs = [i for i in dtc_set if i not in known_dtc_conn]
print(f"  Unlinked DTC count: {len(unlinked_dtcs)}")

for dtc_idx in unlinked_dtcs[:200]:   # 상위 200개 DTC만 출력
    z_dtc  = z_np[dtc_idx]
    scores = z_conn_all @ z_dtc
    top_k_local = np.argsort(scores)[::-1][:TOPK]
    for rank, local_idx in enumerate(top_k_local, 1):
        conn_idx = conn_list[local_idx]
        rows.append({
            "dtc_node_idx":    dtc_idx,
            "dtc_code":        dtc_code_map.get(dtc_idx, ""),
            "rank":            rank,
            "connector_idx":   conn_idx,
            "connector_name":  conn_name_map.get(conn_idx, ""),
            "score":           float(scores[local_idx]),
        })

pred_df = pd.DataFrame(rows)
pred_df.to_csv(OUT_PRED, index=False, encoding="utf-8-sig")
print(f"  Saved -> {OUT_PRED.name}  ({len(pred_df)} rows)")

# ══════════════════════════════════════════════════════════════
# 8. 학습 곡선 시각화
# ══════════════════════════════════════════════════════════════
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("RGAT Link Prediction — Training Results", fontweight="bold")

ax1.plot(train_losses, color="#3498DB", linewidth=1.2)
ax1.set_xlabel("Epoch")
ax1.set_ylabel("BCE Loss")
ax1.set_title("Training Loss")
ax1.grid(alpha=0.3)

epochs_val = [ep for ep, _ in val_aucs]
aucs_val   = [auc for _, auc in val_aucs]
ax2.plot(epochs_val, aucs_val, color="#E74C3C", marker="o",
         markersize=4, linewidth=1.5)
ax2.axhline(best_auc, linestyle="--", color="gray", alpha=0.7,
            label=f"Best AUC = {best_auc:.4f} (ep {best_epoch})")
ax2.set_xlabel("Epoch")
ax2.set_ylabel("AUC-ROC")
ax2.set_title("Test AUC-ROC")
ax2.legend()
ax2.grid(alpha=0.3)
ax2.set_ylim(0.4, 1.05)

plt.tight_layout()
plt.savefig(str(OUT_CURVE), dpi=120, bbox_inches="tight")
plt.close()
print(f"  Saved -> {OUT_CURVE.name}")

# 노드 임베딩 저장
np.save(str(OUT_EMBED), z_np)
print(f"  Embeddings saved -> {OUT_EMBED.name}  shape={z_np.shape}")

print("\n" + "=" * 60)
print(f" RGAT training complete")
print(f"   Best AUC-ROC : {best_auc:.4f}")
print(f"   Embedding dim: {OUT_DIM}")
print(f"   Num relations: {NUM_RELS}")
print(f"   Device used  : {DEVICE}")
print("=" * 60)
