import { CalendarDays, Check, Clock3, Stethoscope } from "lucide-react";
import type { ToolResult } from "@/lib/api";

type ToolArguments =
  | { doctor_id: string; starts_at: string; reason: string }
  | { appointment_id: string }
  | { appointment_id: string; starts_at: string };

function assertNever(value: never): never {
  throw new Error(`ToolResult não suportado: ${JSON.stringify(value)}`);
}

function CatalogCards({ result }: { result: Extract<ToolResult, { type: "insurers" | "exams" | "specialties" | "units" }> }) {
  return <div className="tool-cards directory-cards">{result.items.map((item) => (
    <div className="appointment-tool" key={item.id}>
      <span className="tool-icon"><CalendarDays /></span>
      <span><strong>{item.name}</strong><small>{item.address ?? item.description ?? item.preparation ?? "Disponível"}</small></span>
    </div>
  ))}</div>;
}

export function ToolResultRenderer({ result, onAction }: {
  result: ToolResult;
  onAction: (tool: string, arguments_: ToolArguments) => void;
}) {
  switch (result.type) {
    case "insurers":
    case "exams":
    case "specialties":
    case "units":
      return <CatalogCards result={result} />;
    case "directory":
      return <div className="tool-cards directory-cards">{result.items.map((item) => (
        <div className="appointment-tool" key={item.id}>
          <span className="tool-icon"><Stethoscope /></span>
          <span><strong>{item.name}</strong><small>{item.specialty} · {item.unit} · {item.insurers.join(", ")}</small></span>
        </div>
      ))}</div>;
    case "availability":
      return <div className="tool-cards">{result.items.map((item) => (
        <button key={item.id} onClick={() => result.reschedule_appointment_id
          ? onAction("reschedule_appointment", {
            appointment_id: result.reschedule_appointment_id,
            starts_at: item.starts_at,
          })
          : onAction("create_appointment", {
            doctor_id: item.doctor.id,
            starts_at: item.starts_at,
            reason: "Consulta",
          })}>
          <span className="tool-icon"><CalendarDays /></span>
          <span><strong>{item.doctor.name}</strong><small>{new Date(item.starts_at).toLocaleString("pt-BR", { timeZone: result.timezone ?? undefined })} · {item.unit.name}</small></span>
          <span className="tool-action">{result.reschedule_appointment_id ? "Remarcar" : "Agendar"}</span>
        </button>
      ))}</div>;
    case "appointments":
      return <div className="tool-cards">{result.items.map((item) => (
        <div className="appointment-tool" key={item.id}>
          <span className="tool-icon"><Clock3 /></span>
          <span><strong>{item.doctor ?? item.reason}</strong><small>{new Date(item.starts_at).toLocaleString("pt-BR")} · {item.unit} · {item.status}</small></span>
          {item.status === "confirmed" && <>
            <button onClick={() => onAction("start_reschedule", { appointment_id: item.id })}>Remarcar</button>
            <button onClick={() => onAction("cancel_appointment", { appointment_id: item.id })}>Cancelar</button>
          </>}
        </div>
      ))}</div>;
    case "knowledge":
      return null;
    case "appointment_created":
    case "appointment_cancelled":
    case "appointment_rescheduled":
      return <p className="operation-success"><Check /> Operação concluída com segurança.</p>;
    case "reschedule_started":
      return <p className="operation-success"><Clock3 /> Consulta selecionada para remarcação.</p>;
    default:
      return assertNever(result);
  }
}
