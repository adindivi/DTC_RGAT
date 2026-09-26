# -*- coding: utf-8 -*-
"""
DTC 지식 그래프 진단 시스템 전역 설정 및 하이퍼파라미터
- 파일 경로, 비즈니스 가중치, 서버 옵션 분리 (SRP 준수)
"""
import os
from pathlib import Path

# 기본 디렉토리
BASE_DIR = Path(__file__).parent.resolve()

# 데이터 및 모델 파일 경로
GRAPH_JSON_PATH = BASE_DIR / "dtc_knowledge_graph.json"
EMBED_NPY_PATH  = BASE_DIR / "rgat_embeddings.npy"
MODEL_PT_PATH   = BASE_DIR / "rgat_model.pt"
PRED_CSV_PATH   = BASE_DIR / "rgat_predictions.csv"
CURVE_PNG_PATH  = BASE_DIR / "training_curve.png"
LOG_FILE_PATH   = BASE_DIR / "webapp.log"
LATENT_JSON_PATH = BASE_DIR / "rgat_latent_2d.json"
REPORT_HTML_PATH = BASE_DIR / "최종정리.html"
TEMPLATES_DIR    = BASE_DIR / "templates"

# 진단 랭킹 및 보안 하이퍼파라미터
DEFAULT_ALPHA: float = 0.7  # 구조 점수(2-Hop 배선 도달 비율) 가중치
DEFAULT_BETA: float  = 0.3  # RGAT 임베딩 유사도 가중치
DEFAULT_TOP_K: int   = 20   # 상위 추천 커넥터 개수
EMBED_DIM: int       = 64   # 임베딩 벡터 차원
USE_TOPOLOGY_MASK: bool = True  # 2-Hop 배선 도달 제약 마스킹 활성화 여부
MAX_DTC_CODES_LIMIT: int = 50   # 1회 최대 분석 가능 DTC 코드 개수 (DoS 방어)

# 서버 기본 설정
DEFAULT_HOST: str = "0.0.0.0"
DEFAULT_PORT: int = 5000
IS_PRODUCTION: bool = os.environ.get("FLASK_ENV") == "production"
