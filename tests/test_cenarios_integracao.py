"""Casos de teste gerados pelo PROMPT A (cenários de integração / happy path).

Exercitam a comunicação entre as camadas do fluxo RAG de ponta a ponta
(API -> guardrails -> embedding -> banco vetorial -> LLM -> auditoria), via HTTP.
Estrutura AAA (Arrange, Act, Assert).
"""


def test_saude_responde_ok(client):
    # Act
    resposta = client.get("/saude")
    # Assert
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_fluxo_completo_retorna_resposta_ancorada_com_fontes(client):
    # Arrange
    pedido = {"pergunta": "Quantos dias de férias eu tenho?", "permissoes": []}
    # Act
    resposta = client.post("/perguntar", json=pedido)
    # Assert
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert "doc-ferias" in corpo["fontes"]           # recuperou o documento certo
    assert "30 dias" in corpo["resposta"]            # resposta ancorada no trecho


def test_pergunta_sobre_reembolso_recupera_documento_de_reembolso(client):
    resposta = client.post(
        "/perguntar",
        json={"pergunta": "Como funciona o reembolso de despesas?", "permissoes": []},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert "doc-reembolso" in corpo["fontes"]
    assert "nota fiscal" in corpo["resposta"]


def test_usuario_com_permissao_rh_acessa_documento_restrito(client):
    # Integração do filtro de permissão na recuperação.
    resposta = client.post(
        "/perguntar",
        json={"pergunta": "Qual a tabela de salários por cargo?", "permissoes": ["rh"]},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert "doc-salarios" in corpo["fontes"]
