---
slug: /decisions/0011-grounded-llm-response-composition
---

# ADR 0011 — Composição de respostas fundamentada por LLM

- Status: Accepted
- Data: 2026-11-10

## Contexto

O roteamento híbrido e as tools tipadas tornaram decisões e operações previsíveis. Entretanto, o presenter concatenava templates e trechos recuperados, produzindo respostas corretas, mas burocráticas, repetitivas e pouco sensíveis ao histórico da conversa. Entregar também a autorização de execução ao LLM aumentaria o risco de ações indevidas e alucinação.

## Decisão

Separar autoridade operacional de composição de linguagem:

- `DecisionPolicy` continua escolhendo resposta direta, clarificação, RAG ou tool;
- `ToolRegistry` continua impondo schema, autenticação, confirmação e risco;
- o RAG fornece apenas evidências de documentos publicados;
- o `LlmResponseComposer` recebe histórico recente, decisão, rascunho seguro, dados autoritativos e evidências;
- o LLM pode substituir somente `answer`;
- citações, resultados, intent, autenticação e confirmação não podem ser alterados pelo modelo;
- decisões clínicas e de segurança permanecem determinísticas;
- saída vazia, excessiva ou com termos internos aciona o fallback determinístico;
- fontes permanecem separadas da linguagem exibida ao paciente.

## Alternativas

- Manter templates: menor custo, mas experiência rígida e difícil de evoluir.
- Agente autônomo com function calling irrestrito: maior flexibilidade, porém mistura linguagem, decisão e autorização.
- Gerar respostas sem rascunho seguro: reduz contexto, mas perde um limite explícito para autenticação, confirmação e abstinência.

## Consequências

- respostas podem reconhecer o turno anterior e variar naturalmente;
- conhecimento recuperado deixa de ser colado diretamente na conversa;
- falhas do provedor não interrompem o atendimento;
- toda nova tool continua precisando de contrato e política, não apenas de descrição no prompt;
- testes devem garantir grounding, preservação de metadados e ausência de chamada ao LLM em decisões bloqueadas;
- a latência passa a incluir uma geração curta, limitada e sem raciocínio explícito.

## Links

- [Componentes do agente](../architecture/agent-components.md)
- [Fluxo de chat](../architecture/chat-flow.md)
- [ADR 0010](0010-hybrid-agent-routing.md)
