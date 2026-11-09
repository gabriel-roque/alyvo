# Fluxo de conhecimento

```mermaid
sequenceDiagram
  actor A as Admin
  participant API
  participant DB as PostgreSQL
  participant W as Worker
  participant O as OCR/Embedding
  participant N as Neo4j
  A->>API: upload de um ou mais arquivos
  API->>DB: documento + outbox por arquivo
  W->>DB: claim transacional por evento
  W->>O: extrair e vetorizar
  W->>DB: chunks para revisão
  A->>API: publicar
  API->>DB: estado + outbox
  W->>N: projeção idempotente
```

Cada arquivo é processado isoladamente. Falhas persistem o estado e a causa técnica no documento; reprocessamentos são idempotentes e não duplicam chunks.
