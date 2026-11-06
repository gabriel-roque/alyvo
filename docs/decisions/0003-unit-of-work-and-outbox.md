---
slug: /decisions/0003-unit-of-work-and-outbox
---

# ADR 0003 — Unit of Work e Outbox

- Status: Accepted
- Data: 2026-11-05

## Contexto

Negócio, histórico, auditoria e projeções precisam ser consistentes mesmo com falhas externas.

## Decisão

Handlers escrevem via Unit of Work. Estado, histórico, audit e outbox são persistidos na mesma transação; worker projeta idempotentemente.

## Alternativas

Publicação direta após commit cria dual write. Transação distribuída é inadequada para os provedores usados.

## Consequências

Recuperação confiável e reprocessamento; requer monitorar lag e manter handlers idempotentes.

## Links

[Fluxo de conhecimento](../architecture/knowledge-flow.md).
