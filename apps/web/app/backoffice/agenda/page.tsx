"use client";

import { CalendarDays, Clock3, Users } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { backofficeGet } from "@/lib/api";

type Appointment = { id: string; doctor: string; patient: string; starts_at: string; ends_at: string; status: string };

export default function AgendaPage() {
  const [items, setItems] = useState<Appointment[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { void backofficeGet("/agenda").then((data) => setItems(data.items)).catch((reason) => setError(reason.message)); }, []);
  const grouped = useMemo(() => Object.entries(items.reduce<Record<string, Appointment[]>>((groups, item) => { const key = item.doctor || "Sem profissional"; groups[key] = [...(groups[key] ?? []), item]; return groups; }, {})), [items]);
  return <main className="backoffice-shell"><Sidebar active="Agenda" /><section className="backoffice-main agenda-page"><header className="agenda-heading"><div><p className="eyebrow">Operação</p><h1>Agenda</h1></div><div className="metric-line"><span><CalendarDays /> <strong>{items.length}</strong> consultas</span><span><Clock3 /> atualização em tempo real</span></div></header>{error && <p role="alert" className="error-text">{error}</p>}<div className="agenda-board dynamic-agenda">{grouped.map(([doctor, appointments]) => <section className="doctor-column" key={doctor}><header><span className="avatar"><Users /></span><div><strong>{doctor}</strong><small>{appointments?.length ?? 0} consultas</small></div></header><div>{appointments?.map((item) => <article className="agenda-card" key={item.id}><time>{new Date(item.starts_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</time><strong>{item.patient}</strong><small>{item.status}</small></article>)}</div></section>)}</div></section></main>;
}
