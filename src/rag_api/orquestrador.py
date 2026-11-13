"""Orquestrador do fluxo de pergunta do assistente RAG.

Integra, nesta ordem: guardrails de entrada -> embedding da pergunta -> busca no
banco vetorial (com permissões) -> verificação de confiança -> geração via LLM ->
auditoria. É o componente cuja integração os testes exercitam de ponta a ponta.
"""

from __future__ import annotations

from dataclasses import dataclass

from .componentes import (
    Auditoria,
    BancoVetorial,
    EmbedderFake,
    Guardrails,
    LLMFake,
    RegistroAuditoria,
)
from .config import ler_limiar_confianca


@dataclass
class Resposta:
    status: str           # "ok" | "sem_contexto" | "bloqueado"
    resposta: str
    fontes: list[str]


class Orquestrador:
    def __init__(
        self,
        embedder: EmbedderFake,
        banco: BancoVetorial,
        llm: LLMFake,
        guardrails: Guardrails,
        auditoria: Auditoria,
    ) -> None:
        self._embedder = embedder
        self._banco = banco
        self._llm = llm
        self._guardrails = guardrails
        self._auditoria = auditoria

    def responder(self, pergunta: str, permissoes: set[str]) -> Resposta:
        ok, motivo = self._guardrails.validar_entrada(pergunta)
        if not ok:
            self._auditoria.registrar(RegistroAuditoria(pergunta, "bloqueado"))
            return Resposta("bloqueado", f"Não posso responder: {motivo}.", [])

        consulta = self._embedder.gerar(pergunta)
        recuperados = self._banco.buscar(consulta, permissoes)

        limiar = ler_limiar_confianca()
        if not recuperados or recuperados[0][1] < limiar:
            self._auditoria.registrar(RegistroAuditoria(pergunta, "sem_contexto"))
            return Resposta(
                "sem_contexto",
                "Não encontrei isso na base. Pode reformular a pergunta?",
                [],
            )

        trechos = [doc.texto for doc, _ in recuperados]
        fontes = [doc.id for doc, _ in recuperados]
        resposta = self._llm.gerar(pergunta, trechos)
        self._auditoria.registrar(RegistroAuditoria(pergunta, "ok", fontes))
        return Resposta("ok", resposta, fontes)
