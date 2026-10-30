"use client";

import { CalendarDays, Check, Clock3, MapPin, ShieldCheck, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import type { Slot } from "@alyvo/contracts";
import { Brand } from "@/components/brand";
import { accessToken, cancelAppointment, createAppointment, getAvailability, listMyAppointments, registerPatient, startPatientAuth, verifyPatient } from "@/lib/api";

type Appointment = { id: string; doctor_id: string; starts_at: string; status: string; reason: string };

export default function SchedulePage() {
  const [cpf, setCpf] = useState("123.456.789-09");
  const [code, setCode] = useState("");
  const [email, setEmail] = useState("juliana.demo@alyvo.local");
  const [name, setName] = useState("");
  const [registrationToken, setRegistrationToken] = useState("");
  const [authStep, setAuthStep] = useState<"cpf" | "code" | "register" | "ready">("cpf");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [selected, setSelected] = useState<Slot | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const [appointments, setAppointments] = useState<Appointment[]>([]);

  async function loadSlots() {
    const [items, mine] = await Promise.all([getAvailability(), listMyAppointments()]);
    setSlots(items);
    setSelected(items[0] ?? null);
    setAppointments(mine);
  }

  useEffect(() => {
    if (accessToken()) {
      queueMicrotask(() => {
        setAuthStep("ready");
        void loadSlots();
      });
    }
  }, []);

  async function sendCode() {
    setMessage("");
    await startPatientAuth(cpf, email);
    setAuthStep("code");
  }

  async function verify() {
    setMessage("");
    const result = await verifyPatient(cpf, code);
    if (result.status === "registration_required") {
      setRegistrationToken(result.registration_token);
      setAuthStep("register");
      return;
    }
    setAuthStep("ready");
    await loadSlots();
  }

  async function register() {
    await registerPatient({ cpf, name, email, registration_token: registrationToken });
    setAuthStep("ready");
    await loadSlots();
  }

  async function cancel(id: string) {
    if (!window.confirm("Confirma o cancelamento deste agendamento?")) return;
    await cancelAppointment(id);
    await loadSlots();
  }

  async function confirm() {
    if (!selected) return;
    setMessage("");
    try {
      await createAppointment(selected);
      setConfirmed(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível agendar");
    }
  }

  return (
    <main>
      <header className="app-header schedule-header"><Brand /><nav><Link href="/">Início</Link><Link className="active" href="/agendar">Consultas</Link><Link href="/chat">Assistente</Link></nav></header>
      <section className="schedule-page">
        <div className="page-heading"><p className="eyebrow">Agenda operacional</p><h1>{confirmed ? "Consulta confirmada" : "Agendar consulta"}</h1><p>Os horários vêm do PostgreSQL e a reserva só acontece após confirmação.</p></div>

        {authStep !== "ready" && <section className="panel auth-panel">
          <ShieldCheck /><h2>Confirme sua identidade</h2>
          {authStep === "cpf" && <><label>CPF<input value={cpf} onChange={(event) => setCpf(event.target.value)} /></label><label>E-mail<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label><button className="button button-primary" onClick={sendCode}>Enviar código</button></>}
          {authStep === "code" && <><label>Código temporário<input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" /></label><button className="button button-primary" onClick={verify}>Confirmar código</button></>}
          {authStep === "register" && <><p>Primeiro acesso. Complete o cadastro sintético.</p><label>Nome<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>E-mail<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label><button className="button button-primary" onClick={register} disabled={!name || !email}>Cadastrar e continuar</button></>}
          {message && <p role="alert" className="error-text">{message}</p>}
        </section>}

        {authStep === "ready" && confirmed && selected && <div className="success-state"><span><Check /></span><h2>Consulta registrada.</h2><p>{selected.doctor.name}, em {new Date(selected.starts_at).toLocaleString("pt-BR")}, na {selected.unit.name}.</p><Link href="/chat" className="button button-primary">Voltar ao assistente</Link></div>}

        {authStep === "ready" && !confirmed && <div className="schedule-grid">
          <article className="panel professional-panel"><header>Horários disponíveis</header>{slots.length === 0 ? <p>Nenhum horário disponível.</p> : <div className="time-column">{slots.map((slot) => <button key={slot.id} className={selected?.id === slot.id ? "selected" : ""} onClick={() => setSelected(slot)}><span><strong>{new Date(slot.starts_at).toLocaleDateString("pt-BR")}</strong> · {new Date(slot.starts_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</span>{selected?.id === slot.id && <Check />}</button>)}</div>}</article>
          {selected && <aside className="panel summary-panel"><header>Resumo da consulta</header><dl><div><dt><UserRound /> Profissional</dt><dd>{selected.doctor.name}<small>{selected.doctor.crm}</small></dd></div><div><dt><CalendarDays /> Data</dt><dd>{new Date(selected.starts_at).toLocaleDateString("pt-BR")}</dd></div><div><dt><Clock3 /> Horário</dt><dd>{new Date(selected.starts_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</dd></div><div><dt><MapPin /> Unidade</dt><dd>{selected.unit.name}<small>{selected.unit.address}</small></dd></div></dl><div className="confirmation-note"><Check size={16} /> Confirme para criar a reserva.</div><button className="button button-primary full" onClick={confirm}>Confirmar agendamento</button>{message && <p role="alert" className="error-text">{message}</p>}</aside>}
        </div>}
        {authStep === "ready" && appointments.length > 0 && <section className="panel appointment-list"><header>Meus agendamentos</header>{appointments.map((item) => <article key={item.id}><div><strong>{item.reason}</strong><small>{new Date(item.starts_at).toLocaleString("pt-BR")} · {item.status}</small></div>{item.status === "confirmed" && <button className="button button-secondary" onClick={() => void cancel(item.id)}>Cancelar</button>}</article>)}</section>}
      </section>
    </main>
  );
}
