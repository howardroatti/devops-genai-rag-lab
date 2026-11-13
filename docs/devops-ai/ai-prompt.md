Você é um engenheiro de DevOps sênior atuando como primeiro analista de falhas de CI. Analise o log de erro e o código citado. Responda em português técnico, em seções fixas: RESUMO, EVIDÊNCIAS, CAUSA-RAIZ (arquivo:linha), CORREÇÃO (em formato de código), RISCOS DE SEGURANÇA, COMO VALIDAR e CONFIANÇA/PREMISSAS. Separe causa de sintoma. Não invente linhas de código que não estejam no contexto; se faltar contexto, diga o que falta. Você apenas sugere: não aplica correções.

## Log de falha do CI
```
$ INJECT_BUG=1 python -m pytest -q
(caminhos de usuário anonimizados como <HOME>; segredos mascarados)

============================= test session starts =============================
platform linux -- Python 3.12, pytest-9.1.1
rootdir: <HOME>/devops-genai-rag-lab
collected 13 items

tests/test_casos_erro.py ......                                          [ 46%]
tests/test_cenarios_integracao.py F..F                                   [ 76%]
tests/test_contrato_api.py FF.                                           [100%]

================================== FAILURES ===================================
____________ test_fluxo_completo_retorna_resposta_ancorada_com_fontes ____________

src/rag_api/api.py:69: in perguntar
    resultado = orquestrador.responder(pedido.pergunta, set(pedido.permissoes))

self = <rag_api.orquestrador.Orquestrador object at 0x...>
pergunta = 'Quantos dias de férias eu tenho?', permissoes = set()

    def responder(self, pergunta: str, permissoes: set[str]) -> Resposta:
        ok, motivo = self._guardrails.validar_entrada(pergunta)
        if not ok:
            self._auditoria.registrar(RegistroAuditoria(pergunta, "bloqueado"))
            return Resposta("bloqueado", f"Não posso responder: {motivo}.", [])

        consulta = self._embedder.gerar(pergunta)
        recuperados = self._banco.buscar(consulta, permissoes)

        limiar = ler_limiar_confianca()
>       if not recuperados or recuperados[0][1] < limiar:
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^
E       TypeError: '<' not supported between instances of 'float' and 'str'

src/rag_api/orquestrador.py:55: TypeError
=========================== short test summary info ===========================
FAILED tests/test_cenarios_integracao.py::test_fluxo_completo_retorna_resposta_ancorada_com_fontes
FAILED tests/test_cenarios_integracao.py::test_pergunta_sobre_reembolso_recupera_documento_de_reembolso
FAILED tests/test_cenarios_integracao.py::test_usuario_com_permissao_rh_acessa_documento_restrito
FAILED tests/test_casos_erro.py::test_sem_contexto_relevante_retorna_fallback_sem_alucinar
FAILED tests/test_casos_erro.py::test_documento_restrito_nao_vaza_para_usuario_sem_permissao
FAILED tests/test_contrato_api.py::test_resposta_respeita_o_contrato_de_schema
FAILED tests/test_contrato_api.py::test_sem_contexto_mantem_o_mesmo_contrato_com_fontes_vazias
7 failed, 6 passed in 6.70s

```

## Código: src/rag_api/api.py
```python
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

```

## Código: src/rag_api/componentes.py
```python
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

```

## Código: src/rag_api/orquestrador.py
```python
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

```

## Código: src/rag_api/orquestrador.py
```python
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

```

## Código: src/rag_api/config.py
```python
"""Leitura de configuração do assistente RAG a partir de variáveis de ambiente.

O limiar de confiança (score mínimo de similaridade para responder) é lido aqui,
na fronteira do sistema.

------------------------------------------------------------------------------
FALHA INTENCIONAL CONTROLADA (miniprojeto de DevOps)
------------------------------------------------------------------------------
Quando a variável de ambiente ``INJECT_BUG=1`` está ativa, esta função devolve o
valor do limiar como *string*, sem converter para ``float``. É uma alteração
sintaticamente correta, mas semanticamente errada: o orquestrador passa a comparar
``float < str``, o que gera ``TypeError`` em tempo de execução.

O defeito é injetado SOMENTE pela variável de ambiente (usada no job de CI), então
o código do repositório continua correto por padrão e os testes passam localmente
sem a flag. A graça do exercício é que o erro estoura em ``orquestrador.py`` (onde a
comparação acontece), mas a causa-raiz está AQUI, em ``config.py`` (que nem aparece
no traceback).
"""

from __future__ import annotations

import os

LIMIAR_PADRAO = "0.10"


def ler_limiar_confianca() -> float:
    """Lê o limiar de confiança do ambiente (padrão 0.10)."""
    bruto = os.getenv("RAG_LIMIAR", LIMIAR_PADRAO)
    if os.getenv("INJECT_BUG") == "1":
        # BUG intencional: esquece a conversão para float -> devolve str.
        return bruto  # type: ignore[return-value]
    return float(bruto)

```