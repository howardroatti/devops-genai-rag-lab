# Diagnóstico automático de falha (GenAI)

> Produzido por Claude (Opus 4.8) a partir de exatamente o prompt em
> [`ai-prompt.md`](ai-prompt.md), que o agente [`scripts/ai_diagnose.py`](../../scripts/ai_diagnose.py)
> montou com o log de falha e o código importado no traceback. É uma hipótese bem
> fundamentada, não uma prova: ver a validação humana no fim e no README.

## RESUMO
O pipeline quebrou com `TypeError: '<' not supported between instances of 'float' and 'str'`.
As 7 falhas são do mesmo tipo e têm uma **única causa**: o limiar de confiança está sendo
lido como texto, e não como número.

## EVIDÊNCIAS
- `src/rag_api/orquestrador.py:55` — `recuperados[0][1] < limiar` (float `<` str).
- O traceback cita `api.py:69` e `orquestrador.py:55`, mas **não** cita `config.py`.
- Falham os testes que chegam à comparação de confiança (fluxo completo, schema,
  sem_contexto, permissão); passam os que retornam antes (saúde, guardrail, 422).

## CAUSA-RAIZ (arquivo:linha)
`src/rag_api/config.py:34` — `ler_limiar_confianca()` devolve `os.getenv(...)` **sem
converter para `float`** quando `INJECT_BUG=1`. O sintoma aparece no orquestrador, mas a
origem é a leitura de configuração na fronteira. Investigar só os arquivos do traceback
levaria a "consertar" no lugar errado.

## CORREÇÃO (em formato de código)
Converter o valor na fronteira, em `config.py`:

```python
def ler_limiar_confianca() -> float:
    bruto = os.getenv("RAG_LIMIAR", LIMIAR_PADRAO)
    return float(bruto)   # sempre converter; remover o ramo do INJECT_BUG
```

Evitar o remendo tentador de `float(...)` na linha da comparação em `orquestrador.py`:
isso trata o sintoma e deixa a configuração ainda devolvendo `str` para outros chamadores.

## RISCOS DE SEGURANÇA
Baixo para este defeito (erro de tipo, não de dado). Atenção geral: o log de CI pode
conter caminhos de usuário e credenciais; o agente já anonimiza `<HOME>` e mascara
tokens/chaves antes de enviar qualquer coisa ao provedor de LLM.

## COMO VALIDAR
1. Aplicar o patch numa cópia e rodar `python -m pytest -q` sem `INJECT_BUG` → esperado verde.
2. Rodar com `INJECT_BUG=1` para confirmar que a flag ainda reproduz a falha (controle do lab).
3. Testar valores de borda da variável `RAG_LIMIAR` que a suíte não cobre (ver premissas).

## CONFIANÇA / PREMISSAS
Confiança alta na causa-raiz (o traceback e o código são conclusivos). **Premissa a
validar pelo humano:** a correção mínima (`float`) resolve o `TypeError`, mas **não** trata
valores inválidos da variável de ambiente, como `"abc"` (→ `ValueError`), `"0"` (divisão por
zero conceitual no limiar) ou valores fora de `[0, 1]`. A correção robusta deveria validar
faixa e tipo na fronteira. Isso está fora do que os testes atuais cobrem.
