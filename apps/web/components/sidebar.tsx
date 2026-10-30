import {
  BookOpen,
  Activity,
  Building2,
  CalendarDays,
  FileText,
  LayoutDashboard,
  LogOut,
  MessageSquareText,
  Settings,
  Stethoscope,
  Network,
  Users,
} from "lucide-react";
import Link from "next/link";
import { Brand } from "./brand";

const items = [
  ["/backoffice", "Visão geral", LayoutDashboard],
  ["/backoffice/agenda", "Agenda", CalendarDays],
  ["/backoffice/agendamentos", "Agendamentos", CalendarDays],
  ["/backoffice/pacientes", "Pacientes", Users],
  ["/backoffice/documentos", "Documentos", FileText],
  ["/backoffice/tickets", "Tickets", MessageSquareText],
  ["/backoffice/medicos", "Médicos", Stethoscope],
  ["/backoffice/especialidades", "Especialidades", Activity],
  ["/backoffice/convenios", "Convênios", FileText],
  ["/backoffice/unidades", "Unidades", Building2],
  ["/backoffice/exames", "Exames", Activity],
  ["/backoffice/servicos", "Serviços", Settings],
  ["/backoffice/conhecimento", "Conhecimento", BookOpen],
  ["/backoffice/grafo", "Grafo", Network],
  ["/backoffice/auditoria", "Auditoria", FileText],
  ["/backoffice/configuracoes", "Configurações", Settings],
] as const;

export function Sidebar({ active }: { active: string }) {
  return (
    <aside className="sidebar">
      <Brand />
      <nav aria-label="Back office">
        {items.map(([href, label, Icon]) => (
          <Link href={href} key={href} className={active === label ? "active" : ""}>
            <Icon size={20} aria-hidden="true" />
            {label}
          </Link>
        ))}
      </nav>
      <div className="sidebar-profile">
        <span className="avatar">CL</span>
        <span><strong>Clara Lima</strong><small>Recepção</small></span>
        <LogOut size={18} aria-label="Sair" />
      </div>
    </aside>
  );
}

