"use client";

import { BookOpenCheck, CalendarCheck2, CalendarDays, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { backofficeGet } from "@/lib/api";

type Dashboard = { appointments_today: number; confirmed_today: number; patients: number; knowledge_pending: number };

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { void backofficeGet("/dashboard").then((result) => setData(result as unknown as Dashboard)).catch(() => setError("Entre com uma conta da equipe para continuar.")); }, []);
  return (
    <main className="backoffice-shell">
      <Sidebar active="Visão geral" />
      <section className="backoffice-main dashboard-page">
        <header className="page-heading"><p className="eyebrow">Operação</p><h1>Visão geral</h1><p>O que precisa da sua atenção hoje.</p></header>
        {error && <div className="info-box"><p>{error}</p><Link className="button button-primary" href="/backoffice/login">Entrar</Link></div>}
        {!data && !error && <div className="metric-skeleton">{Array.from({ length: 4 }).map((_, index) => <i key={index} />)}</div>}
        {data && <>
          <div className="operational-summary">
            <article><CalendarDays /><span><strong>{data.appointments_today}</strong> consultas hoje</span></article>
            <article><CalendarCheck2 /><span><strong>{data.confirmed_today}</strong> confirmadas</span></article>
            <article><Users /><span><strong>{data.patients}</strong> pacientes</span></article>
            <article><BookOpenCheck /><span><strong>{data.knowledge_pending}</strong> revisões de conhecimento</span></article>
          </div>
          <section className="dashboard-focus">
            <div><p className="eyebrow">Próxima ação</p><h2>Organize a operação sem perder contexto.</h2><p>Acompanhe a agenda ou revise o conhecimento que alimenta a assistente.</p><div className="button-row"><Link className="button button-primary" href="/backoffice/agenda">Abrir agenda</Link><Link className="button button-secondary" href="/backoffice/conhecimento">Revisar conhecimento</Link></div></div>
          </section>
        </>}
      </section>
    </main>
  );
}
