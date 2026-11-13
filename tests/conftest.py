"""Fixtures compartilhadas dos testes de integração.

A fixture `client` sobe a API com os componentes reais (fakes só nas fronteiras
externas) e já executa a ingestão dos documentos fictícios como pré-condição de
integração, de modo que cada teste exercite o fluxo de ponta a ponta.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rag_api.api import criar_app  # noqa: E402

# Documentos fictícios usados como base de conhecimento nos testes.
DOCUMENTOS_FIXTURE = [
    {
        "id": "doc-ferias",
        "texto": "A política de férias permite 30 dias após 12 meses de trabalho.",
        "permissao": "publico",
    },
    {
        "id": "doc-reembolso",
        "texto": "O reembolso de despesas exige nota fiscal e aprovação do gestor.",
        "permissao": "publico",
    },
    {
        "id": "doc-salarios",
        "texto": "A tabela de salários por cargo é confidencial e restrita ao RH.",
        "permissao": "rh",
    },
]


@pytest.fixture
def client():
    cliente = TestClient(criar_app())
    resposta = cliente.post("/ingerir", json={"documentos": DOCUMENTOS_FIXTURE})
    assert resposta.status_code == 200
    assert resposta.json()["indexados"] == len(DOCUMENTOS_FIXTURE)
    return cliente
