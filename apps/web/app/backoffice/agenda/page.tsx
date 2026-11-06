"use client";

import { Archive, CalendarDays, ChevronLeft, ChevronRight, Clock3, Plus, SlidersHorizontal, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  cancelAppointment as cancelAppointmentRequest,
  createAppointment,
  createAvailabilityBlock,
  createAvailabilityRule,
  listAgenda,
  listAvailabilityBlocks,
  listAvailabilityRules,
  listCatalog,
  listDoctors,
  listPatients,
  updateAppointment,
} from "@/features/backoffice/agenda/api";
import type { Appointment, AvailabilityBlock as Block, AvailabilityRule as Rule } from "@/lib/api";

type Option = { id: string; name: string };

function isoDay(value: Date) { return value.toISOString().slice(0, 10); }
function localInput(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export default function AgendaPage() {
  const [view, setView] = useState<"day" | "week">("day");
  const [cursor, setCursor] = useState(() => new Date());
  const [doctorId, setDoctorId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [items, setItems] = useState<Appointment[]>([]);
  const [doctors, setDoctors] = useState<Option[]>([]);
  const [units, setUnits] = useState<Option[]>([]);
  const [patients, setPatients] = useState<Option[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [panel, setPanel] = useState<"appointment" | "availability" | null>(null);
  const [editing, setEditing] = useState<Appointment | null>(null);
  const [appointment, setAppointment] = useState({ patient_id: "", doctor_id: "", starts_at: "", reason: "Consulta" });
  const [rule, setRule] = useState({ doctor_id: "", unit_id: "", weekday: 0, starts_at: "08:00", ends_at: "18:00", slot_minutes: 30 });
  const [block, setBlock] = useState({ doctor_id: "", starts_at: "", ends_at: "", reason: "Bloqueio administrativo" });
  const [saving, setSaving] = useState(false);

  const range = useMemo(() => {
    const start = new Date(cursor);
    if (view === "week") start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    const end = new Date(start);
    if (view === "week") end.setDate(end.getDate() + 6);
    return { start: isoDay(start), end: isoDay(end) };
  }, [cursor, view]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [agenda, doctorData, unitData, patientData, ruleData, blockData] = await Promise.all([
        listAgenda(range.start, range.end, doctorId || undefined, unitId || undefined),
        listDoctors("", false),
        listCatalog("units", "", false),
        listPatients(),
        listAvailabilityRules(),
        listAvailabilityBlocks(),
      ]);
      setItems(agenda.items);
      setDoctors(doctorData.items);
      setUnits(unitData.items);
      setPatients(patientData.items);
      setRules(ruleData.items);
      setBlocks(blockData.items);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao carregar a agenda."); }
    finally { setLoading(false); }
  }, [doctorId, range.end, range.start, unitId]);

  useEffect(() => { queueMicrotask(() => void load()); }, [load]);

  const days = useMemo(() => {
    const first = new Date(`${range.start}T12:00:00`);
    return Array.from({ length: view === "week" ? 7 : 1 }, (_, index) => { const day = new Date(first); day.setDate(day.getDate() + index); return day; });
  }, [range.start, view]);

  function move(direction: number) { const next = new Date(cursor); next.setDate(next.getDate() + direction * (view === "week" ? 7 : 1)); setCursor(next); }

  function openAppointment(item?: Appointment) {
    setEditing(item ?? null);
    setAppointment(item ? { patient_id: item.patient_id, doctor_id: item.doctor_id, starts_at: localInput(item.starts_at), reason: item.reason } : { patient_id: patients[0]?.id ?? "", doctor_id: doctors[0]?.id ?? "", starts_at: `${range.start}T09:00`, reason: "Consulta" });
    setPanel("appointment");
  }

  async function saveAppointment(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      const starts_at = new Date(appointment.starts_at).toISOString();
      if (editing) await updateAppointment(editing.id, { starts_at, reason: appointment.reason });
      else await createAppointment({ ...appointment, starts_at });
      setPanel(null); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Não foi possível salvar a consulta."); }
    finally { setSaving(false); }
  }

  async function cancelAppointment() {
    if (!editing) return;
    setSaving(true);
    try { await cancelAppointmentRequest(editing.id); setPanel(null); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Não foi possível cancelar."); }
    finally { setSaving(false); }
  }

  async function createRule(event: FormEvent) {
    event.preventDefault(); setSaving(true);
    try { await createAvailabilityRule({ ...rule, valid_from: null, valid_until: null, active: true }); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Não foi possível salvar a regra."); }
    finally { setSaving(false); }
  }

  async function createBlock(event: FormEvent) {
    event.preventDefault(); setSaving(true);
    try { await createAvailabilityBlock({ ...block, starts_at: new Date(block.starts_at).toISOString(), ends_at: new Date(block.ends_at).toISOString() }); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Não foi possível criar o bloqueio."); }
    finally { setSaving(false); }
  }

  return (
    <>
      <section className="agenda-page">
        <header className="resource-heading"><div><p className="eyebrow">Operação</p><h1>Agenda</h1><p>Consultas, disponibilidade e bloqueios em um só lugar.</p></div><div className="button-row"><button className="button button-secondary" onClick={() => setPanel("availability")}><SlidersHorizontal /> Disponibilidade</button><button className="button button-primary" onClick={() => openAppointment()}><Plus /> Nova consulta</button></div></header>
        <div className="agenda-toolbar">
          <div className="segmented"><button className={view === "day" ? "active" : ""} onClick={() => setView("day")}>Dia</button><button className={view === "week" ? "active" : ""} onClick={() => setView("week")}>Semana</button></div>
          <div className="date-navigator"><button aria-label="Período anterior" onClick={() => move(-1)}><ChevronLeft /></button><button onClick={() => setCursor(new Date())}><CalendarDays /> {view === "day" ? new Date(`${range.start}T12:00:00`).toLocaleDateString("pt-BR", { dateStyle: "long" }) : `${new Date(`${range.start}T12:00:00`).toLocaleDateString("pt-BR")} — ${new Date(`${range.end}T12:00:00`).toLocaleDateString("pt-BR")}`}</button><button aria-label="Próximo período" onClick={() => move(1)}><ChevronRight /></button></div>
          <select aria-label="Filtrar por médico" value={doctorId} onChange={(event) => setDoctorId(event.target.value)}><option value="">Todos os médicos</option>{doctors.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select>
          <select aria-label="Filtrar por unidade" value={unitId} onChange={(event) => setUnitId(event.target.value)}><option value="">Todas as unidades</option>{units.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select>
        </div>
        {error && <p className="error-text" role="alert">{error}</p>}
        {loading ? <div className="agenda-skeleton">{Array.from({ length: 12 }).map((_, index) => <i key={index} />)}</div> : (
          <div className="calendar-grid" style={{ "--day-count": days.length } as React.CSSProperties}>
            <div className="calendar-corner" />
            {days.map((day) => <header key={day.toISOString()}><small>{day.toLocaleDateString("pt-BR", { weekday: "short" })}</small><strong>{day.getDate()}</strong></header>)}
            {Array.from({ length: 11 }, (_, index) => index + 8).map((hour) => <div className="calendar-row" key={hour}><time>{String(hour).padStart(2, "0")}:00</time>{days.map((day) => { const dayItems = items.filter((item) => { const value = new Date(item.starts_at); return value.toDateString() === day.toDateString() && value.getHours() === hour; }); return <div className="calendar-cell" key={day.toISOString()}>{dayItems.map((item) => <button className={item.status === "cancelled" ? "calendar-event cancelled" : "calendar-event"} key={item.id} onClick={() => openAppointment(item)}><strong>{item.patient}</strong><span>{new Date(item.starts_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })} · {item.doctor}</span><small>{item.reason}</small></button>)}</div>; })}</div>)}
          </div>
        )}
        {!loading && !items.length && <div className="agenda-empty"><CalendarDays /><strong>Nenhuma consulta neste período</strong><p>Crie uma consulta ou ajuste os filtros.</p></div>}
      </section>

      {panel === "appointment" && <div className="dialog-backdrop"><aside className="side-dialog" role="dialog" aria-modal="true"><header><div><p className="eyebrow">{editing ? "Editar" : "Nova"}</p><h2>{editing ? "Detalhes da consulta" : "Nova consulta"}</h2></div><button className="icon-button" aria-label="Fechar" onClick={() => setPanel(null)}><X /></button></header><form className="drawer-form" onSubmit={saveAppointment}><label>Paciente<select value={appointment.patient_id} onChange={(event) => setAppointment({ ...appointment, patient_id: event.target.value })}>{patients.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Médico<select value={appointment.doctor_id} onChange={(event) => setAppointment({ ...appointment, doctor_id: event.target.value })}>{doctors.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Data e hora<input type="datetime-local" required value={appointment.starts_at} onChange={(event) => setAppointment({ ...appointment, starts_at: event.target.value })} /></label><label>Motivo<input value={appointment.reason} onChange={(event) => setAppointment({ ...appointment, reason: event.target.value })} /></label><footer>{editing && editing.status !== "cancelled" && <button type="button" className="button button-danger" disabled={saving} onClick={() => void cancelAppointment()}><Archive /> Cancelar consulta</button>}<button className="button button-primary" disabled={saving}>{saving ? "Salvando…" : "Salvar consulta"}</button></footer></form></aside></div>}

      {panel === "availability" && <div className="dialog-backdrop"><aside className="side-dialog wide" role="dialog" aria-modal="true"><header><div><p className="eyebrow">Agenda</p><h2>Disponibilidade</h2></div><button className="icon-button" aria-label="Fechar" onClick={() => setPanel(null)}><X /></button></header><div className="availability-tabs"><section><h3>Horários recorrentes</h3><form className="drawer-form compact-form" onSubmit={createRule}><label>Médico<select value={rule.doctor_id} onChange={(event) => setRule({ ...rule, doctor_id: event.target.value })}><option value="">Selecione</option>{doctors.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Unidade<select value={rule.unit_id} onChange={(event) => setRule({ ...rule, unit_id: event.target.value })}><option value="">Selecione</option>{units.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Dia da semana<select value={rule.weekday} onChange={(event) => setRule({ ...rule, weekday: Number(event.target.value) })}>{["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"].map((day, index) => <option value={index} key={day}>{day}</option>)}</select></label><div className="form-grid two"><label>Início<input type="time" value={rule.starts_at} onChange={(event) => setRule({ ...rule, starts_at: event.target.value })} /></label><label>Fim<input type="time" value={rule.ends_at} onChange={(event) => setRule({ ...rule, ends_at: event.target.value })} /></label></div><label>Duração do slot<select value={rule.slot_minutes} onChange={(event) => setRule({ ...rule, slot_minutes: Number(event.target.value) })}><option value="30">30 minutos</option><option value="45">45 minutos</option><option value="60">60 minutos</option></select></label><button className="button button-primary" disabled={saving}>Adicionar regra</button></form><div className="mini-list">{rules.filter((item) => item.active).map((item) => <article key={item.id}><Clock3 /><span><strong>{doctors.find((doctor) => doctor.id === item.doctor_id)?.name}</strong><small>{["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][item.weekday]} · {item.starts_at.slice(0, 5)}–{item.ends_at.slice(0, 5)} · {item.slot_minutes} min</small></span></article>)}</div></section><section><h3>Bloqueios pontuais</h3><form className="drawer-form compact-form" onSubmit={createBlock}><label>Médico<select value={block.doctor_id} onChange={(event) => setBlock({ ...block, doctor_id: event.target.value })}><option value="">Selecione</option>{doctors.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Início<input type="datetime-local" value={block.starts_at} onChange={(event) => setBlock({ ...block, starts_at: event.target.value })} /></label><label>Fim<input type="datetime-local" value={block.ends_at} onChange={(event) => setBlock({ ...block, ends_at: event.target.value })} /></label><label>Motivo<input value={block.reason} onChange={(event) => setBlock({ ...block, reason: event.target.value })} /></label><button className="button button-primary" disabled={saving}>Criar bloqueio</button></form><div className="mini-list">{blocks.map((item) => <article key={item.id}><Archive /><span><strong>{doctors.find((doctor) => doctor.id === item.doctor_id)?.name}</strong><small>{new Date(item.starts_at).toLocaleString("pt-BR")} — {new Date(item.ends_at).toLocaleString("pt-BR")}</small></span></article>)}</div></section></div></aside></div>}
    </>
  );
}
