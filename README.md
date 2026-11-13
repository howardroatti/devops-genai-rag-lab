# Miniprojeto de DevOps com IA Generativa - assistente RAG

Atividade prática do **Módulo C14 - Unidade 5 (Projeto Integrador de DevOps com IA Generativa)**.
O laboratório mostra como a GenAI pode atuar como **primeiro analista** de falhas de um pipeline
CI/CD: uma aplicação Python com um **erro intencional**, testes automatizados, e um **agente de IA**
que lê os logs de falha e produz um diagnóstico com causa-raiz e sugestão de correção, sempre com
**supervisão humana**.

Dei continuidade ao projeto-fio dos módulos anteriores: a API RAG (FastAPI) do módulo C13 ganhou aqui
um pipeline de CI/CD e o agente de diagnóstico. Dados fictícios, sem credenciais no repositório.

## Repositório e pipelines

Repositório no **GitHub** (minha conta): o laboratório é baseado em GitLab, então incluí o
**`.gitlab-ci.yml` equivalente** além do workflow do GitHub Actions.

- [`.github/workflows/devops-ai.yml`](.github/workflows/devops-ai.yml) - job `testes` + job
  `diagnostico-ia` (só roda em caso de falha, `if: failure()`).
- [`.gitlab-ci.yml`](.gitlab-ci.yml) - estágios `test` e `ai-diagnosis` (`when: on_failure`),
  seguindo o mecanismo da Seção 5.2.2 do material.

## Execução do projeto

1. Instalar dependências: `pip install -r requirements-dev.txt`.
2. Rodar os testes: `python -m pytest -q` → **13 passam** (estado saudável).
3. Reproduzir a falha controlada (como no lab): `INJECT_BUG=1 python -m pytest -q` →
   **7 falham, 6 passam**. No CI, a flag é ligada pela variável de ambiente (GitLab) ou pela
   entrada `inject_bug` do disparo manual (GitHub), **sem alterar o código do repositório**.
4. Diagnóstico com IA sobre o log: `python scripts/ai_diagnose.py --log docs/devops-ai/pytest-failure.log`.

As evidências ficam em [`docs/devops-ai/`](docs/devops-ai/): o log de falha
([`pytest-failure.log`](docs/devops-ai/pytest-failure.log)), o prompt montado pelo agente
([`ai-prompt.md`](docs/devops-ai/ai-prompt.md)) e o diagnóstico
([`analysis.md`](docs/devops-ai/analysis.md)).

## O erro intencional (e por que ele é interessante)

A falha é injetada em [`src/rag_api/config.py`](src/rag_api/config.py): quando `INJECT_BUG=1`, a
função `ler_limiar_confianca()` devolve o limiar como **string**, esquecendo a conversão para `float`.
É uma alteração **sintaticamente correta, mas semanticamente errada**. O orquestrador então compara
`float < str` e estoura:

```text
TypeError: '<' not supported between instances of 'float' and 'str'
src/rag_api/orquestrador.py:55: TypeError
```

O detalhe importante: o traceback aponta `orquestrador.py`, mas a **causa-raiz está em `config.py`**,
que nem aparece no traceback. Por isso o agente anexa ao prompt não só os arquivos do traceback, mas
também os módulos que eles importam.

## Análise com IA generativa

O agente [`scripts/ai_diagnose.py`](scripts/ai_diagnose.py) implementa o mecanismo do material:
1. **Coleta de contexto:** lê o log do job que falhou e o código citado (mais os módulos importados).
2. **Engenharia de prompt:** monta um prompt estruturado pedindo causa-raiz em português técnico,
   correção em formato de código e riscos de segurança; **mascara segredos e anonimiza caminhos**.
3. **Feedback:** a análise seria publicada como comentário no Merge Request.

O diagnóstico (em [`analysis.md`](docs/devops-ai/analysis.md)) **acertou a causa-raiz**
(`config.py`, conversão ausente), separou **causa de sintoma** (recusou o remendo de `float(...)` na
linha da comparação, que deixaria a configuração ainda devolvendo `str`) e propôs a correção na
fronteira. Importante: a análise foi **produzida por Claude (Opus 4.8)** a partir de exatamente o
prompt salvo como artefato; o agente, sem chave de API no ambiente, **não falha o pipeline** - ele
grava o prompt e explica o motivo.

## Desafios encontrados

- **Causa-raiz fora do traceback:** a primeira versão do agente só mandava os arquivos do traceback,
  então o prompt não mostrava `config.py`. Passei a incluir os módulos importados.
- **Pipeline "verde" enganoso:** `pytest | tee` devolveria o código de saída do `tee`, deixando o job
  verde mesmo com testes vermelhos. Resolvi com `set -o pipefail`.
- **Dados sensíveis no log:** o log local trazia o caminho da pasta de usuário. O agente anonimiza
  `<HOME>` e mascara tokens/chaves; o log commitado já está limpo.
- **Credencial e custo de API:** sem chave, o SDK só falha na hora da requisição. O agente verifica a
  credencial antes e, sem ela, gera o prompt como artefato em vez de quebrar o pipeline (vários
  colegas relataram `429 insufficient_quota`; evitei acoplar o lab a saldo de API).
- **Injeção sem corromper o repo:** optei por injetar o bug via variável de ambiente, para o código
  versionado continuar correto e a falha ser reproduzível sob demanda.

## Reflexão crítica

**Vantagens.** A IA fez em segundos a triagem de 7 falhas e percebeu que todas tinham **uma única
causa**, evitando investigar vários problemas. Traduziu um `TypeError` cru em um diagnóstico com
evidências, apontou o arquivo certo (fora do traceback) e sugeriu uma correção mínima na fronteira.
Como primeiro analista, encurta o tempo entre "job vermelho" e "entendi o problema".

**Limitações.** Sem o contexto certo no prompt, a IA preenche lacunas com suposições plausíveis
(linhas inventadas, hipóteses falsas). E **"pipeline verde" não é "correção completa"**: o patch
mínimo passa nos testes, mas valores inválidos de `RAG_LIMIAR` (`"abc"`, `"0"`, fora de `[0,1]`)
continuariam produzindo erro ou resultado sem sentido, porque a IA só enxerga o que os testes cobrem.
Há ainda custo, dependência de serviço externo e risco de vazar dados do log.

**Por que validar antes de aplicar.** O diagnóstico é uma **hipótese bem escrita, não uma prova**.
Validar aqui significou conferir a causa no código, aplicar o patch numa cópia e rodar a suíte, e
**testar entradas que os testes não cobrem** (como `RAG_LIMIAR` inválido), transformando o que a IA
não viu em novos testes. A IA acelera a investigação; a decisão, a correção e a **responsabilidade**
continuam humanas.

## Organização

```text
devops-genai-rag-lab/
├── README.md
├── .gitlab-ci.yml                 # pipeline GitLab (test + ai-diagnosis on_failure)
├── .github/workflows/devops-ai.yml# pipeline equivalente no GitHub Actions
├── src/rag_api/                   # API RAG (FastAPI): componentes, orquestrador, api, config (bug)
├── tests/                         # 13 testes de integração (pytest + TestClient)
├── scripts/ai_diagnose.py         # agente de diagnóstico (coleta, prompt, máscara de segredos)
├── docs/devops-ai/
│   ├── pytest-failure.log         # log da execução com a falha (anonimizado)
│   ├── ai-prompt.md               # prompt montado pelo agente
│   └── analysis.md                # diagnóstico da IA (produzido por Claude a partir do prompt)
├── requirements.txt
└── requirements-dev.txt
```
