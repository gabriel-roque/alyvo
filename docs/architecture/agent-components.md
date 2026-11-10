# Componentes do agente

```mermaid
flowchart TD
  Message[Mensagem + contexto não sensível] --> Normalize[Normalize]
  Normalize --> Guard[Guardrails determinísticos]
  Guard --> Understand[Understand]
  Understand --> Rules[Regras ordenadas]
  Rules -->|sem decisão| Semantic[Classificador semântico estruturado]
  Rules -->|decisão clara| Context[Resolução de contexto e slots]
  Semantic --> Context
  Context --> Policy[DecisionPolicy]

  Policy -->|small talk| Direct[Resposta direta]
  Policy -->|faltam slots| Clarify[Clarificação]
  Policy -->|dados atuais| Tool[Tool plan]
  Policy -->|documentos aprovados| RAG[RAG plan]
  Policy -->|risco| Reject[Resposta de segurança]

  Tool --> Registry[ToolRegistry]
  Registry --> Auth[Autenticação e confirmação]
  Auth --> Handler[Handler tipado]
  Handler --> UseCase[Caso de uso]
  RAG --> Retrieval[Busca híbrida + answerability]

  Direct --> Compose[LLM ResponseComposer]
  Clarify --> Compose
  Reject --> Compose
  UseCase --> Validate[Validação do resultado]
  Retrieval --> Validate
  Validate --> Compose
  Compose -->|indisponível ou inválido| Fallback[Presenter determinístico]
  Compose --> Answer[Resposta + fontes separadas]
  Fallback --> Answer
```

O roteamento é híbrido. Segurança, saudações puras e operações críticas usam regras previsíveis. O classificador semântico é apenas o último recurso para linguagem ambígua e retorna um contrato validado; ele não executa ferramentas.

`DecisionPolicy` escolhe resposta direta, clarificação, tool ou RAG. Dados vivos de agenda e catálogo sempre vêm de tools. Políticas e informações institucionais vêm apenas de documentos publicados.

`ConversationContext` guarda somente preferências operacionais, como data e período. Identidade, tokens e dados pessoais não são persistidos nele. Uma saudação acompanhada de pedido funciona como marcador de tom e não interrompe a intenção principal.

O registry é a fonte de schema, risco, autenticação, confirmação, idempotência, timeout e auditoria das tools. Depois da execução, o `LlmResponseComposer` recebe o histórico recente, o rascunho seguro, o resultado estruturado e as evidências recuperadas. Ele pode alterar somente o texto apresentado; flags, fontes, autenticação, confirmação e resultados permanecem autoritativos.

Decisões clínicas e de segurança não dependem do LLM. Se o provedor falhar, exceder o limite ou produzir conteúdo com metadados internos, o presenter determinístico assume a resposta. Documentos recuperados são dados, nunca instruções.
