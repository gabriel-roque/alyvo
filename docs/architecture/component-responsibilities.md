# Responsabilidades dos componentes

Esta página explica por que cada componente arquitetural existe e qual papel ele exerce no Alyvo. A distinção principal é entre a **fonte de verdade**, mantida no PostgreSQL, e os componentes auxiliares de processamento, armazenamento, busca e geração de linguagem.

## Aplicação

| Componente | Para que serve | Onde é usado |
| --- | --- | --- |
| **Next.js (Web)** | Entrega a interface para pacientes, equipe e administradores. | Autenticação, chat, agendamento e backoffice de conhecimento. Consome somente a API HTTP do Alyvo. |
| **FastAPI (API)** | Expõe os endpoints HTTP, autentica usuários, valida entradas e encaminha cada requisição ao caso de uso correspondente. | É a fronteira síncrona do sistema. Também publica a referência OpenAPI/Scalar quando habilitada. |
| **LangGraph** | Organiza o fluxo interno do agente em etapas previsíveis: normalizar, classificar, planejar, executar, validar e apresentar. | Orquestra o chat, mas não acessa livremente a infraestrutura. Operações de negócio passam por tools tipadas e casos de uso. |
| **Celery worker** | Executa trabalho assíncrono e reprocessável fora do ciclo de uma requisição HTTP. | Processa documentos enviados, consome eventos da outbox e atualiza projeções no Neo4j. As tarefas têm retry e backoff. |
| **Celery beat** | Dispara tarefas periódicas do Celery. | A cada cinco segundos agenda o consumo de um lote da outbox transacional. Não executa o trabalho; apenas agenda a tarefa para o worker. |

## Dados e infraestrutura

| Componente | Para que serve | O que não é |
| --- | --- | --- |
| **PostgreSQL** | É a **fonte de verdade** do Alyvo. Persiste usuários, catálogo, médicos, agenda, documentos e chunks, conversas, tokens, auditoria e outbox. Garante transações e restrições de integridade, como impedir consultas sobrepostas para o mesmo médico. | Não armazena os arquivos binários originais dos uploads. A busca SQL de conhecimento existe como fallback quando a projeção no Neo4j não está disponível ou não encontra evidência. |
| **Redis** | É o broker de mensagens e o backend de resultados do Celery. Faz a ponte entre o Celery beat e os workers para a execução das tarefas assíncronas. | Atualmente não é fonte de verdade, cache da API, armazenamento de sessão nem substituto do PostgreSQL. |
| **MinIO** | Armazena de forma privada os arquivos originais enviados para a base de conhecimento, usando uma interface compatível com S3. | Não guarda os registros de negócio nem o texto processado. Metadados, estado do processamento, conteúdo extraído e chunks ficam no PostgreSQL. |
| **Neo4j** | Mantém uma projeção otimizada para leitura e busca. Guarda relações de médicos e catálogo e, para conhecimento publicado, permite busca híbrida por texto completo e vetores com fusão de ranking. | Não é a fonte de verdade. A projeção é alimentada de forma idempotente pela outbox e pode ser reconstruída a partir do PostgreSQL. |

## Modelos e processamento de conhecimento

| Componente | Para que serve | Onde é usado |
| --- | --- | --- |
| **Ollama** | Executa localmente o modelo de linguagem configurado para o Alyvo. Evita depender exclusivamente de um provedor externo. | É o fallback do OpenRouter na composição das respostas e, quando o roteamento por LLM está habilitado, na classificação de mensagens ambíguas. Também atende o LangGraph Studio local. |
| **OpenRouter** | Oferece acesso ao modelo de linguagem remoto configurado como provedor primário. | É usado somente quando provedores externos estão permitidos e existe uma chave de API. Se estiver indisponível, o sistema tenta Ollama e ainda preserva um presenter determinístico como último fallback. |
| **BGE-M3** | Converte trechos de documentos e perguntas em vetores semânticos. | Gera embeddings durante o processamento de documentos e durante a busca vetorial no Neo4j. |
| **PaddleOCR** | Extrai texto de arquivos que precisam de reconhecimento óptico. | É executado pelo worker durante a ingestão de documentos antes da divisão em chunks e da geração de embeddings. |
| **LangSmith** | Recebe traces do ecossistema LangChain/LangGraph para observabilidade, quando explicitamente habilitado. | É opcional e não participa da execução das regras de negócio nem persiste o estado autoritativo. |

O modelo de linguagem não decide sozinho qual operação executar e não altera dados diretamente. Regras determinísticas e a `DecisionPolicy` escolhem o tipo de plano; o `ToolRegistry` controla autenticação, confirmação e execução; o LLM apenas classifica casos ambíguos quando habilitado e humaniza uma resposta já fundamentada.

## Como os componentes colaboram

### Upload e publicação de conhecimento

1. A API grava o arquivo original no MinIO e registra documento e evento de outbox no PostgreSQL.
2. O Celery beat agenda periodicamente o consumo da outbox por meio do Redis.
3. O Celery worker lê o arquivo no MinIO, executa OCR, cria chunks e embeddings e persiste o resultado no PostgreSQL para revisão.
4. Depois da publicação, outro evento da outbox faz o worker projetar os chunks e vetores no Neo4j.
5. No chat, a API consulta primeiro a busca híbrida do Neo4j; se ela falhar ou não produzir evidência, usa a busca lexical no PostgreSQL como fallback.

### Resposta do chat

1. A API carrega a conversa e executa o grafo do agente.
2. Regras e políticas escolhem entre resposta direta, clarificação, tool de negócio, busca de conhecimento ou rejeição segura.
3. Dados atuais de agenda e catálogo vêm dos casos de uso apoiados pelo PostgreSQL; conhecimento institucional publicado vem da recuperação no Neo4j, com fallback SQL.
4. OpenRouter ou Ollama pode redigir a resposta final sem alterar resultados, fontes ou flags de segurança. Se nenhum modelo responder de forma válida, o presenter determinístico produz a resposta.

## Regra prática de recuperação

- Se o **PostgreSQL** for perdido, há perda do estado de negócio autoritativo.
- Se o **MinIO** for perdido, os arquivos originais deixam de estar disponíveis para novo processamento.
- Se o **Neo4j** for perdido, a projeção pode ser reconstruída a partir dos dados e eventos mantidos no PostgreSQL.
- Se o **Redis** for reiniciado, o estado de negócio permanece no PostgreSQL e a outbox ainda pode ser consumida; tarefas em trânsito precisam ser reenviadas pelo ciclo de processamento.
- Se **OpenRouter ou Ollama** estiver indisponível, as regras, tools e respostas determinísticas continuam sendo a camada segura de fallback.
