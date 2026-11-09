import { createAlyvoClient, type components } from "@alyvo/contracts";

const configuredUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const API_ROOT = configuredUrl.endsWith("/api/v1") ? configuredUrl.slice(0, -7) : configuredUrl;

let patientToken: string | null = null;

export type Citation = components["schemas"]["Citation"];
export type ChatResponse = components["schemas"]["ChatResponse"];
export type ToolResult = NonNullable<ChatResponse["tool_result"]>;
export type Doctor = components["schemas"]["DoctorView"];
export type Catalog = components["schemas"]["CatalogView"];
export type Patient = components["schemas"]["PatientListView"];
export type Appointment = components["schemas"]["AppointmentView"];
export type AvailabilityRule = components["schemas"]["AvailabilityRuleView"];
export type AvailabilityBlock = components["schemas"]["AvailabilityBlockView"];
export type KnowledgeDocument = components["schemas"]["DocumentView"];
export type CatalogKind = "specialties" | "units" | "insurers" | "exams";
export type BackofficeItem = Doctor | Catalog | Patient;

export function staffAccessToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem("alyvo_staff_access_token");
}

export function setPatientToken(token: string) {
  patientToken = token;
}

const publicClient = createAlyvoClient(API_ROOT);
const patientClient = createAlyvoClient(API_ROOT, () => patientToken);
const staffClient = createAlyvoClient(API_ROOT, staffAccessToken);

type ApiResult<T> = { data?: T; error?: unknown; response: Response };

function messageFrom(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null && "message" in error && typeof error.message === "string") {
    return error.message;
  }
  return fallback;
}

function unwrap<T>(result: ApiResult<T>, fallback: string): T {
  if (result.data !== undefined) return result.data;
  throw new Error(messageFrom(result.error, fallback));
}

function expectNoContent(result: ApiResult<unknown>, fallback: string): void {
  if (result.response.status === 204) return;
  throw new Error(messageFrom(result.error, fallback));
}

function isChatResponse(value: unknown): value is ChatResponse {
  return typeof value === "object" && value !== null
    && "answer" in value && typeof value.answer === "string"
    && "intent" in value && typeof value.intent === "string"
    && "confidence" in value && typeof value.confidence === "number"
    && "citations" in value && Array.isArray(value.citations)
    && "suggestions" in value && Array.isArray(value.suggestions);
}

export async function createChatSession() {
  return unwrap(await patientClient.POST("/api/v1/chat/sessions"), "Não foi possível iniciar a conversa");
}

export async function sendMessage(sessionId: string, content: string) {
  return unwrap(
    await patientClient.POST("/api/v1/chat/sessions/{session_id}/messages", {
      params: { path: { session_id: sessionId } },
      body: { content },
    }),
    "A assistente está temporariamente indisponível",
  );
}

export async function streamMessage(
  sessionId: string,
  content: string,
  onEvent: (event: "status" | "delta", payload: { label?: string; text?: string }) => void,
) {
  const result = await patientClient.POST("/api/v1/chat/sessions/{session_id}/messages/stream", {
    params: { path: { session_id: sessionId } },
    body: { content },
    parseAs: "stream",
  });
  if (result.error || !result.data) throw new Error("A assistente está temporariamente indisponível");
  const reader = result.data.getReader();
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
      const payload: unknown = JSON.parse(data);
      if (event === "final" && isChatResponse(payload)) final = payload;
      if ((event === "status" || event === "delta") && typeof payload === "object" && payload !== null) {
        const label = "label" in payload && typeof payload.label === "string" ? payload.label : undefined;
        const text = "text" in payload && typeof payload.text === "string" ? payload.text : undefined;
        onEvent(event, { label, text });
      }
    }
    if (done) break;
  }
  if (!final) throw new Error("A resposta foi interrompida. Tente novamente.");
  return final;
}

export async function resumeChat(sessionId: string) {
  return unwrap(
    await patientClient.POST("/api/v1/chat/sessions/{session_id}/resume", {
      params: { path: { session_id: sessionId } },
    }),
    "Não foi possível retomar a solicitação",
  );
}

export async function requestChatAction(
  sessionId: string,
  tool: string,
  arguments_: components["schemas"]["ActionCreate"]["arguments"],
) {
  return unwrap(
    await patientClient.POST("/api/v1/chat/sessions/{session_id}/actions", {
      params: { path: { session_id: sessionId } },
      body: { tool, arguments: arguments_ },
    }),
    "Não foi possível preparar a operação",
  );
}

