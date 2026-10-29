/** Public client-facing types generated from the Alyvo OpenAPI domain. */
export type Citation = { title: string; source: string; excerpt: string };

export type ChatResponse = {
  id: string;
  answer: string;
  intent: "knowledge" | "schedule" | "cancel_appointment" | "ticket" | "clinical_safety";
  confidence: number;
  citations: Citation[];
  form_request?: { type: string; endpoint?: string; fields?: string[] };
  confirmation_request?: { type: string; label: string };
  graph_trace: string[];
};

export type Doctor = {
  id: string;
  name: string;
  crm: string;
  specialty: string;
  unit: string;
  insurers: string[];
};

export type Slot = {
  id: string;
  doctor: { id: string; name: string; crm: string };
  unit: { id: string; name: string; address: string };
  starts_at: string;
  ends_at: string;
};

export type DocumentReview = {
  id: string;
  kind: string;
  filename: string;
  fields: Record<string, string>;
  confidence: Record<string, number>;
  confirmed: boolean;
  status: string;
};

