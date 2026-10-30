"use client";

import { CalendarDays, FileText, MessageSquareText, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { backofficeGet } from "@/lib/api";

type Dashboard = { appointments: number; patients: number; documents_pending: number; tickets_open: number };

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { void backofficeGet("/dashboard").then(setData).catch(() => setError("Entre com uma conta da equipe para continuar.")); }, []);
  return <main className="backoffice-shell"><Sidebar active="Visão geral" /><section className="backoffice-main dashboard-page"><div className="page-heading"><p className="eyebrow">Operação em tempo real</p><h1>Visão geral da clínica</h1><p>Dados carregados do banco operacional e isolados por clínica.</p></div>{error && <div className="info-box"><p>{error}</p><Link className="button button-primary" href="/backoffice/login">Entrar</Link></div>}{data && <><div className="operational-summary"><article><CalendarDays /><span><strong>{data.appointments}</strong> consultas</span></article><article><Users /><span><strong>{data.patients}</strong> pacientes</span></article><article><FileText /><span><strong>{data.documents_pending}</strong> documentos em revisão</span></article><article><MessageSquareText /><span><strong>{data.tickets_open}</strong> tickets abertos</span></article></div><section className="dashboard-focus"><div><p className="eyebrow">Próxima ação</p><h2>Resolva as pendências da operação.</h2><p>Documentos e tickets permanecem na fila até uma ação da equipe.</p><div className="button-row"><Link className="button button-primary" href="/backoffice/documentos">Ver documentos</Link><Link className="button button-secondary" href="/backoffice/tickets">Ver tickets</Link></div></div></section></>}</section></main>;
}
