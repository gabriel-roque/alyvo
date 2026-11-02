export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
export const TENANT = process.env.NEXT_PUBLIC_DEMO_TENANT ?? "clinic-alyvo";

let patientToken: string | null = null;

export type Citation = { title: string; source: string; excerpt: string };
export type ChatResponse = {
  id: string;
  answer: string;
  intent: string;
  confidence: number;
  citations: Citation[];
  auth_required: boolean;
  confirmation_request?: { id: string; tool: string; summary: string } | null;
  tool_result?: { type: string; items?: Record<string, unknown>[]; appointment?: Record<string, unknown>; timezone?: string; total?: number; has_more?: boolean; query_summary?: string } | null;
  tool_call?: { name: string } | null;
  suggestions?: { label: string; message: string }[];
  resolved_request?: Record<string, unknown> | null;
};
type BackofficePayload = Record<string, unknown> & { items: never[] };

export function staffAccessToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem("alyvo_staff_access_token");
}

export function setPatientToken(token: string) {
  patientToken = token;
}

export async function apiFetch(path: string, init: RequestInit = {}, token?: string | null) {
  const headers = new Headers(init.headers);
  headers.set("X-Tenant-ID", TENANT);
  const resolved = token === undefined ? patientToken ?? staffAccessToken() : token;
  if (resolved) headers.set("Authorization", `Bearer ${resolved}`);
  return fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
}

async function json<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail = payload.detail;
    if (typeof detail === "string") throw new Error(detail);
    if (Array.isArray(detail)) {
      const fields = detail
        .map((item) => item?.loc?.at?.(-1))
        .filter((item): item is string => typeof item === "string")
        .join(" e ");
      throw new Error(fields ? `Confira os campos: ${fields}.` : fallback);
    }
    throw new Error(fallback);
  }
  return response.json();
}

export async function createChatSession() {
  return json<{ id: string }>(await apiFetch("/chat/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tenant_id: TENANT }) }, patientToken), "Não foi possível iniciar a conversa");
}

export async function sendMessage(sessionId: string, content: string) {
  return json<ChatResponse>(await apiFetch(`/chat/sessions/${sessionId}/messages`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content }) }, patientToken), "A assistente está temporariamente indisponível");
}

export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: "status" | "delta", payload: { label?: string; text?: string }) => void,
) {
  const response = await apiFetch(`/chat/sessions/${sessionId}/messages/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ content }),
  }, patientToken);
  if (!response.ok || !response.body) throw new Error("A assistente está temporariamente indisponível");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: ChatResponse | undefined;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const event = frame.match(/^event: (.+)$/m)?.[1];
      const data = frame.match(/^data: (.+)$/m)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === "final") final = payload as ChatResponse;
      else if (event === "status" || event === "delta") onEvent(event, payload);
    }
    if (done) break;
  }
  if (!final) throw new Error("A resposta foi interrompida. Tente novamente.");
  return final;
}

export async function resumeChat(sessionId: string) {
  return json<ChatResponse>(await apiFetch(`/chat/sessions/${sessionId}/resume`, { method: "POST" }, patientToken), "Não foi possível retomar a solicitação");
}

export async function requestChatAction(sessionId: string, tool: string, arguments_: Record<string, unknown>) {
  return json<ChatResponse>(await apiFetch(`/chat/sessions/${sessionId}/actions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tool, arguments: arguments_ }) }, patientToken), "Não foi possível preparar a operação");
}

export async function confirmChatAction(sessionId: string, confirmationId: string, accepted = true) {
  return json<ChatResponse>(await apiFetch(`/chat/sessions/${sessionId}/confirmations/${confirmationId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ accepted }) }, patientToken), "Não foi possível concluir a operação");
}

export async function identifyPatient(cpf: string, birthDate: string) {
  const payload = await json<{ status: string; access_token?: string; registration_token?: string; patient?: { name: string } }>(await apiFetch("/auth/patient/identify", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tenant_id: TENANT, cpf, birth_date: birthDate }) }, null), "CPF ou data de nascimento inválidos");
  if (payload.access_token) setPatientToken(payload.access_token);
  return payload;
}

export async function registerPatient(payload: { name: string; email: string; registration_token: string }) {
  const result = await json<{ access_token: string; patient: { name: string } }>(await apiFetch("/auth/patient/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tenant_id: TENANT, ...payload }) }, null), "Não foi possível concluir o cadastro");
  setPatientToken(result.access_token);
  return result;
}

export async function staffLogin(email: string, password: string) {
  const payload = await json<{ access_token: string; refresh_token?: string }>(await apiFetch("/auth/staff/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tenant_id: TENANT, email, password }) }, null), "Credenciais inválidas");
  window.localStorage.setItem("alyvo_staff_access_token", payload.access_token);
  if (payload.refresh_token) window.localStorage.setItem("alyvo_staff_refresh_token", payload.refresh_token);
  return payload;
}

export async function backofficeGet(path: string) {
  return json<BackofficePayload>(await apiFetch(`/backoffice${path}`, {}, staffAccessToken()), "Acesso ao backoffice não autorizado");
}

export async function backofficeMutate(path: string, init: RequestInit) {
  return json<Record<string, unknown>>(await apiFetch(`/backoffice${path}`, init, staffAccessToken()), "Não foi possível concluir a operação");
}