export async function confirmChatAction(sessionId: string, confirmationId: string, accepted = true) {
  return unwrap(
    await patientClient.POST("/api/v1/chat/sessions/{session_id}/confirmations/{confirmation_id}", {
      params: { path: { session_id: sessionId, confirmation_id: confirmationId } },
      body: { accepted },
    }),
    "Não foi possível concluir a operação",
  );
}

export async function identifyPatient(cpf: string, birthDate: string) {
  const payload = unwrap(
    await publicClient.POST("/api/v1/auth/patients/identify", { body: { cpf, birth_date: birthDate } }),
    "CPF ou data de nascimento inválidos",
  );
  if (payload.access_token) setPatientToken(payload.access_token);
  return payload;
}

export async function registerPatient(payload: components["schemas"]["PatientRegister"]) {
  const result = unwrap(
    await publicClient.POST("/api/v1/auth/patients/register", { body: payload }),
    "Não foi possível concluir o cadastro",
  );
  if (result.access_token) setPatientToken(result.access_token);
  return result;
}

export async function staffLogin(email: string, password: string) {
  const payload = unwrap(
    await publicClient.POST("/api/v1/auth/staff/login", { body: { email, password } }),
    "Credenciais inválidas",
  );
  window.localStorage.setItem("alyvo_staff_access_token", payload.access_token);
  window.localStorage.setItem("alyvo_staff_refresh_token", payload.refresh_token);
  return payload;
}

export async function getDashboard() {
  return unwrap(await staffClient.GET("/api/v1/backoffice/dashboard"), "Acesso não autorizado");
}

export async function listDoctors(query = "", includeInactive = true) {
  return unwrap(await staffClient.GET("/api/v1/backoffice/doctors", {
    params: { query: { q: query, include_inactive: includeInactive } },
  }), "Não foi possível carregar médicos");
}

export async function listPatients(query = "") {
  return unwrap(await staffClient.GET("/api/v1/backoffice/patients", {
    params: { query: { q: query } },
  }), "Não foi possível carregar pacientes");
}

export async function listCatalog(kind: CatalogKind, query = "", includeInactive = true) {
  const params = { query: { q: query, include_inactive: includeInactive, page: 1, page_size: 100 } };
  if (kind === "specialties") return unwrap(await staffClient.GET("/api/v1/backoffice/specialties", { params }), "Falha no catálogo");
  if (kind === "units") return unwrap(await staffClient.GET("/api/v1/backoffice/units", { params }), "Falha no catálogo");
  if (kind === "insurers") return unwrap(await staffClient.GET("/api/v1/backoffice/insurers", { params }), "Falha no catálogo");
  return unwrap(await staffClient.GET("/api/v1/backoffice/exams", { params }), "Falha no catálogo");
}

export async function saveDoctor(
  body: components["schemas"]["DoctorPayload"],
  id?: string,
) {
  if (id) return unwrap(await staffClient.PUT("/api/v1/backoffice/doctors/{doctor_id}", {
    params: { path: { doctor_id: id } }, body,
  }), "Falha ao salvar médico");
  return unwrap(await staffClient.POST("/api/v1/backoffice/doctors", { body }), "Falha ao criar médico");
}

export async function archiveDoctor(id: string) {
  expectNoContent(await staffClient.DELETE("/api/v1/backoffice/doctors/{doctor_id}", {
    params: { path: { doctor_id: id } },
  }), "Falha ao arquivar médico");
}

export async function saveCatalog(
  kind: CatalogKind,
  body: components["schemas"]["CatalogPayload"],
  id?: string,
) {
  if (kind === "specialties") {
    return id
      ? unwrap(await staffClient.PATCH("/api/v1/backoffice/specialties/{item_id}", { params: { path: { item_id: id } }, body }), "Falha ao salvar")
      : unwrap(await staffClient.POST("/api/v1/backoffice/specialties", { body }), "Falha ao criar");
  }
  if (kind === "units") {
    return id
      ? unwrap(await staffClient.PATCH("/api/v1/backoffice/units/{item_id}", { params: { path: { item_id: id } }, body }), "Falha ao salvar")
      : unwrap(await staffClient.POST("/api/v1/backoffice/units", { body }), "Falha ao criar");
  }
  if (kind === "insurers") {
    return id
      ? unwrap(await staffClient.PATCH("/api/v1/backoffice/insurers/{item_id}", { params: { path: { item_id: id } }, body }), "Falha ao salvar")
      : unwrap(await staffClient.POST("/api/v1/backoffice/insurers", { body }), "Falha ao criar");
  }
  return id
    ? unwrap(await staffClient.PATCH("/api/v1/backoffice/exams/{item_id}", { params: { path: { item_id: id } }, body }), "Falha ao salvar")
    : unwrap(await staffClient.POST("/api/v1/backoffice/exams", { body }), "Falha ao criar");
}

