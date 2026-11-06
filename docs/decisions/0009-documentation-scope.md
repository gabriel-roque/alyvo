---
slug: /decisions/0009-documentation-scope
---

# ADR 0009 — Escopo enxuto do portal de engenharia

- Status: Accepted
- Data: 2026-11-06
- Substitui parcialmente: ADR 0008

## Contexto

O portal Docusaurus foi criado com seções extensas de dados, API, operações e desenvolvimento. Esse volume diluía a navegação principal e duplicava informações mantidas em contratos executáveis, no código e na referência Scalar.

## Decisão

Manter no portal apenas a página inicial Alyvo Engineering, Primeiros passos, Arquitetura e Decisões ADR. A referência interativa da API continua no Scalar, fora da árvore documental.

## Alternativas

- Manter todas as seções: preservaria mais conteúdo, mas aumentaria ruído e risco de documentação desatualizada.
- Apenas ocultar as seções: deixaria páginas órfãs publicadas e sem responsabilidade clara de manutenção.

## Consequências

- A navegação fica curta e orientada às decisões estruturais.
- Conteúdo operacional, de API, dados e desenvolvimento deixa de ser publicado no portal.
- Mudanças arquiteturais continuam exigindo atualização dos diagramas e novos ADRs.

## Links

- [Alyvo Engineering](../index.md)
- [Visão geral da arquitetura](../architecture/overview.md)
- [ADR 0008](0008-docusaurus-documentation-portal.md)
