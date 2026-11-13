"""Casos de teste gerados pelo PROMPT C (contrato de API / schema + dados).

Validam o contrato da resposta (campos, tipos, valores de status permitidos) e a
exposição da especificação OpenAPI, de forma independente do conteúdo textual.
"""

STATUS_PERMITIDOS = {"ok", "sem_contexto", "bloqueado"}


def test_resposta_respeita_o_contrato_de_schema(client):
    resposta = client.post(
        "/perguntar",
        json={"pergunta": "Quantos dias de férias eu tenho?", "permissoes": []},
    )
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("application/json")
    corpo = resposta.json()
    # contrato: exatamente estes campos, com estes tipos
    assert set(corpo.keys()) == {"status", "resposta", "fontes"}
    assert corpo["status"] in STATUS_PERMITIDOS
    assert isinstance(corpo["resposta"], str) and corpo["resposta"]
    assert isinstance(corpo["fontes"], list)
    assert all(isinstance(fonte, str) for fonte in corpo["fontes"])


def test_sem_contexto_mantem_o_mesmo_contrato_com_fontes_vazias(client):
    resposta = client.post(
        "/perguntar",
        json={"pergunta": "Explique fotossíntese das plantas aquáticas.", "permissoes": []},
    )
    corpo = resposta.json()
    assert set(corpo.keys()) == {"status", "resposta", "fontes"}
    assert corpo["status"] == "sem_contexto"
    assert corpo["fontes"] == []


def test_openapi_expoe_o_endpoint_perguntar(client):
    esquema = client.get("/openapi.json").json()
    assert "/perguntar" in esquema["paths"]
    assert "post" in esquema["paths"]["/perguntar"]
