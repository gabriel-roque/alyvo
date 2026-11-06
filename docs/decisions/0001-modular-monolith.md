---
slug: /decisions/0001-modular-monolith
---

# ADR 0001 — Monólito modular

- Status: Accepted
- Data: 2026-11-05

## Contexto

Arquivos grandes misturavam HTTP, persistência, agente e negócio, elevando acoplamento e custo de mudança.

## Decisão

Adotar monólito modular com módulos identity, catalog, scheduling, knowledge e conversations, kernel compartilhado mínimo e dependências para dentro.

## Alternativas

Manter estrutura por camada global preservaria acoplamento. Microserviços ampliariam custo operacional sem necessidade atual.

## Consequências

Fronteiras testáveis e coesão lexical melhor; exige disciplina de imports e contracts automatizados.

## Links

[Visão geral](../architecture/overview.md).
