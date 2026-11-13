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
