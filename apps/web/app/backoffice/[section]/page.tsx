import { FileText, MessageSquareText, Search, Settings, UserRound } from "lucide-react";
import { Sidebar } from "@/components/sidebar";

const content: Record<string, { title: string; description: string; icon: typeof UserRound; rows: string[][] }> = {
  pacientes: { title: "Pacientes", description: "Cadastros sintéticos isolados por clínica.", icon: UserRound, rows: [["Juliana Silva", "juliana.demo@alyvo.local", "Cadastro confirmado"], ["Mariana Alves", "mariana.demo@alyvo.local", "Documento pendente"], ["Fernanda Lima", "fernanda.demo@alyvo.local", "Cadastro confirmado"]] },
  tickets: { title: "Tickets", description: "Solicitações administrativas originadas pelo assistente.", icon: MessageSquareText, rows: [["Integração com convênio", "Aberto", "Hoje, 08:45"], ["Documento necessário", "Em atendimento", "Ontem, 16:10"]] },
  configuracoes: { title: "Configurações", description: "Políticas da clínica e integrações locais.", icon: Settings, rows: [["Fuso horário", "America/Sao_Paulo", "Ativo"], ["Modelo local", "qwen3:8b via Ollama", "Fallback mock"], ["OCR", "PaddleOCR", "Fallback mock"]] },
};

export default async function GenericBackofficePage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;
  const page = content[section] ?? { title: "Módulo", description: "Área operacional da demonstração.", icon: FileText, rows: [] };
  const Icon = page.icon;
  return <main className="backoffice-shell"><Sidebar active={page.title} /><section className="backoffice-main list-page"><div className="page-heading"><p className="eyebrow">Back office</p><h1>{page.title}</h1><p>{page.description}</p></div><div className="list-toolbar"><label><Search /><input aria-label={`Buscar em ${page.title}`} placeholder={`Buscar em ${page.title.toLowerCase()}...`} /></label><button className="button button-primary"><Icon /> Nova entrada</button></div><div className="data-list">{page.rows.map((row) => <article key={row[0]}><span className="avatar"><Icon /></span><div><strong>{row[0]}</strong><small>{row[1]}</small></div><em>{row[2]}</em></article>)}</div></section></main>;
}

