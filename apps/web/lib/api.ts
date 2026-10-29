import type { ChatResponse, Doctor, Slot } from "@alyvo/contracts";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
export const TENANT = process.env.NEXT_PUBLIC_DEMO_TENANT ?? "clinic-alyvo";

export async function createChatSession(): Promise<string> {
  const response = await fetch(`${API_URL}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tenant_id: TENANT }),
  });
  if (!response.ok) throw new Error("Não foi possível iniciar a conversa");
  return (await response.json()).id;
}

export async function sendMessage(sessionId: string, content: string): Promise<ChatResponse> {
  const response = await fetch(`${API_URL}/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!response.ok) throw new Error("A assistente está temporariamente indisponível");
  return response.json();
}

export async function getAvailability(): Promise<Slot[]> {
  const response = await fetch(`${API_URL}/availability?tenant_id=${TENANT}`, { cache: "no-store" });
  if (!response.ok) throw new Error("Não foi possível consultar a agenda");
  return (await response.json()).items;
}

export const demoDoctors: Doctor[] = [
  { id: "marina", name: "Dra. Marina Lopes", crm: "CRM 123456 SP", specialty: "Cardiologia", unit: "Unidade Centro", insurers: ["Vida+", "Amil"] },
  { id: "lucas", name: "Dr. Lucas Ferreira", crm: "CRM 234567 SP", specialty: "Cardiologia", unit: "Unidade Centro", insurers: ["Vida+"] },
  { id: "amanda", name: "Dra. Amanda Prado", crm: "CRM 345678 SP", specialty: "Pediatria", unit: "Unidade Sul", insurers: ["Amil"] },
];

