---
slug: /decisions/0008-docusaurus-documentation-portal
---

# ADR 0008 — Docusaurus como portal de engenharia

Status: Accepted

## Contexto

O portal precisa manter arquitetura, diagramas Mermaid, decisões ADR, modelo de dados, contratos e runbooks, além de permitir evolução visual e componentes interativos no mesmo monorepo Node do frontend.

## Decisão

Adotar Docusaurus em modo docs-only, com conteúdo Markdown em `docs/`, navegação explícita em `sidebars.ts`, Mermaid oficial e build estático servido por Nginx. As rotas permanecem na raiz do portal em `localhost:8001`.

## Alternativas

- MkDocs Material: simples e maduro, mas mantém uma segunda toolchain Python para o portal.
- Site Next.js próprio: flexível, porém exigiria implementar navegação, índices e recursos documentais.
- Geradores sem aplicação React: menor custo, com menos extensibilidade para conteúdo interativo.

## Consequências

- Arquitetura e ADRs continuam documentação como código e passam a aceitar MDX/React.
- Mermaid, links e build são validados na CI pelo Docusaurus.
- Dependências MkDocs saem do ambiente Python e entram no workspace npm.
- O portal exige Node.js 20 ou superior.

## Links

- [Visão geral da arquitetura](../architecture/overview.md)
- [Primeiros passos](../getting-started.md)
