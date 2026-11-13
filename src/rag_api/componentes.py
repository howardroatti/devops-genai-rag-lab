"""Componentes internos do assistente RAG (integrados pelo orquestrador).

Dados fictícios. As fronteiras externas (embeddings e LLM) são representadas por
implementações determinísticas (fakes), para que os testes de integração sejam
reprodutíveis e não dependam de rede. Os componentes internos (guardrails, banco
vetorial em memória e auditoria) são reais.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

LIMIAR_CONFIANCA = 0.10  # score mínimo de similaridade para responder
TAMANHO_MAXIMO_PERGUNTA = 2000
TERMOS_DE_INJECAO = ("ignore as instruções", "ignore previous", "desconsidere o sistema")


STOPWORDS = {
    "a", "o", "e", "de", "do", "da", "das", "dos", "em", "no", "na", "nos", "nas",
    "um", "uma", "para", "por", "com", "que", "ao", "aos", "os", "as", "se", "ou",
}


def tokenizar(texto: str) -> Counter:
    """Quebra o texto em tokens de conteúdo (bag-of-words) para similaridade.

    Remove stopwords e tokens de 1 caractere para que a recuperação seja guiada
    por palavras de conteúdo, e não por palavras funcionais comuns a quase todo texto.
    """
    tokens = re.findall(r"[a-zá-ú0-9]+", texto.lower())
    return Counter(t for t in tokens if len(t) > 1 and t not in STOPWORDS)


def similaridade_cosseno(a: Counter, b: Counter) -> float:
    """Similaridade do cosseno entre dois vetores de contagem de tokens."""
    if not a or not b:
        return 0.0
    comuns = set(a) & set(b)
    produto = sum(a[t] * b[t] for t in comuns)
    norma = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return produto / norma if norma else 0.0


# --- Fronteiras externas (fakes determinísticos) --------------------------------

class EmbedderFake:
    """Gera o "embedding" como o vetor de tokens do texto (determinístico)."""

    def gerar(self, texto: str) -> Counter:
        return tokenizar(texto)


class LLMFake:
    """Compõe a resposta ancorada apenas nos trechos recuperados (sem alucinar)."""

    def gerar(self, pergunta: str, trechos: list[str]) -> str:
        base = " ".join(trechos)
        return f"Com base nos documentos: {base}"


# --- Componentes internos (reais) -----------------------------------------------

@dataclass
class Documento:
    id: str
    texto: str
    permissao: str = "publico"  # "publico" ou um rótulo de permissão exigido


class BancoVetorial:
    """Armazena documentos e recupera por similaridade, respeitando permissões."""

    def __init__(self, embedder: EmbedderFake) -> None:
        self._embedder = embedder
        self._documentos: list[tuple[Documento, Counter]] = []

    def indexar(self, documento: Documento) -> None:
        self._documentos.append((documento, self._embedder.gerar(documento.texto)))

    def buscar(self, consulta: Counter, permissoes: set[str], k: int = 3) -> list[tuple[Documento, float]]:
        visiveis = [
            (doc, vec) for doc, vec in self._documentos
            if doc.permissao == "publico" or doc.permissao in permissoes
        ]
        pontuados = [(doc, similaridade_cosseno(consulta, vec)) for doc, vec in visiveis]
        pontuados.sort(key=lambda par: par[1], reverse=True)
        return pontuados[:k]


class Guardrails:
    """Valida entrada e saída do fluxo de pergunta."""

    def validar_entrada(self, pergunta: str) -> tuple[bool, str]:
        if len(pergunta) > TAMANHO_MAXIMO_PERGUNTA:
            return False, "pergunta excede o tamanho máximo permitido"
        minuscula = pergunta.lower()
        if any(termo in minuscula for termo in TERMOS_DE_INJECAO):
            return False, "entrada suspeita de injeção de prompt"
        return True, ""


@dataclass
class RegistroAuditoria:
    pergunta: str
    status: str
    fontes: list[str] = field(default_factory=list)


class Auditoria:
    """Registra cada interação para rastreabilidade (em memória)."""

    def __init__(self) -> None:
        self.registros: list[RegistroAuditoria] = []

    def registrar(self, registro: RegistroAuditoria) -> None:
        self.registros.append(registro)
