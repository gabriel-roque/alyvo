import {
  BookOpen,
  CalendarDays,
  FileText,
  LayoutDashboard,
  LogOut,
  MessageSquareText,
  Settings,
  Users,
} from "lucide-react";
import Link from "next/link";
import { Brand } from "./brand";

const items = [
  ["/backoffice", "Visão geral", LayoutDashboard],
  ["/backoffice/agenda", "Agenda", CalendarDays],
  ["/backoffice/pacientes", "Pacientes", Users],
  ["/documentos/revisao", "Documentos", FileText],
  ["/backoffice/tickets", "Tickets", MessageSquareText],
  ["/backoffice/conhecimento", "Conhecimento", BookOpen],
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

