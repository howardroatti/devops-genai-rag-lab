#!/usr/bin/env python3
"""Agente de diagnóstico de falhas de CI com IA generativa.

Segue o mecanismo descrito na Unidade 5 (Seção 5.2.2):
1. Coleta de contexto: lê o log do job que falhou e o código citado no traceback.
2. Engenharia de prompt: monta um prompt estruturado (causa-raiz em português
   técnico, correção em formato de código e riscos de segurança).
3. Feedback: imprime a análise para ser publicada no Merge Request / resumo do job.

Segurança: antes de enviar qualquer coisa ao modelo, o agente ANONIMIZA caminhos de
usuário e MASCARA tokens/chaves. Sem credencial de API configurada, ele não falha o
pipeline: grava o prompt completo como artefato e explica o motivo. O agente nunca
altera código nem muda o status do pipeline (a decisão continua humana).

Uso:
    python scripts/ai_diagnose.py --log docs/devops-ai/pytest-failure.log \\
        --out-prompt docs/devops-ai/ai-prompt.md
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

# Padrões de segredo a mascarar antes de enviar ao modelo.
PADROES_SEGREDO = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"glpat-[A-Za-z0-9_-]{8,}"),
]

PROMPT_SISTEMA = (
    "Você é um engenheiro de DevOps sênior atuando como primeiro analista de falhas "
    "de CI. Analise o log de erro e o código citado. Responda em português técnico, "
    "em seções fixas: RESUMO, EVIDÊNCIAS, CAUSA-RAIZ (arquivo:linha), CORREÇÃO "
    "(em formato de código), RISCOS DE SEGURANÇA, COMO VALIDAR e CONFIANÇA/PREMISSAS. "
    "Separe causa de sintoma. Não invente linhas de código que não estejam no contexto; "
    "se faltar contexto, diga o que falta. Você apenas sugere: não aplica correções."
)


def mascarar_segredos(texto: str) -> str:
    """Anonimiza caminhos de usuário e mascara credenciais."""
    texto = re.sub(r"(/home/[^/\s]+|/c/Users/[^/\s]+|C:\\Users\\[^\\\s]+)", "<HOME>", texto)
    for padrao in PADROES_SEGREDO:
        texto = padrao.sub("<REDACTED>", texto)
    return texto


def arquivos_do_traceback(log: str, raiz: Path) -> list[Path]:
    """Extrai os arquivos do projeto citados no traceback e seus módulos importados."""
    citados = set(re.findall(r"(src/[\w/]+\.py)", log))
    encontrados: list[Path] = []
    for rel in sorted(citados):
        caminho = raiz / rel
        if caminho.exists():
            encontrados.append(caminho)
            # inclui também os módulos importados pelo arquivo citado,
            # porque a causa-raiz pode não aparecer no traceback.
            fonte = caminho.read_text(encoding="utf-8")
            for imp in re.findall(r"from \.(\w+) import|import \.(\w+)", fonte):
                nome = imp[0] or imp[1]
                vizinho = caminho.parent / f"{nome}.py"
                if vizinho.exists() and vizinho not in encontrados:
                    encontrados.append(vizinho)
    return encontrados


def montar_prompt(log: str, arquivos: list[Path], raiz: Path) -> str:
    partes = [PROMPT_SISTEMA, "\n## Log de falha do CI\n```\n" + mascarar_segredos(log) + "\n```"]
    for caminho in arquivos:
        rel = caminho.relative_to(raiz).as_posix()
        conteudo = mascarar_segredos(caminho.read_text(encoding="utf-8"))
        partes.append(f"\n## Código: {rel}\n```python\n{conteudo}\n```")
    return "\n".join(partes)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True)
    parser.add_argument("--out-prompt", default="docs/devops-ai/ai-prompt.md")
    args = parser.parse_args()

    raiz = Path(__file__).resolve().parents[1]
    log = Path(args.log).read_text(encoding="utf-8")
    arquivos = arquivos_do_traceback(log, raiz)
    prompt = montar_prompt(log, arquivos, raiz)

    saida = raiz / args.out_prompt
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(prompt, encoding="utf-8")
    print(f"[ai-diagnose] prompt gerado em {args.out_prompt} "
          f"({len(arquivos)} arquivo(s) de contexto, segredos mascarados)")

    chave = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not chave:
        print("[ai-diagnose] Sem credencial de API no ambiente. O prompt foi salvo "
              "como artefato para análise. O pipeline NÃO foi falhado por isso.")
        return 0

    # Com credencial, aqui entraria a chamada ao SDK do provedor e a publicação do
    # diagnóstico no Merge Request. Mantido como ponto de integração para não acoplar
    # o laboratório a um provedor específico nem exigir saldo de API para rodar.
    print("[ai-diagnose] Credencial detectada: integração com o provedor de LLM "
          "seria executada aqui, publicando o diagnóstico no Merge Request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
