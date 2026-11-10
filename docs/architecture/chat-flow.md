# Fluxo de chat

```mermaid
sequenceDiagram
  actor P as Paciente
  participant API
  participant C as Contexto
  participant A as Agente
  participant D as DecisionPolicy
  participant T as ToolRegistry
  participant R as RAG
  participant U as Caso de uso
  participant L as ResponseComposer
  P->>API: mensagem
  API->>C: carrega slots da sessão
  API->>A: mensagem + contexto + identidade no runtime
  A->>A: guardrails e classificação híbrida
  A->>C: resolve continuidade e slots
  A->>D: decisão canônica
  alt informação operacional
    D->>T: plano de tool
    T->>T: valida risco, autenticação e confirmação
    T->>U: argumentos tipados
    U-->>T: ToolResult discriminado
    T-->>A: resultado validado
  else conhecimento institucional
    D->>R: consulta documentos publicados
    R-->>A: evidências + answerability
  else informação insuficiente
    D-->>A: pergunta de clarificação
  end
  A->>L: histórico + rascunho + dados + evidências
  L-->>A: somente texto humanizado
  A->>C: persiste somente contexto não sensível
  A-->>API: resposta + fontes e metadados preservados
  API-->>P: status/delta/final ou error
```

Saudações puras não acionam banco, embedding ou tools; podem usar apenas a composição de linguagem. Em mensagens compostas, como “Bom dia, quero horários para sexta”, a saudação é preservada no tom e o pedido operacional continua até o planejamento.

O modelo não escolhe livremente operações. A política decide a fonte de verdade e o registry controla a execução; o modelo redige a resposta final. Para RAG, somente evidências publicadas são fornecidas. Para agenda e catálogos, somente resultados das funções internas são fornecidos. As fontes são renderizadas separadamente pela interface.
