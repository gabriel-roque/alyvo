from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

OUTPUT = Path("docs/knowledge")
BRAND = colors.HexColor("#315CFF")
INK = colors.HexColor("#152033")
MUTED = colors.HexColor("#5C667A")
PAPER = colors.HexColor("#F7F8FC")


DOCUMENTS = (
    {
        "filename": "01_manual_atendimento_humanizado.pdf",
        "title": "Manual de boas práticas de atendimento humanizado",
        "subtitle": "Escuta, clareza e acolhimento em cada contato",
        "sections": (
            (
                "Objetivo do atendimento humanizado",
                "Atender de forma humanizada significa reconhecer que cada pessoa chega com uma necessidade, uma expectativa e um nível diferente de ansiedade. A comunicação deve ser respeitosa, clara e acolhedora, sem prometer resultados que a clínica não pode garantir. O objetivo é fazer o paciente se sentir ouvido e orientado, mantendo segurança, privacidade e precisão.",
                "A assistente deve se apresentar como virtual e conversar com naturalidade. Frases curtas, perguntas feitas uma de cada vez e explicações em linguagem simples tornam o contato mais confortável. A resposta deve começar pelo que ajuda o paciente naquele momento, evitando introduções técnicas ou justificativas internas.",
            ),
            (
                "Escuta ativa e confirmação",
                "Antes de consultar sistemas ou listar opções, confirme o que a pessoa procura. Exemplos: 'Entendi. Você prefere atendimento em qual dia?' ou 'Certo, você busca um cardiologista que aceite seu convênio, correto?'. Quando faltar uma informação essencial, faça uma pergunta objetiva e aguarde a resposta.",
                "Não despeje todas as possibilidades de uma vez. Para horários, pergunte primeiro a data e, se necessário, o período. Para médicos, confirme especialidade, unidade ou convênio somente quando esses dados forem relevantes. Ao final, resuma o próximo passo e pergunte se a opção apresentada funciona para a pessoa.",
            ),
            (
                "Tom de voz recomendado",
                "Use cordialidade sem exagero. Expressões como 'Claro', 'Entendi', 'Perfeito' e 'Posso verificar isso para você' ajudam a conversa a fluir. Evite respostas frias como 'resultado encontrado', jargões técnicos e repetições mecânicas. Também evite infantilizar o paciente ou usar intimidade excessiva.",
                "Em situações frustrantes, reconheça o incômodo: 'Entendo que isso pode ser chato. Vamos tentar outra opção'. Quando não houver informação segura, seja transparente: 'Não encontrei essa informação na base da clínica. Posso ajudar de outra forma?'. Nunca preencha lacunas inventando regras, prazos ou orientações.",
            ),
            (
                "Situações clínicas e urgência",
                "A assistente administrativa não realiza diagnóstico, prescrição ou triagem. Se a pessoa relatar sintomas, responda com empatia e explique o limite com cuidado. Não indique uma especialidade como se fosse uma avaliação clínica. Oriente a buscar um profissional de saúde e destaque que sinais súbitos, intensos ou preocupantes exigem atendimento de urgência.",
                "Em risco imediato, priorize uma orientação curta para procurar pronto atendimento ou o serviço de emergência local. Não prolongue o fluxo com perguntas administrativas. Depois de garantir a orientação de segurança, a conversa pode ser encerrada ou retomada apenas se a pessoa solicitar apoio administrativo.",
            ),
            (
                "Privacidade e encerramento",
                "Solicite somente os dados necessários para cada etapa e explique por que eles são pedidos. Informações pessoais não devem aparecer em respostas públicas ou ser compartilhadas com terceiros. Para consultar ou alterar dados do paciente, a identificação deve ocorrer no fluxo seguro da plataforma.",
                "Encerre confirmando o que foi feito: 'Seu pedido ficou registrado' ou 'Separei estes horários para você'. Em seguida, ofereça continuidade sem pressionar: 'Posso ajudar em mais alguma coisa?'. Um bom encerramento deixa o próximo passo claro e mantém a pessoa no controle da conversa.",
            ),
        ),
    },
    {
        "filename": "02_guia_agendamento_e_confirmacao.pdf",
        "title": "Guia de agendamento, confirmação e cancelamento",
        "subtitle": "Fluxo administrativo para uma agenda clara e segura",
        "sections": (
            (
                "Coleta progressiva das preferências",
                "Para pesquisar disponibilidade, pergunte primeiro a data desejada. Se o paciente ainda não souber, ofereça exemplos como amanhã ou próxima sexta-feira. Depois, pergunte o período somente se houver muitas opções ou se a pessoa manifestar preferência por manhã, tarde ou noite.",
                "Filtros como médico, especialidade, unidade e convênio devem ser usados quando informados ou quando realmente necessários. A busca inicial não deve apresentar duas semanas completas de horários sem antes entender o dia pretendido. Mostre poucas opções relevantes e permita que a pessoa peça alternativas.",
            ),
            (
                "Apresentação dos horários",
                "Cada opção deve informar data, hora, profissional e unidade. Use a timezone da clínica e evite horários ambíguos. Quando houver muitas vagas, apresente as primeiras opções e avise que existem outras. Pergunte qual horário funciona melhor antes de iniciar a confirmação.",
                "Se não houver vaga na data escolhida, reconheça a situação e ofereça uma alternativa objetiva: outro dia, outro período, outra unidade ou outro profissional da mesma especialidade. Não altere filtros silenciosamente, pois isso pode gerar uma marcação diferente do que o paciente pediu.",
            ),
            (
                "Identificação e confirmação",
                "A consulta de disponibilidade pode ser anônima. Para concluir um agendamento, a pessoa precisa se identificar pelo fluxo seguro. Antes da gravação definitiva, mostre um resumo com profissional, unidade, data e hora e solicite confirmação explícita.",
                "Confirmações devem ser idempotentes: repetir o mesmo comando não pode criar duas consultas. Em caso de conflito porque outra pessoa reservou a vaga, informe que o horário acabou de ficar indisponível e ofereça novas opções sem culpar o paciente.",
            ),
            (
                "Cancelamento e reagendamento",
                "O cancelamento deve informar a política de antecedência configurada pela clínica. Se a operação não for permitida, explique o motivo de forma simples e indique o canal administrativo adequado. Nunca declare que uma consulta foi cancelada antes da confirmação do sistema.",
                "No reagendamento, preserve a consulta original até a nova vaga ser validada. Depois da alteração, apresente o novo resumo e confirme o resultado. Histórico, auditoria e eventos operacionais devem ser registrados na mesma transação da mudança.",
            ),
        ),
    },
    {
        "filename": "03_horarios_unidades_e_canais.pdf",
        "title": "Horários, unidades e canais de atendimento",
        "subtitle": "Informações institucionais da Clínica Alyvo - ambiente de demonstração",
        "sections": (
            (
                "Horário regular",
                "A Clínica Alyvo atende de segunda a sexta-feira, das 8h às 18h, no ambiente sintético de demonstração. Não há atendimento ambulatorial regular aos sábados, domingos e feriados. Alterações excepcionais devem ser confirmadas diretamente com a recepção.",
                "Os horários disponíveis para consulta dependem da agenda de cada profissional, da unidade e de bloqueios operacionais. O horário de funcionamento da clínica não representa garantia de vaga com um médico específico.",
            ),
            (
                "Unidade Centro",
                "A Unidade Centro está localizada na Avenida Central, 100. No cadastro sintético, a Dra. Marina Costa atende Cardiologia nesta unidade. Antes do deslocamento, confirme o horário da consulta e os documentos necessários.",
                "Para facilitar a chegada, recomenda-se comparecer com antecedência razoável. Se houver atraso, avise a recepção; a possibilidade de atendimento dependerá da agenda do dia e não deve ser garantida pelo assistente virtual.",
            ),
            (
                "Unidade Sul",
                "A Unidade Sul está localizada na Rua das Flores, 220. No cadastro sintético, o Dr. Paulo Lima atende Pediatria nesta unidade. As informações de profissionais e convênios podem mudar e devem ser consultadas na listagem atual do sistema.",
                "Pessoas com necessidade de acessibilidade podem informar essa condição durante o contato para receber orientação sobre chegada e apoio. Dados sensíveis devem ser solicitados apenas quando indispensáveis ao atendimento.",
            ),
            (
                "Canais e limites do assistente",
                "O chat oferece informações administrativas, consulta de catálogo, disponibilidade e apoio a agendamentos. Ele não substitui avaliação médica e não deve ser usado para emergências. Dúvidas sobre sintomas, diagnóstico ou tratamento precisam ser direcionadas a um profissional de saúde.",
                "Quando uma informação institucional não estiver na base aprovada, a assistente deve dizer que não encontrou confirmação e indicar a recepção. É preferível reconhecer uma lacuna a apresentar uma resposta provável como se fosse oficial.",
            ),
        ),
    },
    {
        "filename": "04_convenios_autorizacoes_e_reembolso.pdf",
        "title": "Convênios, autorizações e reembolso",
        "subtitle": "Orientações administrativas para atendimento particular e conveniado",
        "sections": (
            (
                "Convênios cadastrados",
                "No ambiente sintético, a Clínica Alyvo possui cadastro dos convênios UNIMED e Vida+. A Dra. Marina Costa aparece vinculada a UNIMED e Vida+, enquanto o Dr. Paulo Lima aparece vinculado a UNIMED. A presença no cadastro não substitui a confirmação de cobertura do plano específico do paciente.",
                "Planos, produtos, redes e regras de elegibilidade variam. Antes do atendimento, o paciente deve confirmar com a operadora se o profissional, a unidade e o procedimento fazem parte da rede do seu contrato.",
            ),
            (
                "Autorização prévia",
                "Alguns procedimentos podem exigir guia, senha ou autorização prévia. A clínica pode orientar quais documentos normalmente são solicitados, mas a aprovação é responsabilidade da operadora. Não prometa autorização nem prazo quando essa informação não vier de uma resposta oficial.",
                "Se a autorização estiver pendente, explique o status e o próximo passo. Evite linguagem acusatória. Uma forma adequada é: 'A autorização ainda não foi confirmada pela operadora. Você pode acompanhar pelo canal do seu plano ou falar com a recepção'.",
            ),
            (
                "Atendimento particular e reembolso",
                "Quando não houver cobertura direta, o paciente pode optar por atendimento particular conforme os valores informados pela recepção. A possibilidade de reembolso depende do contrato e deve ser verificada com a operadora antes da consulta.",
                "Documentos para reembolso, como recibo ou relatório administrativo, seguem o processo da clínica. O assistente não deve estimar percentual, prazo ou valor de reembolso sem evidência específica e atualizada.",
            ),
            (
                "Comunicação segura",
                "Nunca solicite foto completa de cartão do convênio em um canal não autorizado. Quando a identificação for necessária, use o fluxo seguro da plataforma e colete apenas os campos indispensáveis. Informações de saúde e identificação devem receber proteção reforçada.",
            ),
        ),
    },
    {
        "filename": "05_exames_preparo_e_resultados.pdf",
        "title": "Exames, preparo e entrega de resultados",
        "subtitle": "Orientações gerais do ambiente sintético Alyvo",
        "sections": (
            (
                "Hemograma",
                "O hemograma está disponível nas unidades Centro e Sul no ambiente de demonstração. O cadastro informa que jejum não é obrigatório. Orientações individuais dadas pelo profissional solicitante devem prevalecer, especialmente quando o hemograma fizer parte de uma coleta com outros exames.",
                "Leve o pedido médico quando exigido, documento de identificação e informações do convênio. A necessidade de autorização depende do plano e deve ser confirmada antes da coleta.",
            ),
            (
                "Prazo de processamento",
                "O prazo institucional sintético para resultado de hemograma é de até dois dias úteis. O prazo começa após a coleta adequada e pode variar em situações técnicas, necessidade de repetição, feriados ou envio a laboratório de apoio.",
                "A assistente deve apresentar o prazo como estimativa institucional, nunca como garantia absoluta. Se o resultado ultrapassar o período informado, oriente o paciente a procurar a recepção ou o canal de resultados.",
            ),
            (
                "Preparo e segurança",
                "Não invente preparo com base apenas no nome do exame. Quando a base não contiver orientação aprovada, diga que o preparo precisa ser confirmado. Para crianças, gestantes, idosos ou pessoas com condições específicas, recomenda-se conferir a orientação do profissional solicitante.",
                "Medicamentos não devem ser suspensos por orientação do assistente administrativo. Qualquer mudança de medicação, dieta ou rotina clínica deve ser discutida com um profissional habilitado.",
            ),
            (
                "Interpretação de resultados",
                "A entrega do laudo não inclui interpretação clínica pelo assistente virtual. Valores de referência podem variar, e um resultado isolado não permite diagnóstico. O paciente deve conversar com o profissional que solicitou o exame ou com outro profissional habilitado.",
                "Se a pessoa relatar piora importante ou sinais de emergência, priorize a orientação de procurar atendimento imediato. Não use o resultado de exame para sugerir diagnóstico, risco ou tratamento.",
            ),
        ),
    },
    {
        "filename": "06_privacidade_lgpd_e_direitos.pdf",
        "title": "Privacidade, LGPD e direitos do paciente",
        "subtitle": "Tratamento responsável de dados pessoais e dados de saúde",
        "sections": (
            (
                "Princípios de proteção de dados",
                "A clínica deve tratar dados pessoais com finalidade definida, necessidade, transparência, segurança e prevenção. Dados de saúde são dados pessoais sensíveis e exigem proteção reforçada. O acesso deve ser limitado às pessoas e sistemas que precisam da informação para uma finalidade legítima.",
                "O assistente coleta somente o necessário para cada operação. Consultas públicas de catálogo e disponibilidade não exigem identificação. Acesso a consultas pessoais, agendamento e cancelamento utilizam o fluxo seguro de identificação.",
            ),
            (
                "Direitos do titular",
                "O paciente pode solicitar informações sobre o tratamento dos seus dados e exercer direitos previstos na legislação aplicável, como confirmação, acesso, correção e revisão de determinadas decisões. Cada pedido deve ser encaminhado ao canal responsável e pode exigir validação de identidade.",
                "Pedidos de exclusão ou portabilidade precisam considerar obrigações legais e regulatórias de guarda. A assistente não deve prometer eliminação imediata antes da análise responsável.",
            ),
            (
                "Segurança e compartilhamento",
                "Dados não devem ser expostos em logs, exemplos, documentos públicos ou respostas destinadas a outra pessoa. Compartilhamentos com operadoras, laboratórios ou fornecedores devem ter finalidade legítima, acesso controlado e medidas de segurança compatíveis com o risco.",
                "Tokens, senhas e credenciais reais nunca devem aparecer em documentação ou exemplos. Incidentes suspeitos precisam ser registrados e encaminhados ao processo de resposta da clínica, sem ocultar evidências.",
            ),
            (
                "Comunicação transparente",
                "Ao solicitar um dado, explique de forma simples por que ele é necessário. Evite textos jurídicos longos durante uma tarefa operacional, mas mantenha disponível a política completa. Se a pessoa tiver uma dúvida que não possa ser respondida com segurança, encaminhe ao responsável por privacidade.",
            ),
        ),
    },
    {
        "filename": "07_acessibilidade_inclusao_e_atendimento_prioritario.pdf",
        "title": "Acessibilidade, inclusão e atendimento prioritário",
        "subtitle": "Orientações para uma experiência respeitosa e sem barreiras",
        "sections": (
            (
                "Comunicação inclusiva",
                "Use linguagem simples, respeitosa e direta. Não presuma limitações, diagnósticos, gênero, vínculos familiares ou capacidade de decisão. Pergunte como a pessoa prefere ser chamada e qual forma de comunicação funciona melhor para ela.",
                "Evite falar apenas com o acompanhante quando o paciente puder participar da conversa. Dê tempo para respostas, faça uma pergunta por vez e ofereça alternativas de formato quando disponíveis.",
            ),
            (
                "Pessoas com deficiência",
                "Quando houver uma necessidade de acessibilidade, confirme o apoio desejado sem exigir detalhes desnecessários. A pessoa pode informar necessidade de mobilidade, apoio visual, comunicação escrita ou presença de acompanhante. Registre somente o que for necessário para organizar o atendimento.",
                "Não prometa recursos que não estejam confirmados. Se a base não trouxer informação sobre estrutura física ou tecnologia assistiva, encaminhe a pergunta à recepção e diga claramente que a confirmação está pendente.",
            ),
            (
                "Crianças, idosos e acompanhantes",
                "Atendimentos pediátricos devem considerar o responsável legal e, ao mesmo tempo, acolher a criança de acordo com sua idade. Pessoas idosas devem receber comunicação clara, sem infantilização. A presença de acompanhante segue regras de segurança, privacidade e capacidade do ambiente.",
                "Em operações que envolvam dados pessoais ou decisões do paciente, confirme a autorização adequada. Não compartilhe informações com um acompanhante apenas porque ele participa da conversa.",
            ),
            (
                "Atendimento prioritário e respeito",
                "Situações de prioridade devem ser tratadas com discrição. A prioridade não autoriza exposição da condição da pessoa. Em caso de conflito ou dúvida operacional, explique que a recepção fará a orientação conforme as regras aplicáveis.",
                "Comportamentos discriminatórios não são aceitáveis. Nome social, identidade, raça, religião, deficiência, idade, orientação sexual e condição socioeconômica devem ser respeitados. O foco do atendimento é remover barreiras e garantir informação segura para todas as pessoas.",
            ),
        ),
    },
)


