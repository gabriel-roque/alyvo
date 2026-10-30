"use client";

import { CalendarDays, Clock3, Plus, Trash2, Users } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { apiFetch, backofficeGet } from "@/lib/api";

type Appointment = { id: string; doctor: string; patient: string; starts_at: string; ends_at: string; status: string };
type Doctor = { id: string; name: string; unit_id: string };
type Unit = { id: string; name: string };
type Block = { id: string; doctor_id: string; starts_at: string; ends_at: string; reason: string };

export default function AgendaPage() {
  const [items, setItems] = useState<Appointment[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [doctorId, setDoctorId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [day, setDay] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const query = new URLSearchParams();
    if (doctorId) query.set("doctor_id", doctorId);
    if (unitId) query.set("unit_id", unitId);
    if (day) query.set("day", day);
    const [agenda, doctorData, unitData, blockData] = await Promise.all([backofficeGet(`/agenda?${query}`), backofficeGet("/doctors"), backofficeGet("/catalog/units"), backofficeGet("/availability-blocks")]);
    setItems(agenda.items); setDoctors(doctorData.items); setUnits(unitData.items); setBlocks(blockData.items);
  }, [day, doctorId, unitId]);
  useEffect(() => { queueMicrotask(() => void load().catch((reason) => setError(reason.message))); }, [load]);

  async function createBlock(event: FormEvent) {
    event.preventDefault();
    const response = await apiFetch("/backoffice/availability-blocks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ doctor_id: doctorId || doctors[0]?.id, starts_at: startsAt, ends_at: endsAt, reason: "Bloqueio administrativo" }) });
    if (!response.ok) { setError((await response.json()).detail ?? "Falha ao bloquear"); return; }
    setStartsAt(""); setEndsAt(""); await load();
  }

  async function removeBlock(id: string) { await apiFetch(`/backoffice/availability-blocks/${id}`, { method: "DELETE" }); await load(); }

  const grouped = useMemo(() => Object.entries(items.reduce<Record<string, Appointment[]>>((groups, item) => { const key = item.doctor || "Sem profissional"; groups[key] = [...(groups[key] ?? []), item]; return groups; }, {})), [items]);
  return <main className="backoffice-shell"><Sidebar active="Agenda" /><section className="backoffice-main agenda-page"><header className="agenda-heading"><div><p className="eyebrow">Operação</p><h1>Agenda e bloqueios</h1></div><div className="metric-line"><span><CalendarDays /> <strong>{items.length}</strong> consultas</span><span><Clock3 /> atualização em tempo real</span></div></header>
    <section className="panel inline-form agenda-admin"><label>Data<input type="date" value={day} onChange={(event) => setDay(event.target.value)} /></label><label>Profissional<select value={doctorId} onChange={(event) => setDoctorId(event.target.value)}><option value="">Todos</option>{doctors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Unidade<select value={unitId} onChange={(event) => setUnitId(event.target.value)}><option value="">Todas</option>{units.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></section>
    <form className="panel inline-form agenda-admin" onSubmit={createBlock}><label>Início<input type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} required /></label><label>Fim<input type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} required /></label><button className="button button-primary"><Plus /> Criar bloqueio</button></form>
    {blocks.length > 0 && <div className="panel block-list">{blocks.map((block) => <article key={block.id}><span><strong>{doctors.find((item) => item.id === block.doctor_id)?.name}</strong><small>{new Date(block.starts_at).toLocaleString("pt-BR")} — {new Date(block.ends_at).toLocaleString("pt-BR")}</small></span><button aria-label="Excluir bloqueio" onClick={() => void removeBlock(block.id)}><Trash2 /></button></article>)}</div>}
    {error && <p role="alert" className="error-text">{error}</p>}<div className="agenda-board dynamic-agenda">{grouped.map(([doctor, appointments]) => <section className="doctor-column" key={doctor}><header><span className="avatar"><Users /></span><div><strong>{doctor}</strong><small>{appointments?.length ?? 0} consultas</small></div></header><div>{appointments?.map((item) => <article className="agenda-card" key={item.id}><time>{new Date(item.starts_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</time><strong>{item.patient}</strong><small>{item.status}</small></article>)}</div></section>)}</div>
  </section></main>;
}
