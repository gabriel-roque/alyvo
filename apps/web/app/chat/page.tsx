"use client";

import { BookOpen, CalendarDays, Check, ChevronDown, FileText, MapPin, Paperclip, Send, ShieldCheck, Sparkles, Upload } from "lucide-react";
import Link from "next/link";
import { DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import type { Citation, Slot } from "@alyvo/contracts";
import { Brand } from "@/components/brand";
import { accessToken, confirmPatientDocument, createChatSession, getAvailability, getPatientDocument, listMyAppointments, registerPatient, sendMessage, startPatientAuth, streamChatEvents, uploadChatAttachment, verifyPatient } from "@/lib/api";

type FormRequest = { type: "patient_auth" | "availability" | "appointments" };
type Message = { role: "user" | "assistant"; content: string; streamId?: string; citations?: Citation[]; intent?: string; canTicket?: boolean; form?: FormRequest; toolResult?: Record<string, unknown> | null };
type Appointment = { id: string; starts_at: string; status: string; reason: string };
type Review = { id: string; filename: string; status: string; fields: Record<string, string>; confidence: Record<string, number> };

const firstAnswer: Message = { role: "assistant", content: "Olá, sou a assistente administrativa da Alyvo. Posso localizar profissionais, explicar convênios e documentos, receber arquivos ou concluir agendamentos aqui na conversa. Como posso ajudar?" };

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([firstAnswer]);
  const [text, setText] = useState("");
  const [session, setSession] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [cpf, setCpf] = useState("123.456.789-09");
  const [email, setEmail] = useState("juliana.demo@alyvo.local");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [registrationToken, setRegistrationToken] = useState("");
  const [authStep, setAuthStep] = useState<"cpf" | "code" | "register" | "ready">("cpf");
  const [slots, setSlots] = useState<Slot[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [selected, setSelected] = useState<Slot | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => { if (accessToken()) setAuthStep("ready"); }, []);

  async function ensureSession() {
    const id = session ?? await createChatSession();
    setSession(id);
    return id;
  }

  async function appendResponse(sessionId: string, response: Awaited<ReturnType<typeof sendMessage>>) {
    const form = response.form_request as FormRequest | undefined;
    const streamId = `${Date.now()}-${Math.random()}`;
    const message: Message = { role: "assistant", content: "", streamId, citations: response.citations, intent: response.intent, canTicket: response.confirmation_request?.type === "ticket", form, toolResult: response.tool_result };
    setMessages((items) => [...items, message]);
    let streamed = "";
    try {
      await streamChatEvents(sessionId, (event, payload) => {
        if (event === "token") {
          streamed += String(payload.text ?? "");
          setMessages((items) => items.map((item) => item.streamId === streamId ? { ...item, content: streamed } : item));
        }
      });
    } catch {
      streamed = response.answer;
    }
    const finalAnswer = response.ticket_id ? "Ticket criado para a recepção." : streamed || response.answer;
    setMessages((items) => items.map((item) => item.streamId === streamId ? { ...item, content: finalAnswer } : item));
    if (form?.type === "availability") await loadOperations();
    if (form?.type === "appointments") setAppointments(await listMyAppointments());
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = text.trim();
    if (!content || loading) return;
    setMessages((items) => [...items, { role: "user", content }]);
    setText("");
    setLoading(true);
    try {
      const sessionId = await ensureSession();
      await appendResponse(sessionId, await sendMessage(sessionId, content));
    } catch (error) {
      setMessages((items) => [...items, { role: "assistant", content: error instanceof Error ? error.message : "Não foi possível consultar a Alyvo agora." }]);
    } finally { setLoading(false); }
  }

  async function loadOperations() {
    const [available, mine] = await Promise.all([getAvailability(), listMyAppointments()]);
    setSlots(available); setSelected(available[0] ?? null); setAppointments(mine);
  }

  async function continueAuthenticated() {
    const sessionId = await ensureSession();
    await appendResponse(sessionId, await sendMessage(sessionId, "Quero agendar uma consulta"));
  }

  async function authenticate() {
    try {
      setNotice("");
      if (authStep === "cpf") { await startPatientAuth(cpf, email); setAuthStep("code"); return; }
      if (authStep === "code") {
        const result = await verifyPatient(cpf, code);
        if (result.status === "registration_required") { setRegistrationToken(result.registration_token); setAuthStep("register"); return; }
        setAuthStep("ready"); await continueAuthenticated(); return;
      }
      await registerPatient({ cpf, name, email, registration_token: registrationToken });
      setAuthStep("ready"); await continueAuthenticated();
    } catch (error) { setNotice(error instanceof Error ? error.message : "Falha na autenticação"); }
  }

  async function runAction(action: Record<string, unknown>, label: string) {
    if (!session) return;
    setLoading(true);
    try {
      setMessages((items) => [...items, { role: "user", content: label }]);
      await appendResponse(session, await sendMessage(session, label, { action, confirmed: true }));
      await loadOperations();
    } finally { setLoading(false); }
  }

  async function upload(file: File) {
    if (!accessToken()) { setNotice("Confirme sua identidade no formulário da conversa antes de anexar."); return; }
    setNotice("Enviando e processando o documento…");
    try {
      const sessionId = await ensureSession();
      let item = await uploadChatAttachment(sessionId, file, "insurance_card");
      for (let attempt = 0; attempt < 225 && ["uploaded", "processing"].includes(item.status); attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 800));
        item = await getPatientDocument(item.id);
      }
      if (item.status !== "review_required") throw new Error("O OCR não ficou pronto para revisão");
      setReview(item); setFields(item.fields); setNotice("");
    } catch (error) { setNotice(error instanceof Error ? error.message : "Falha no documento"); }
  }

  function drop(event: DragEvent<HTMLFormElement>) { event.preventDefault(); const file = event.dataTransfer.files[0]; if (file) void upload(file); }

  return <main className="chat-shell">
    <header className="app-header"><Brand /><nav><Link className="active" href="/chat">Assistente</Link><Link href="/agendar">Agenda</Link><Link href="/backoffice/pacientes">Pacientes</Link><Link href="/backoffice/conhecimento">Conhecimento</Link></nav><div className="profile"><span className="avatar">PA</span><span><strong>Paciente</strong><small>Clínica Alyvo</small></span><ChevronDown size={17} /></div></header>
    <div className="chat-layout"><aside className="conversation-list"><button className="button button-primary full" onClick={() => { setMessages([firstAnswer]); setSession(undefined); setReview(null); }}><Sparkles size={19} /> Nova conversa</button><p className="nav-label">Sessão atual</p><button className="conversation active">Conversa ponta a ponta <small>agora</small></button></aside>
      <section className="chat-main" aria-label="Conversa com a Alyvo"><header className="chat-title"><div><h1>Assistente Alyvo <i /> <small>Online</small></h1><p>Respostas e operações baseadas em dados reais da clínica</p></div><span className="trust-badge"><ShieldCheck size={17} /> Administrativo, sem diagnóstico</span></header>
        <div className="message-stream" aria-live="polite">
          {messages.map((message, index) => <div className={`message-row ${message.role}`} key={`${index}-${message.content.slice(0, 12)}`}><span className="message-avatar">{message.role === "assistant" ? "A" : "EU"}</span><div className="message-bubble"><p>{message.content}</p>
            {message.form?.type === "patient_auth" && authStep !== "ready" && <div className="chat-inline-form">
              {authStep === "cpf" && <><label>CPF<input value={cpf} onChange={(event) => setCpf(event.target.value)} /></label><label>E-mail<input value={email} onChange={(event) => setEmail(event.target.value)} /></label></>}
              {authStep === "code" && <label>Código temporário<input value={code} onChange={(event) => setCode(event.target.value)} /></label>}
              {authStep === "register" && <><label>Nome<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>E-mail<input value={email} onChange={(event) => setEmail(event.target.value)} /></label></>}
              <button className="inline-action" onClick={() => void authenticate()}><ShieldCheck size={18} /> {authStep === "cpf" ? "Enviar código" : authStep === "code" ? "Validar código" : "Cadastrar"}</button>
            </div>}
            {message.form?.type === "availability" && <div className="chat-options">{slots.slice(0, 8).map((slot) => <button key={slot.id} className={selected?.id === slot.id ? "selected" : ""} onClick={() => setSelected(slot)}><strong>{slot.doctor.name}</strong><span>{new Date(slot.starts_at).toLocaleString("pt-BR")} · {slot.unit.name}</span></button>)}{selected && <button className="inline-action" onClick={() => void runAction({ type: "schedule", doctor_id: selected.doctor.id, starts_at: selected.starts_at, reason: "Consulta" }, "Confirmo este agendamento")}><Check size={18} /> Confirmar agendamento</button>}</div>}
            {message.form?.type === "appointments" && <div className="chat-options">{appointments.filter((item) => item.status === "confirmed").map((item) => <button key={item.id} onClick={() => void runAction({ type: "cancel", appointment_id: item.id }, "Confirmo o cancelamento")}><strong>{item.reason}</strong><span>{new Date(item.starts_at).toLocaleString("pt-BR")} · cancelar</span></button>)}</div>}
            {message.canTicket && session && <button className="inline-action" onClick={async () => appendResponse(session, await sendMessage(session, "Quero falar com a recepção", { confirmTicket: true }))}><ShieldCheck size={18} /> Criar ticket</button>}
            {message.toolResult && <p className="operation-success"><Check size={16} /> Operação concluída e auditada.</p>}
            {message.citations?.length ? <details className="citations" open><summary><BookOpen size={17} /> Fontes consultadas ({message.citations.length})</summary>{message.citations.map((citation, citationIndex) => <div className="citation" key={`${citation.title}-${citationIndex}`}><span>{citationIndex + 1}</span><p><strong>{citation.title}</strong><small>{citation.source} — {citation.excerpt}</small></p></div>)}</details> : null}
          </div></div>)}
          {loading && <div className="message-row assistant"><span className="message-avatar">A</span><div className="typing" aria-label="Alyvo está respondendo"><i /><i /><i /></div></div>}
          {review && <section className="chat-document panel"><header><Upload size={18} /> Revise a extração de {review.filename}</header>{Object.entries(fields).map(([key, value]) => <label key={key}>{key}<input value={value} onChange={(event) => setFields((current) => ({ ...current, [key]: event.target.value }))} /><small>Confiança: {Math.round((review.confidence[key] ?? 0) * 100)}%</small></label>)}<button className="button button-primary" onClick={async () => { await confirmPatientDocument(review.id, fields); setReview(null); setNotice("Documento confirmado e liberado à recepção."); }}>Confirmar dados</button></section>}
          {notice && <p className="chat-notice" role="status">{notice}</p>}
          {messages.length === 1 && <div className="prompt-grid"><button onClick={() => setText("Quais cardiologistas aceitam Vida+ na Unidade Centro?")}><MapPin /> Médicos por convênio</button><button onClick={() => setText("Quero agendar uma consulta de cardiologia")}><CalendarDays /> Agendar consulta</button><button onClick={() => setText("Quais documentos devo levar?")}><FileText /> Documentos necessários</button></div>}
        </div>
        <form className="composer" onSubmit={submit} onDragOver={(event) => event.preventDefault()} onDrop={drop}><button type="button" className="icon-button" aria-label="Anexar documento" onClick={() => fileInput.current?.click()}><Paperclip /></button><input ref={fileInput} hidden type="file" accept="image/png,image/jpeg,application/pdf" onChange={(event) => event.target.files?.[0] && void upload(event.target.files[0])} /><label className="sr-only" htmlFor="message">Mensagem</label><input id="message" value={text} onChange={(event) => setText(event.target.value)} placeholder="Pergunte, agende, cancele ou arraste um documento…" /><button className="send-button" aria-label="Enviar mensagem" disabled={loading || !text.trim()}><Send /></button></form>
      </section>
    </div>
  </main>;
}
