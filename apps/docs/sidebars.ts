import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  engineering: [
    'index',
    'getting-started',
    {
      type: 'category',
      label: 'Casos de uso',
      collapsed: false,
      items: ['use-cases/test-prompts'],
    },
    {
      type: 'category',
      label: 'Arquitetura',
      collapsed: false,
      items: [
        'architecture/overview',
        'architecture/context',
        'architecture/containers',
        'architecture/component-responsibilities',
        'architecture/backend-components',
        'architecture/agent-components',
        'architecture/frontend-components',
        'architecture/deployment',
        'architecture/chat-flow',
        'architecture/scheduling-flow',
        'architecture/knowledge-flow',
      ],
    },
    {
      type: 'category',
      label: 'Decisões ADR',
      collapsed: false,
      items: [
        'decisions/modular-monolith',
        'decisions/single-clinic',
        'decisions/unit-of-work-and-outbox',
        'decisions/langgraph-boundary',
        'decisions/openapi-contract-first',
        'decisions/alembic',
        'decisions/scalar-api-reference',
        'decisions/docusaurus-documentation-portal',
        'decisions/documentation-scope',
        'decisions/hybrid-agent-routing',
        'decisions/grounded-llm-response-composition',
        'decisions/template',
      ],
    },
  ],
};

export default sidebars;
