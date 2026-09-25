# DTC_RGAT: 차량 전장 DTC-하네스 지능형 고장 진단 플랫폼 🚗⚡

> **Relational Graph Attention Network (RGAT) 기반 고장 진단 코드(DTC) ➔ 물리 배선 하네스 커넥터(Connector) 근본 원인 추론 시스템**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org)
[![PyG](https://img.shields.io/badge/PyG-TorchGeometric-3C2179)](https://pyg.org)
[![Flask](https://img.shields.io/badge/Flask-Webapp-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![Waitress](https://img.shields.io/badge/WSGI-Waitress-blue)](https://docs.pylonsproject.org/projects/waitress)

---

## 📌 프로젝트 개요

차량 전장 제어기(ECU)에서 감지되는 **DTC(Diagnostic Trouble Code)**는 소프트웨어적 현상만을 알려줄 뿐, 실제 차체 내부의 **어떤 배선 커넥터(Connector)가 접촉 불량, 단선, 단락의 근본 원인인지**는 지침서상에 약 13.5%만 매핑되어 있습니다.

본 프로젝트는 **이종 지식 그래프(Heterogeneous Knowledge Graph)**와 **관계형 그래프 어텐션 신경망(RGAT)**을 활용하여:
1. 미연결된 DTC ➔ 커넥터 링크(86.5%)를 **AUC-ROC 0.9743**의 높은 정확도로 추론합니다.
2. 다발 고장 발생 시 공통 원인 커넥터를 실시간으로 도출하는 **Apple Human Interface 스타일 웹 대시보드**를 제공합니다.
3. 1,290개 전체 DTC의 서브타입 명칭을 **ISO 14229-1 (UDS FTB)** 국제 표준에 맞추어 100% 결측치 없이 정제했습니다.

---

## 🏗️ 시스템 아키텍처

```
[차량 진단 지식 그래프]
  ├── DTC (1,290개) ──(SW_IN: 논리 고장 감지)──▶ ECU (40개)
  ├── ECU (40개) ──(HW_WIRE: 물리 배선)──▶ Connector (375개)
  └── DTC ──(HW_MAP: 기존 검증 직결 매핑)──▶ Connector (양성 학습 타깃)
              │
              ▼
    [RGAT 링크 예측 모델 (train_rgat.py)]
     - 38차원 DTC 구조 도메인 피처 (SAE J2019 규격)
     - 2-Layer RGATConv (4-Heads, Self-Loop 기반 임베딩 붕괴 방지)
     - Best AUC-ROC : 0.9743 / Hits@50 : 77.5%
              │
              ▼
    [하이브리드 진단 엔진 & 웹앱 (webapp.py)]
     - 1순위: 마스터 직결 검증 커넥터 (Score 2.0 고정 노출)
     - 2순위: Final Score = 0.7 * 구조 점수(2-Hop 배선) + 0.3 * RGAT 점수
     - vis.js 기반 좌➔우 3계층(DTC -> ECU -> Connector) 인터랙티브 시각화
```

---

## 📂 파일 구성

| 파일명 | 역할 및 설명 |
| :--- | :--- |
| `config.py` | 시스템 전역 경로, 하이퍼파라미터(Alpha/Beta), 서버 설정 모듈 |
| `graph_service.py` | 지식 그래프 관리, $O(1)$ 색인 및 RGAT 랭킹 추론 순수 도메인 엔진 (SRP 준수) |
| `webapp.py` | Flask 기반 진단 대시보드, 에러 로깅, 팝업 모달 UI, Waitress WSGI 서버 |
| `train_rgat.py` | PyTorch Geometric 기반 RGAT 링크 예측 딥러닝 학습 및 평가 파이프라인 |
| `dtc_knowledge_graph.json` | 노드 1,705개, 엣지 1,872개의 차량 전장 원천 지식 그래프 (서브타입 100% 완비) |
| `dtc_knowledge_graph_updated.xlsx` | 5개 다중 시트로 구성된 종합 엑셀 보고서 (마스터 매핑, ECU, 커넥터 현황) |
| `dtc_guide_for_student.html` | 중학생도 쉽게 이해할 수 있는 비유와 그림 중심의 쉬운 웹 가이드 |
| `rgat_model.pt` | 학습 완료된 최고 성능(AUC 0.9743) RGAT 모델 가중치 |
| `rgat_embeddings.npy` | 1,705개 전체 노드의 64차원 학습 잠재 임베딩 행렬 |
| `rgat_predictions.csv` | 미연결 DTC 1,116개 대상 상위 10개 추천 커넥터 예측표 |
| `training_curve.png` | 에포크별 Loss 감소 및 AUC 검증 곡선 시각화 그래프 |

---

## 🚀 빠른 시작 가이드 (Quick Start)

### 1. 환경 설정 및 패키지 설치
```powershell
pip install torch torch_geometric flask waitress pandas openpyxl matplotlib scikit-learn
```

### 2. 진단 웹 대시보드 실행
```powershell
# 개발 서버 모드 (자동 브라우저 오픈)
python webapp.py

# 프로덕션 멀티스레드 WSGI 모드 (권장, 8 스레드)
python webapp.py --prod
```
- 브라우저 접속: **`http://localhost:5000`**

### 3. RGAT 모델 재학습 (신규 데이터 반영 시)
```powershell
python train_rgat.py
```

### 4. 엑셀 종합 보고서 생성
```powershell
python convert_to_excel.py
```

---

## 📊 ISO 14229-1 국제 표준 서브타입 정제 내역

전체 1,290개 DTC 중 기존에 비어있거나 모호했던 **453개 결측 서브타입을 100% 공식 표준 명칭으로 정제** 완료했습니다.
- `00` (241건): `세부 유형 없음 (기본 고장)` (No Sub-type Information)
- `14` (13건): `회로 그라운드 쇼트 또는 단선` (Circuit Short to Ground or Open)
- `56` (11건): `잘못된/호환되지 않은 사양 입력됨` (Invalid/Incompatible Software)
- `98` (9건): `시스템 및 부품 과열` (Component Over Temperature)
- `72 / 73` (8건): `액추에이터 열린/닫힌 상태로 고착` (Actuator Stuck Open/Closed)
- `02` (15건): `일반 신호 오류` (General Signal Failure)

---

## 📜 라이선스
MIT License