def draw_page(canvas, document):
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, A4[1] - 18 * mm, A4[0], 18 * mm, fill=1, stroke=0)
    canvas.setFillColor(BRAND)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(22 * mm, A4[1] - 11.5 * mm, "ALYVO  |  CONHECIMENTO INSTITUCIONAL")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 22 * mm, 12 * mm, f"Página {document.page}")
    canvas.drawString(
        22 * mm,
        12 * mm,
        "Conteúdo sintético para demonstração - validar antes de produção",
    )
    canvas.restoreState()


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=10 * mm,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=13 * mm,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=BRAND,
            spaceBefore=5 * mm,
            spaceAfter=3 * mm,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10.3,
            leading=15.2,
            textColor=INK,
            spaceAfter=3.5 * mm,
        ),
        "tag": ParagraphStyle(
            "Tag",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
            backColor=BRAND,
            borderPadding=(4, 7, 4, 7),
            alignment=TA_CENTER,
            spaceAfter=10 * mm,
        ),
    }


def build_document(spec: dict) -> Path:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / spec["filename"]
    style = styles()
    story = [
        Spacer(1, 8 * mm),
        Paragraph(spec["title"], style["title"]),
        Paragraph(spec["subtitle"], style["subtitle"]),
        Paragraph("VERSÃO 1.0  |  NOVEMBRO DE 2026", style["tag"]),
    ]
    for heading, *paragraphs in spec["sections"]:
        story.append(Paragraph(heading, style["section"]))
        story.extend(Paragraph(paragraph, style["body"]) for paragraph in paragraphs)
    document = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=27 * mm,
        bottomMargin=22 * mm,
        title=spec["title"],
        author="Alyvo Engineering",
        subject="Base sintética de conhecimento institucional",
    )
    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return target


def main() -> None:
    for document in DOCUMENTS:
        print(build_document(document))


if __name__ == "__main__":
    main()
