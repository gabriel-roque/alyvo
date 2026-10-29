# Design System Editorial Premium

**Editorial Premium** é o design system oficial do MVP do Alyvo. Sua direção visual combina linguagem editorial suíça, minimalista, clínica, tecnológica e acessível, com grande uso de espaço negativo, uma tarefa principal por tela e alta legibilidade.

## Fundamentos

### Cores

| Token | Valor | Uso |
| --- | --- | --- |
| Paper | `#F7F7F2` | Fundo principal. |
| Ink | `#101828` | Texto, títulos e ícones. |
| Cobalt | `#2457FF` | Ação primária, seleção, link e foco. |
| Lime | `#B8F34A` | Apenas pequenos acentos; nunca usar em grandes fundos. |
| Cool Gray | `#D8DDE6` | Divisórias, bordas e estados neutros. |
| Success | `#16A34A` | Estados de sucesso. |
| Warning | `#D97706` | Estados de atenção. |
| Error | `#DC2626` | Estados de erro. |

O Lime deve aparecer somente em indicadores pequenos de disponibilidade, sucesso ou validação. Cobalt continua sendo a cor interativa e não deve ser substituído por Lime em ações, links, seleção ou foco.

### Tipografia

A família tipográfica oficial é **Inter**.

| Estilo | Tamanho/entrelinha | Peso |
| --- | --- | --- |
| Display | `64/64` | `800` |
| H1 | `48/52` | `700` |
| H2 | `32/38` | `600` |
| Body | `16/24` | `400` |
| Label | `12/16` | `500`, com tracking |

### Espaçamento, raios e profundidade

- Escala de espaçamento: `4`, `8`, `12`, `16`, `24`, `32`, `48` e `64px`.
- Raios: `4`, `8` e `12px`.
- Evitar *rounded everything*: o raio deve comunicar agrupamento ou função, não decorar indiscriminadamente.
- Bordas: `1px` em Cool Gray.
- Sombras: discretas e usadas apenas quando a hierarquia exigir separação de planos.

### Ícones

- Usar **Lucide**, com traço consistente.
- Tamanhos padrão: `20px` e `24px`.
- Não usar emojis como elementos de interface.

## Composição

- Comunicar uma mensagem principal por seção.
- Exibir no máximo dois CTAs simultâneos.
- Limitar o hero a no máximo três benefícios.
- Manter o chat fechado por padrão.
- Revelar conteúdo progressivamente abaixo da dobra.
- Evitar excesso de cards, métricas e contêineres visuais.
- Preservar espaço negativo e uma tarefa principal por tela.

## Acessibilidade

- Atender contraste **WCAG AA**.
- Manter foco visível em todos os controles interativos.
- Usar alvos de interação com pelo menos `44px`.
- Garantir navegação completa por teclado.
- Respeitar a preferência `prefers-reduced-motion`.
- Manter o texto base em no mínimo `16px`.

## Referências visuais

As imagens abaixo são referências direcionais para composição, hierarquia e linguagem visual; não são contratos pixel-perfect. Os componentes e tokens implementados no código serão a fonte executável de verdade.

| Arquivo | Descrição |
| --- | --- |
| [00-design-system-editorial-premium.png](references/00-design-system-editorial-premium.png) | Visão geral do sistema, com paleta, tipografia, espaçamento e componentes-base. |
| [01-home-publica.png](references/01-home-publica.png) | Direção da home pública, hierarquia editorial, hero e entrada discreta para o chat. |
| [02-chat-rag-graphrag.png](references/02-chat-rag-graphrag.png) | Conversa administrativa com respostas fundamentadas, fontes e recuperação RAG/GraphRAG. |
| [03-agendamento.png](references/03-agendamento.png) | Fluxo de seleção de disponibilidade, resumo e confirmação de agendamento. |
| [04-ocr-confirmacao-documento.png](references/04-ocr-confirmacao-documento.png) | Revisão e confirmação dos campos extraídos de documento antes da persistência. |
| [05-backoffice-agenda.png](references/05-backoffice-agenda.png) | Agenda do back office com foco operacional, filtros e leitura clara dos estados. |
| [06-ingestao-graphrag.png](references/06-ingestao-graphrag.png) | Ingestão institucional, revisão e publicação controlada no GraphRAG. |

## Checklist de consistência

- [ ] A tela tem uma tarefa principal e hierarquia inequívoca.
- [ ] Cores, tipografia, espaçamento, raios, bordas e ícones usam os tokens oficiais.
- [ ] Cobalt identifica interações; Lime aparece somente como pequeno indicador permitido.
- [ ] Não há excesso de cards, métricas, CTAs ou elementos arredondados.
- [ ] Contraste, foco, teclado, alvos de `44px`, texto de `16px` e reduced motion foram verificados.
- [ ] A implementação consulta estas regras e as referências relevantes sem copiá-las como contrato pixel-perfect.
