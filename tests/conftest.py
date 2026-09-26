# -*- coding: utf-8 -*-
"""
Pytest 글로벌 픽스처 (Fixture) 정의
- KnowledgeGraphService 싱글톤 인스턴스 공유 (Cold Start 지연 방지)
- Flask Test Client 생성
"""
import pytest
import config
from graph_service import KnowledgeGraphService
from webapp import app


@pytest.fixture(scope="session")
def service() -> KnowledgeGraphService:
    """테스트 세션 전체에서 공유하는 KnowledgeGraphService 인스턴스"""
    return KnowledgeGraphService(
        graph_path=config.GRAPH_JSON_PATH,
        embed_path=config.EMBED_NPY_PATH,
        alpha=config.DEFAULT_ALPHA,
        beta=config.DEFAULT_BETA,
        top_k=config.DEFAULT_TOP_K,
    )


@pytest.fixture(scope="session")
def client():
    """Flask 테스트 클라이언트 픽스처"""
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client
