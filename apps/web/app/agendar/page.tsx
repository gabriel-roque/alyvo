"use client";

import { Building2, CalendarDays, Check, ChevronLeft, ChevronRight, Clock3, CreditCard, MapPin, UserRound } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Brand } from "@/components/brand";

const times = ["09:00", "10:30", "14:00", "16:30"];

export default function SchedulePage() {
  const [time, setTime] = useState("10:30");
  const [confirmed, setConfirmed] = useState(false);
  const days = useMemo(() => Array.from({ length: 30 }, (_, index) => index + 1), []);

  return (
    <main>
      <header className="app-header schedule-header"><Brand /><nav><Link href="/">Início</Link><Link className="active" href="/agendar">Consultas</Link><Link href="/chat">Assistente</Link></nav><div className="profile"><span className="avatar">JS</span><span><strong>Juliana Silva</strong><small>Paciente demo</small></span></div></header>
      <section className="schedule-page">
        <div className="page-heading"><p className="eyebrow">Agenda operacional</p><h1>{confirmed ? "Consulta confirmada" : "Agendar consulta"}</h1><p>{confirmed ? "A reserva foi registrada na agenda da Clínica Alyvo." : "Escolha o profissional e um horário disponível. A reserva só acontece após sua confirmação."}</p></div>
        {confirmed ? (
          <div className="success-state"><span><Check /></span><h2>Tudo certo, Juliana.</h2><p>Cardiologia com Dra. Marina Lopes em 12 de novembro, às {time}, na Unidade Centro.</p><div className="button-row"><Link href="/chat" className="button button-primary">Voltar ao assistente</Link><button className="button button-secondary" onClick={() => setConfirmed(false)}>Ver resumo</button></div></div>
        ) : (
          <>
            <ol className="stepper"><li className="done"><span><Check /></span><div><strong>Especialidade</strong><small>Cardiologia</small></div></li><li className="done"><span><Check /></span><div><strong>Profissional</strong><small>Dra. Marina Lopes</small></div></li><li className="current"><span>3</span><div><strong>Horário</strong><small>Selecione uma opção</small></div></li><li><span>4</span><div><strong>Confirmar</strong><small>Revise os dados</small></div></li></ol>
            <div className="schedule-grid">
              <article className="panel professional-panel"><header>Profissional selecionado</header><div className="selected-doctor"><div className="doctor-monogram">ML</div><div><h2>Dra. Marina Lopes</h2><p>Cardiologia</p><small>CRM 123456 SP</small></div></div><dl><div><dt><MapPin /> Unidade</dt><dd>Unidade Centro<small>Rua das Acácias, 320</small></dd></div><div><dt><CreditCard /> Convênio</dt><dd>Vida+</dd></div><div><dt><Check /> Avaliação</dt><dd>4,9 <small>128 avaliações sintéticas</small></dd></div></dl></article>
              <article className="panel calendar-panel"><header>Selecione o dia e horário</header><div className="calendar-toolbar"><button aria-label="Mês anterior"><ChevronLeft /></button><strong>Novembro 2026</strong><button aria-label="Próximo mês"><ChevronRight /></button></div><div className="calendar-week"><span>SEG</span><span>TER</span><span>QUA</span><span>QUI</span><span>SEX</span><span>SÁB</span><span>DOM</span></div><div className="calendar-days">{days.map((day) => <button className={day === 12 ? "selected" : ""} key={day}>{day}</button>)}</div><div className="time-column"><p className="nav-label">Horários disponíveis · quinta, 12</p>{times.map((item) => <button className={time === item ? "selected" : ""} onClick={() => setTime(item)} key={item}><span>{item}</span>{time === item ? <Check /> : <i />} </button>)}</div></article>
              <aside className="panel summary-panel"><header>Resumo da consulta</header><dl><div><dt><CalendarDays /> Data</dt><dd>Quinta-feira, 12 de novembro</dd></div><div><dt><Clock3 /> Horário</dt><dd>{time}</dd></div><div><dt><Building2 /> Unidade</dt><dd>Unidade Centro<small>Rua das Acácias, 320</small></dd></div><div><dt><UserRound /> Paciente</dt><dd>Juliana Silva<small>Convênio Vida+</small></dd></div></dl><div className="confirmation-note"><Check size={16} /> Você confirma que os dados acima estão corretos?</div><button className="button button-primary full" onClick={() => setConfirmed(true)}>Confirmar agendamento <ChevronRight /></button></aside>
            </div>
          </>
        )}
      </section>
    </main>
  );
}

