import type { ChatResponse, Slot } from "@alyvo/contracts";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
export const TENANT = process.env.NEXT_PUBLIC_DEMO_TENANT ?? "clinic-alyvo";

export function accessToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem("alyvo_access_token");
}

export function storeTokens(payload: { access_token: string; refresh_token?: string }) {
  window.localStorage.setItem("alyvo_access_token", payload.access_token);
  if (payload.refresh_token) window.localStorage.setItem("alyvo_refresh_token", payload.refresh_token);
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const token = accessToken();
  const headers = new Headers(init.headers);
  headers.set("X-Tenant-ID", TENANT);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
}

export async function createChatSession(): Promise<string> {
  const response = await apiFetch(`/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: TENANT }),
  });
  if (!response.ok) throw new Error("Não foi possível iniciar a conversa");
  return (await response.json()).id;
}

export async function sendMessage(sessionId: string, content: string, options: { confirmTicket?: boolean } = {}): Promise<ChatResponse> {
  const response = await apiFetch(`/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, confirm_ticket: options.confirmTicket ?? false }),
  });
  if (!response.ok) throw new Error("A assistente está temporariamente indisponível");
  return response.json();
}

export async function getAvailability(): Promise<Slot[]> {
  const response = await apiFetch(`/availability?tenant_id=${TENANT}`);
  if (!response.ok) throw new Error("Não foi possível consultar a agenda");
  return (await response.json()).items;
}

export async function startPatientAuth(cpf: string, email?: string) {
  const response = await apiFetch("/auth/patient/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: TENANT, cpf, email }),
  });
  if (!response.ok) throw new Error("Não foi possível enviar o código");
  return response.json();
}

export async function verifyPatient(cpf: string, code: string) {
  const response = await apiFetch("/auth/patient/verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: TENANT, cpf, code }),
  });
  if (!response.ok) throw new Error("Código inválido ou expirado");
  const payload = await response.json();
  if (payload.access_token) storeTokens(payload);
  return payload;
}

export async function registerPatient(payload: { cpf: string; name: string; email: string; registration_token: string }) {
  const response = await apiFetch("/auth/patient/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: TENANT, ...payload }),
  });
  if (!response.ok) throw new Error((await response.json()).detail ?? "Não foi possível concluir o cadastro");
  const tokens = await response.json();
  storeTokens(tokens);
  return tokens;
}

export async function createAppointment(slot: Slot) {
  const response = await apiFetch("/appointments", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doctor_id: slot.doctor.id, starts_at: slot.starts_at, reason: "Consulta", confirmed: true }),
  });
  if (!response.ok) throw new Error((await response.json()).detail ?? "Não foi possível agendar");
  return response.json();
}

export async function listMyAppointments() {
  const response = await apiFetch("/appointments/me");
  if (!response.ok) throw new Error("Não foi possível consultar seus agendamentos");
  return (await response.json()).items;
}

export async function cancelAppointment(id: string) {
  const response = await apiFetch(`/appointments/${id}/cancel?confirmed=true`, { method: "POST" });
  if (!response.ok) throw new Error((await response.json()).detail ?? "Não foi possível cancelar");
  return response.json();
}

export async function uploadPatientDocument(file: File, kind: string) {
  const body = new FormData();
  body.append("file", file);
  body.append("kind", kind);
  const response = await apiFetch("/patient/documents", { method: "POST", body });
  if (!response.ok) throw new Error((await response.json()).detail ?? "Falha no upload");
  return response.json();
}

export async function getPatientDocument(id: string) {
  const response = await apiFetch(`/patient/documents/${id}`);
  if (!response.ok) throw new Error("Documento indisponível");
  return response.json();
}

export async function confirmPatientDocument(id: string, fields: Record<string, string>) {
  const response = await apiFetch(`/patient/documents/${id}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields, confirmed: true }),
  });
  if (!response.ok) throw new Error("Não foi possível confirmar o documento");
  return response.json();
}

export async function staffLogin(email: string, password: string) {
  const response = await apiFetch("/auth/staff/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: TENANT, email, password }),
  });
  if (!response.ok) throw new Error("Credenciais inválidas");
  const payload = await response.json();
  storeTokens(payload);
  return payload;
}

export async function backofficeGet(path: string) {
  const response = await apiFetch(`/backoffice${path}`);
  if (!response.ok) throw new Error("Acesso ao backoffice não autorizado");
  return response.json();
}