export async function archiveCatalog(kind: CatalogKind, id: string) {
  if (kind === "specialties") return expectNoContent(await staffClient.DELETE("/api/v1/backoffice/specialties/{item_id}", { params: { path: { item_id: id } } }), "Falha ao arquivar");
  if (kind === "units") return expectNoContent(await staffClient.DELETE("/api/v1/backoffice/units/{item_id}", { params: { path: { item_id: id } } }), "Falha ao arquivar");
  if (kind === "insurers") return expectNoContent(await staffClient.DELETE("/api/v1/backoffice/insurers/{item_id}", { params: { path: { item_id: id } } }), "Falha ao arquivar");
  return expectNoContent(await staffClient.DELETE("/api/v1/backoffice/exams/{item_id}", { params: { path: { item_id: id } } }), "Falha ao arquivar");
}

export async function listAgenda(start: string, end: string, doctorId?: string, unitId?: string) {
  return unwrap(await staffClient.GET("/api/v1/backoffice/appointments", {
    params: { query: { start, end, doctor_id: doctorId, unit_id: unitId } },
  }), "Falha ao carregar agenda");
}

export async function listAvailabilityRules() {
  return unwrap(await staffClient.GET("/api/v1/backoffice/availability/rules"), "Falha nas regras");
}

export async function listAvailabilityBlocks() {
  return unwrap(await staffClient.GET("/api/v1/backoffice/availability/blocks"), "Falha nos bloqueios");
}

export async function createAppointment(body: components["schemas"]["StaffAppointmentCreate"]) {
  return unwrap(await staffClient.POST("/api/v1/backoffice/appointments", { body }), "Falha ao criar consulta");
}

export async function updateAppointment(id: string, body: components["schemas"]["AppointmentUpdate"]) {
  return unwrap(await staffClient.PATCH("/api/v1/backoffice/appointments/{appointment_id}", {
    params: { path: { appointment_id: id } }, body,
  }), "Falha ao reagendar consulta");
}

export async function cancelAppointment(id: string) {
  expectNoContent(await staffClient.DELETE("/api/v1/backoffice/appointments/{appointment_id}", {
    params: { path: { appointment_id: id } },
  }), "Falha ao cancelar consulta");
}

export async function createAvailabilityRule(body: components["schemas"]["AvailabilityRulePayload"]) {
  return unwrap(await staffClient.POST("/api/v1/backoffice/availability/rules", { body }), "Falha ao criar regra");
}

export async function createAvailabilityBlock(body: components["schemas"]["AvailabilityBlockPayload"]) {
  return unwrap(await staffClient.POST("/api/v1/backoffice/availability/blocks", { body }), "Falha ao criar bloqueio");
}

export async function listKnowledgeDocuments() {
  return unwrap(await staffClient.GET("/api/v1/backoffice/knowledge/documents"), "Falha ao carregar conhecimento");
}

export async function uploadKnowledge(files: File[]) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return unwrap(await staffClient.POST("/api/v1/backoffice/knowledge/uploads", {
    body: { files: files.map((file) => file.name) },
    bodySerializer: () => form,
  }), "Falha no upload dos documentos");
}

export async function publishKnowledge(id: string, entities: components["schemas"]["PublishDocument"]["entities"] = []) {
  return unwrap(await staffClient.POST("/api/v1/backoffice/knowledge/documents/{document_id}/publish", {
    params: { path: { document_id: id } }, body: { entities, confirmed: true },
  }), "Falha ao publicar conhecimento");
}

export async function rejectKnowledge(id: string) {
  return unwrap(await staffClient.POST("/api/v1/backoffice/knowledge/documents/{document_id}/reject", {
    params: { path: { document_id: id } },
  }), "Falha ao rejeitar conhecimento");
}
