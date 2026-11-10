---
slug: /decisions/0010-hybrid-agent-routing
---

# ADR 0010 — Roteamento híbrido e contexto conversacional

- Status: Accepted
- Data: 2026-11-10

## Contexto

O roteamento determinístico reduziu latência e alucinação, mas correspondências simples de palavras-chave não representavam bem mensagens compostas, negações e continuidades como “à tarde”. Permitir que um LLM escolhesse e executasse livremente qualquer ferramenta reduziria previsibilidade em operações sensíveis.

## Decisão

Adotar roteamento híbrido com as seguintes fronteiras:

- guardrails e caminhos críticos permanecem determinísticos;
- small talk só encerra o fluxo quando for a solicitação completa;
- o classificador semântico é um fallback estruturado e não executa tools;
- `DecisionPolicy` produz um plano tipado e auditável;
- `ConversationContext` persiste apenas slots operacionais não sensíveis;
- dados estruturados e atuais usam tools;
- documentos institucionais publicados usam RAG;
- autenticação e confirmação são impostas pelo `ToolRegistry`;
- baixa confiança ou ausência de slots resulta em clarificação.

## Alternativas

- LLM autônomo para todo o roteamento: mais flexível, porém mais lento e menos previsível.
- Somente regras textuais: rápido, mas frágil diante de paráfrases, negação e múltiplos turnos.
- Persistir todo o histórico no estado do grafo: simplifica contexto, mas aumenta exposição de dados e acoplamento.

## Consequências

- saudações e rotas claras continuam rápidas;
- mensagens compostas preservam o pedido principal;
- preferências de data e período sobrevivem entre turnos;
- planos e origem da decisão passam a ser observáveis;
- novas intenções exigem contrato, política, testes de avaliação e tool tipada quando aplicável;
- o comportamento do agente não pode ser alterado por instruções recuperadas de documentos.

## Links

- [Componentes do agente](../architecture/agent-components.md)
- [Fluxo de chat](../architecture/chat-flow.md)
- [ADR 0004](0004-langgraph-boundary.md)
