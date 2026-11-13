"""Camada REST (FastAPI) do assistente RAG.

Expõe os endpoints usados nos testes de integração:
- POST /ingerir   -> indexa documentos fictícios no banco vetorial;
- POST /perguntar -> executa o fluxo RAG de ponta a ponta;
- GET  /saude     -> verificação simples de disponibilidade.

`criar_app` permite injetar componentes (fakes/reais), facilitando os testes.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .componentes import Auditoria, BancoVetorial, Documento, EmbedderFake, Guardrails, LLMFake
from .orquestrador import Orquestrador


class DocumentoEntrada(BaseModel):
    id: str = Field(min_length=1)
    texto: str = Field(min_length=1)
    permissao: str = "publico"


class PedidoIngestao(BaseModel):
    documentos: list[DocumentoEntrada] = Field(min_length=1)


class PedidoPergunta(BaseModel):
    pergunta: str = Field(min_length=1, max_length=2000)
    permissoes: list[str] = Field(default_factory=list)


class RespostaPergunta(BaseModel):
    status: str
    resposta: str
    fontes: list[str]


def criar_app(
    embedder: EmbedderFake | None = None,
    llm: LLMFake | None = None,
) -> FastAPI:
    embedder = embedder or EmbedderFake()
    banco = BancoVetorial(embedder)
    orquestrador = Orquestrador(
        embedder=embedder,
        banco=banco,
        llm=llm or LLMFake(),
        guardrails=Guardrails(),
        auditoria=Auditoria(),
    )

    app = FastAPI(title="Assistente RAG", version="1.0.0")

    @app.get("/saude")
    def saude() -> dict:
        return {"status": "ok"}

    @app.post("/ingerir")
    def ingerir(pedido: PedidoIngestao) -> dict:
        for doc in pedido.documentos:
            banco.indexar(Documento(id=doc.id, texto=doc.texto, permissao=doc.permissao))
        return {"indexados": len(pedido.documentos)}

    @app.post("/perguntar", response_model=RespostaPergunta)
    def perguntar(pedido: PedidoPergunta) -> RespostaPergunta:
        resultado = orquestrador.responder(pedido.pergunta, set(pedido.permissoes))
        return RespostaPergunta(
            status=resultado.status,
            resposta=resultado.resposta,
            fontes=resultado.fontes,
        )

    return app
