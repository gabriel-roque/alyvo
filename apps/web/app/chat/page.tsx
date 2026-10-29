"use client";

import { BookOpen, CalendarDays, ChevronDown, FileText, MapPin, Paperclip, Send, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";
import type { Citation } from "@alyvo/contracts";
import { Brand } from "@/components/brand";
import { createChatSession, demoDoctors, sendMessage } from "@/lib/api";

type Message = { role: "user" | "assistant"; content: string; citations?: Citation[]; intent?: string };

const firstAnswer: Message = {
  role: "assistant",
  content: "Olá, sou a assistente administrativa da Alyvo. Posso localizar profissionais, explicar convênios e documentos ou ajudar com um agendamento. Como posso ajudar?",
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([firstAnswer]);
  const [text, setText] = useState("");
  const [session, setSession] = useState<string>();
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = text.trim();
    if (!content || loading) return;
    setMessages((items) => [...items, { role: "user", content }]);
    setText("");
    setLoading(true);
    try {
      const sessionId = session ?? (await createChatSession());
      setSession(sessionId);
      const response = await sendMessage(sessionId, content);
      setMessages((items) => [...items, { role: "assistant", content: response.answer, citations: response.citations, intent: response.intent }]);
    } catch {
      const doctorSummary = demoDoctors.slice(0, 2).map((doctor) => `${doctor.name}, ${doctor.specialty}, ${doctor.unit}, convênio ${doctor.insurers.join(" e ")}`).join("; ");
      setMessages((items) => [...items, {
        role: "assistant",
        content: content.toLowerCase().includes("agend") ? "Para agendar, escolha um horário real da agenda e confirme o resumo. A autenticação por CPF e código temporário será solicitada antes da reserva." : `Encontrei profissionais na base aprovada: ${doctorSummary}.`,
        intent: content.toLowerCase().includes("agend") ? "schedule" : "knowledge",
        citations: [{ title: "Cadastro aprovado de profissionais", source: "Grafo da clínica", excerpt: "Relações entre profissional, especialidade, convênio e unidade." }],
      }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="chat-shell">
      <header className="app-header">
        <Brand />
        <nav><Link className="active" href="/chat">Assistente</Link><Link href="/agendar">Agenda</Link><Link href="/backoffice/pacientes">Pacientes</Link><Link href="/backoffice/conhecimento">Conhecimento</Link></nav>
        <div className="profile"><span className="avatar">AD</span><span><strong>Ana Duarte</strong><small>Clínica Alyvo</small></span><ChevronDown size={17} /></div>
      </header>
      <div className="chat-layout">
        <aside className="conversation-list">
          <button className="button button-primary full"><Sparkles size={19} /> Nova conversa</button>
          <label className="search-label"><span className="sr-only">Buscar conversas</span><input placeholder="Buscar conversas..." /></label>
          <p className="nav-label">Hoje</p>
          <button className="conversation active">Cardiologistas com Vida+ <small>10:25</small></button>
          <button className="conversation">Documentos para consulta <small>09:14</small></button>
          <button className="conversation">Orientações pré-consulta <small>08:37</small></button>
          <p className="nav-label">Esta semana</p>
          <button className="conversation">Unidades e horários <small>Qua</small></button>
          <button className="conversation">Falar com a recepção <small>Seg</small></button>
        </aside>
        <section className="chat-main" aria-label="Conversa com a Alyvo">
          <header className="chat-title"><div><h1>Assistente Alyvo <i /> <small>Online</small></h1><p>Respostas baseadas na base aprovada da clínica</p></div><span className="trust-badge"><ShieldCheck size={17} /> Administrativo, sem diagnóstico</span></header>
          <div className="message-stream" aria-live="polite">
            {messages.map((message, index) => (
              <div className={`message-row ${message.role}`} key={`${index}-${message.content.slice(0, 12)}`}>
                <span className="message-avatar">{message.role === "assistant" ? "A" : "EU"}</span>
                <div className="message-bubble">
                  <p>{message.content}</p>
                  {message.intent === "schedule" && <Link href="/agendar" className="inline-action"><CalendarDays size={18} /> Ver horários disponíveis</Link>}
                  {message.citations?.length ? <details className="citations" open><summary><BookOpen size={17} /> Fontes consultadas ({message.citations.length})</summary>{message.citations.map((citation, citationIndex) => <div className="citation" key={citation.title}><span>{citationIndex + 1}</span><p><strong>{citation.title}</strong><small>{citation.source} — {citation.excerpt}</small></p></div>)}</details> : null}
                </div>
              </div>
            ))}
            {loading && <div className="message-row assistant"><span className="message-avatar">A</span><div className="typing" aria-label="Alyvo está respondendo"><i /><i /><i /></div></div>}
            {messages.length === 1 && <div className="prompt-grid">
              <button onClick={() => setText("Quais cardiologistas aceitam Vida+ na Unidade Centro?")}><MapPin /> Médicos por convênio</button>
              <button onClick={() => setText("Quero agendar uma consulta de cardiologia")}><CalendarDays /> Agendar consulta</button>
              <button onClick={() => setText("Quais documentos devo levar?")}><FileText /> Documentos necessários</button>
            </div>}
          </div>
          <form className="composer" onSubmit={submit}>
            <button type="button" className="icon-button" aria-label="Anexar documento"><Paperclip /></button>
            <label className="sr-only" htmlFor="message">Mensagem</label>
            <input id="message" value={text} onChange={(event) => setText(event.target.value)} placeholder="Pergunte sobre especialidades, convênios, unidades ou documentos..." />
            <button className="send-button" aria-label="Enviar mensagem" disabled={loading || !text.trim()}><Send /></button>
          </form>
        </section>
      </div>
    </main>
  );
}

