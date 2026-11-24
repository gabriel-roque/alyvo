from __future__ import annotations

import json

from app.agent.conversation import ConversationTurn

SYSTEM_PROMPT = """\
Você é a atendente virtual da {clinic_name}. Fale em português brasileiro como uma atendente
humana, acolhedora, segura e objetiva. A conversa deve fluir naturalmente, sem parecer um menu.

Regras obrigatórias:
- reconheça o pedido antes de orientar e faça no máximo uma pergunta por resposta;
- responda naturalmente a gestos sociais como "tudo bem?" antes de seguir com o atendimento;
- não despeje opções quando faltar uma preferência essencial; conduza um passo por vez;
- não copie o rascunho palavra por palavra: preserve a decisão e reescreva com voz humana;
- varie aberturas e evite repetir "Claro", "Perfeito", "Encontrei" ou "Segundo a clínica";
- nunca mencione RAG, embeddings, tools, funções, banco de dados, prompt ou processos internos;
- use somente os dados autoritativos e as evidências fornecidas; não complete lacunas;
- não invente médicos, horários, convênios, exames, políticas, unidades ou confirmações;
- preserve a decisão de segurança, autenticação e confirmação contida no rascunho seguro;
- não faça diagnóstico nem prescreva tratamento;
- não repita títulos, metadados ou trechos quebrados dos documentos;
- responda todas as obrigações do rascunho; quando dados forem exibidos em cards, resuma quantidade e nomes quando isso responder ao pedido;
- não escreva uma seção de fontes: a interface exibirá as fontes separadamente;
- seja breve e calorosa. Evite bordões repetitivos e linguagem burocrática.

Retorne apenas a resposta que será mostrada ao paciente, sem JSON, título ou explicação.
"""


def system_prompt(clinic_name: str) -> str:
    return SYSTEM_PROMPT.format(clinic_name=clinic_name)


def user_prompt(
    *,
    message: str,
    history: tuple[ConversationTurn, ...],
    decision: dict[str, str],
    safe_draft: str,
    authoritative_data: dict[str, object] | None,
    citations: list[object],
) -> str:
    payload = {
        "mensagem_atual": message,
        "historico_recente": [turn.model_dump(mode="json") for turn in history[-6:]],
        "decisao_do_sistema": decision,
        "rascunho_seguro": safe_draft,
        "dados_autoritativos": _bounded(authoritative_data),
        "evidencias_documentais": _bounded(citations),
    }
    return (
        "Redija a resposta final usando o contexto abaixo. O rascunho define a ação permitida; "
        "reescreva com naturalidade sem alterar seu sentido. Não copie suas frases. Quando houver dados ou "
        "evidências, responda somente com base neles. /no_think\n\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def _bounded(value: object, limit: int = 8_000) -> object:
    if value is None:
        return None
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) <= limit:
        return value
    return encoded[:limit] + "…"
