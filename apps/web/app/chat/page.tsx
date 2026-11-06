"use client";

import { ArrowLeft, BookOpen, CalendarDays, Check, Send, ShieldCheck, Sparkles, Stethoscope, UserRound } from "lucide-react";
import Link from "next/link";
import { FormEvent, useReducer, useRef, useState } from "react";
import { Brand } from "@/components/brand";
import { identifyPatient, registerPatient } from "@/features/auth/api";
import { ToolResultRenderer } from "@/features/chat/tool-result";
import {
  confirmChatAction,
  createChatSession,
  requestChatAction,
  resumeChat,
  streamMessage,
  type ChatResponse,
  type Citation,
} from "@/features/chat/api";

type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  response?: ChatResponse;
};

type MessageAction = { type: "append"; message: Message };

function messageReducer(state: Message[], action: MessageAction): Message[] {
  if (action.type === "append") return [...state, action.message];
  return state;
}

const welcome: Message = {
  role: "assistant",
  content: "Olá! Posso ajudar com médicos, convênios, exames, horários e suas consultas. Você pode começar sem se identificar.",
};

export default function ChatPage() {
  const [messages, dispatchMessage] = useReducer(messageReducer, [welcome]);
  const [text, setText] = useState("");
  const [session, setSession] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [activity, setActivity] = useState("");
  const [draft, setDraft] = useState("");
  const [cpf, setCpf] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [registrationToken, setRegistrationToken] = useState("");
  const [authMode, setAuthMode] = useState<"identify" | "register">("identify");
  const [identifiedName, setIdentifiedName] = useState("");
  const [notice, setNotice] = useState("");
  const streamEnd = useRef<HTMLDivElement>(null);

  async function ensureSession() {
    if (session) return session;
    const created = await createChatSession();
    setSession(created.id);
    return created.id;
  }

  function appendResponse(response: ChatResponse) {
    dispatchMessage({ type: "append", message: { role: "assistant", content: response.answer, citations: response.citations, response } });
    window.setTimeout(() => streamEnd.current?.scrollIntoView({ behavior: "smooth" }), 50);
  }

  async function sendPrompt(content: string) {
    if (!content || loading) return;
    dispatchMessage({ type: "append", message: { role: "user", content } });
    setText("");
    setLoading(true);
    setActivity("Entendendo seu pedido…");
    setDraft("");
    setNotice("");
    try {
      const response = await streamMessage(await ensureSession(), content, (event, payload) => {
        if (event === "status") setActivity(payload.label ?? "Consultando…");
        if (event === "delta") {
          setActivity("");
          setDraft((current) => current + (payload.text ?? ""));
        }
      });
      appendResponse(response);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Não foi possível consultar a Alyvo.");
    } finally {
      setLoading(false);
      setActivity("");
      setDraft("");
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await sendPrompt(text.trim());
  }

  async function authenticate() {
    setLoading(true);
    setNotice("");
    try {
      if (authMode === "identify") {
        const result = await identifyPatient(cpf, birthDate);
        if (result.status === "registration_required") {
          setRegistrationToken(result.registration_token ?? "");
          setAuthMode("register");
          return;
        }
        setIdentifiedName(result.patient?.name ?? "Paciente");
      } else {
        const result = await registerPatient({ name, email, registration_token: registrationToken });
        setIdentifiedName(result.patient?.name ?? name);
      }
      if (session) appendResponse(await resumeChat(session));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Não foi possível confirmar seus dados.");
    } finally {
      setLoading(false);
    }
  }

  async function action(
    tool: string,
    arguments_: { doctor_id: string; starts_at: string; reason: string } | { appointment_id: string },
  ) {
    setLoading(true);
    setNotice("");
    try {
      appendResponse(await requestChatAction(await ensureSession(), tool, arguments_));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Não foi possível preparar a operação.");
    } finally {
      setLoading(false);
    }
  }

  async function confirm(id: string, accepted: boolean) {
    if (!session) return;
    setLoading(true);
    try {
      appendResponse(await confirmChatAction(session, id, accepted));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Não foi possível concluir a operação.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="patient-chat">
      <header className="chat-header">
        <Link href="/" className="icon-button" aria-label="Voltar para o início"><ArrowLeft /></Link>
        <Brand />
        <span className={identifiedName ? "identity-chip identified" : "identity-chip"}>
          {identifiedName ? <Check /> : <ShieldCheck />}
          {identifiedName || "Conversa anônima"}
        </span>
      </header>

      <section className="chat-window" aria-label="Conversa com a Alyvo">
        <header className="chat-intro">
          <div className="assistant-mark"><Sparkles /></div>
          <div><h1>Assistente Alyvo</h1><p>Informação administrativa, agenda e conhecimento da clínica.</p></div>
          <span><i /> Pronta para ajudar</span>
        </header>

        <div className="message-stream" aria-live="polite">
          {messages.map((message, index) => {
            const result = message.response?.tool_result;
            return (
              <article className={`chat-message ${message.role}`} key={`${index}-${message.content.slice(0, 16)}`}>
                {message.role === "assistant" && <span className="message-avatar">A</span>}
                <div className="message-content">
                  <p>{message.content}</p>

                  {message.response?.auth_required && !identifiedName && (
                    <section className="identity-card">
                      <header><UserRound /><div><strong>Confirme sua identidade</strong><small>Seus dados não ficam salvos neste navegador.</small></div></header>
                      {authMode === "identify" ? (
                        <div className="form-grid two">
                          <label>CPF<input inputMode="numeric" value={cpf} onChange={(event) => setCpf(event.target.value)} /></label>
                          <label>Data de nascimento<input type="date" value={birthDate} onChange={(event) => setBirthDate(event.target.value)} /></label>
                        </div>
                      ) : (
                        <div className="form-grid two">
                          <label>Nome completo<input value={name} onChange={(event) => setName(event.target.value)} /></label>
                          <label>E-mail<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
                        </div>
                      )}
                      <button className="button button-primary" disabled={loading || (authMode === "identify" ? !cpf || !birthDate : !name || !email)} onClick={() => void authenticate()}>
                        <ShieldCheck /> {authMode === "identify" ? "Continuar" : "Criar cadastro"}
                      </button>
                    </section>
                  )}

                  {result && <ToolResultRenderer result={result} onAction={(tool, arguments_) => void action(tool, arguments_)} />}

                  {message.response?.confirmation_request && (
                    <section className="confirmation-card">
                      <strong>Confirmar operação?</strong>
                      <p>{message.response.confirmation_request.summary}</p>
                      <div>
                        <button className="button button-secondary" onClick={() => void confirm(message.response!.confirmation_request!.id, false)}>Voltar</button>
                        <button className="button button-primary" onClick={() => void confirm(message.response!.confirmation_request!.id, true)}><Check /> Confirmar</button>
                      </div>
                    </section>
                  )}

                  {message.citations?.length ? (
                    <details className="citations">
                      <summary><BookOpen /> Fontes consultadas ({message.citations.length})</summary>
                      {message.citations.map((citation, citationIndex) => <p key={`${citation.title}-${citationIndex}`}><strong>{citation.title}</strong><small>{citation.source} — {citation.excerpt}</small></p>)}
                    </details>
                  ) : null}

                  {message.response?.suggestions?.length ? (
                    <div className="reply-suggestions" aria-label="Sugestões de resposta">
                      {message.response.suggestions.map((suggestion) => (
                        <button key={`${index}-${suggestion.label}`} disabled={loading} onClick={() => void sendPrompt(suggestion.message)}>{suggestion.label}</button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </article>
            );
          })}
          {loading && <div className="chat-message assistant" aria-live="polite"><span className="message-avatar">A</span><div className="message-content streaming-message"><p>{draft || activity}</p>{!draft && <span className="typing-dots"><i /><i /><i /></span>}</div></div>}
          {notice && <p className="error-text" role="alert">{notice}</p>}
          {messages.length === 1 && (
            <div className="suggestion-grid">
              <button onClick={() => setText("Quais cardiologistas aceitam Vida+?")}><Stethoscope /> Médicos por convênio</button>
              <button onClick={() => setText("Quero ver horários disponíveis")}><CalendarDays /> Horários disponíveis</button>
              <button onClick={() => setText("Quais são minhas consultas?")}><UserRound /> Minhas consultas</button>
            </div>
          )}
          <div ref={streamEnd} />
        </div>

        <form className="chat-composer" onSubmit={submit}>
          <label className="sr-only" htmlFor="chat-message">Mensagem</label>
          <input id="chat-message" value={text} onChange={(event) => setText(event.target.value)} placeholder="Pergunte sobre a clínica ou suas consultas…" />
          <button aria-label="Enviar mensagem" disabled={loading || !text.trim()}><Send /></button>
        </form>
      </section>
    </main>
  );
}
