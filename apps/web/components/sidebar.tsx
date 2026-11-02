"use client";

import { Activity, BookOpen, Building2, CalendarDays, ChevronLeft, CreditCard, LayoutDashboard, LogOut, Stethoscope, TestTube2, Users } from "lucide-react";
import Link from "next/link";
import { Brand } from "./brand";

const groups = [
  {
    label: "Operação",
    items: [
      ["/backoffice", "Visão geral", LayoutDashboard],
      ["/backoffice/agenda", "Agenda", CalendarDays],
      ["/backoffice/pacientes", "Pacientes", Users],
    ],
  },
  {
    label: "Cadastros",
    items: [
      ["/backoffice/medicos", "Médicos", Stethoscope],
      ["/backoffice/especialidades", "Especialidades", Activity],
      ["/backoffice/convenios", "Convênios", CreditCard],
      ["/backoffice/exames", "Exames", TestTube2],
      ["/backoffice/unidades", "Unidades", Building2],
    ],
  },
  {
    label: "Inteligência",
    items: [["/backoffice/conhecimento", "Conhecimento", BookOpen]],
  },
] as const;

export function Sidebar({ active }: { active: string }) {
  return (
    <aside className="backoffice-sidebar">
      <div className="sidebar-brand"><Brand /><Link href="/" aria-label="Voltar ao site"><ChevronLeft /></Link></div>
      <nav aria-label="Navegação do backoffice">
        {groups.map((group) => (
          <section key={group.label}>
            <p className="nav-label">{group.label}</p>
            {group.items.map(([href, label, Icon]) => (
              <Link href={href} key={href} className={active === label ? "active" : ""}>
                <Icon /> <span>{label}</span>
              </Link>
            ))}
          </section>
        ))}
      </nav>
      <Link className="sidebar-logout" href="/backoffice/login" onClick={() => window.localStorage.removeItem("alyvo_staff_access_token")}>
        <LogOut /> Sair
      </Link>
    </aside>
  );
}
