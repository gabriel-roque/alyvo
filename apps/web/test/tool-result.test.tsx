import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ToolResultRenderer } from "@/features/chat/tool-result";
import type { ToolResult } from "@/lib/api";

const noop = vi.fn();

describe("ToolResultRenderer", () => {
  it.each([
    ["insurers", "Saúde Azul", { type: "insurers", total: 1, items: [{ id: "i1", name: "Saúde Azul", active: true, description: null }] }],
    ["exams", "Hemograma", { type: "exams", total: 1, items: [{ id: "e1", name: "Hemograma", active: true, preparation: "Jejum" }] }],
    ["specialties", "Cardiologia", { type: "specialties", total: 1, items: [{ id: "s1", name: "Cardiologia", active: true, description: null }] }],
    ["units", "Centro", { type: "units", total: 1, items: [{ id: "u1", name: "Centro", active: true, address: "Rua Exemplo, 10" }] }],
  ] as const)("renders the %s catalog variant", (_, label, result) => {
    render(<ToolResultRenderer result={result as unknown as ToolResult} onAction={noop} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("renders directory and knowledge variants", () => {
    const { rerender } = render(<ToolResultRenderer result={{
      type: "directory",
      total: 1,
      items: [{ id: "d1", name: "Dra. Ana", crm: "CRM 1", specialty_id: "s1", specialty: "Clínica", unit_id: "u1", unit: "Centro", insurer_ids: ["i1"], insurers: ["Saúde Azul"], active: true }],
    }} onAction={noop} />);
    expect(screen.getByText("Dra. Ana")).toBeVisible();
    rerender(<ToolResultRenderer result={{ type: "knowledge", query: "Teste", citations: [], confidence: 0.9 }} onAction={noop} />);
    expect(screen.queryByText("Dra. Ana")).not.toBeInTheDocument();
  });

  it("emits a typed action from availability", () => {
    const onAction = vi.fn();
    render(<ToolResultRenderer result={{
      type: "availability",
      total: 1,
      timezone: "America/Sao_Paulo",
      requested_from: "2030-01-10",
      requested_to: "2030-01-10",
      period: null,
      items: [{
        id: "slot-1",
        starts_at: "2030-01-10T12:00:00Z",
        ends_at: "2030-01-10T12:30:00Z",
        timezone: "America/Sao_Paulo",
        doctor: { id: "d1", name: "Dra. Ana" },
        unit: { id: "u1", name: "Centro" },
      }],
    }} onAction={onAction} />);
    fireEvent.click(screen.getByRole("button", { name: /Agendar/ }));
    expect(onAction).toHaveBeenCalledWith("create_appointment", expect.objectContaining({ doctor_id: "d1" }));
  });

  it("renders appointments and emits cancellation", () => {
    const onAction = vi.fn();
    render(<ToolResultRenderer result={{
      type: "appointments",
      total: 1,
      items: [{
        id: "a1", patient_id: "p1", doctor_id: "d1", doctor: "Dra. Ana", unit_id: "u1",
        unit: "Centro", starts_at: "2030-01-10T12:00:00Z", ends_at: "2030-01-10T12:30:00Z",
        status: "confirmed", reason: "Consulta",
      }],
    }} onAction={onAction} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(onAction).toHaveBeenCalledWith("cancel_appointment", { appointment_id: "a1" });
  });

  it.each(["appointment_created", "appointment_cancelled"] as const)("renders %s", (type) => {
    render(<ToolResultRenderer result={{
      type,
      appointment: {
        id: "a1", patient_id: "p1", doctor_id: "d1", doctor: "Dra. Ana", unit_id: "u1",
        unit: "Centro", starts_at: "2030-01-10T12:00:00Z", ends_at: "2030-01-10T12:30:00Z",
        status: "confirmed", reason: "Consulta",
      },
    }} onAction={noop} />);
    expect(screen.getByText(/Operação concluída/)).toBeVisible();
  });
});
