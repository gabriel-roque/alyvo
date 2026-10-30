"use client";

import { Database, Pencil, Plus, Save, Trash2 } from "lucide-react";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { apiFetch, backofficeGet } from "@/lib/api";

const sections: Record<string, { title: string; endpoint?: string; catalog?: string }> = {
  agendamentos: { title: "Agendamentos", endpoint: "/agenda" }, pacientes: { title: "Pacientes", endpoint: "/patients" }, documentos: { title: "Documentos de pacientes", endpoint: "/patient-documents" }, tickets: { title: "Tickets", endpoint: "/tickets" }, medicos: { title: "Médicos", endpoint: "/doctors" }, especialidades: { title: "Especialidades", endpoint: "/catalog/specialties", catalog: "specialties" }, convenios: { title: "Convênios", endpoint: "/catalog/insurers", catalog: "insurers" }, unidades: { title: "Unidades", endpoint: "/catalog/units", catalog: "units" }, exames: { title: "Exames", endpoint: "/catalog/exams", catalog: "exams" }, servicos: { title: "Serviços", endpoint: "/catalog/services", catalog: "services" }, grafo: { title: "Explorador do grafo", endpoint: "/graph" }, auditoria: { title: "Auditoria", endpoint: "/audit" }, configuracoes: { title: "Configurações" },
};

export default function BackofficeSectionPage() {
  const { section } = useParams<{ section: string }>();
  const definition = sections[section] ?? { title: "Módulo" };
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [edges, setEdges] = useState<Record<string, unknown>[]>([]);
  const [name, setName] = useState(""); const [crm, setCrm] = useState(""); const [specialtyId, setSpecialtyId] = useState(""); const [unitId, setUnitId] = useState(""); const [insurerId, setInsurerId] = useState("");
  const [editingId, setEditingId] = useState<string>();
  const [catalogs, setCatalogs] = useState<Record<string, Record<string, unknown>[]>>({});
  const [clinic, setClinic] = useState({ name: "", timezone: "America/Sao_Paulo", cancellation_notice_hours: 0 });
  const [user, setUser] = useState({ name: "", email: "", role: "receptionist", password: "" });
  const [graphFilter, setGraphFilter] = useState(""); const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      if (section === "configuracoes") {
        const [clinicData, users] = await Promise.all([backofficeGet("/clinic"), backofficeGet("/users")]);
        setClinic({ name: clinicData.name, timezone: clinicData.timezone, cancellation_notice_hours: clinicData.cancellation_notice_hours }); setItems(users.items); return;
      }
      if (!definition.endpoint) return;
      const separator = definition.endpoint.includes("?") ? "&" : "?";
      const payload = await backofficeGet(`${definition.endpoint}${section === "grafo" && graphFilter ? `${separator}entity_type=${graphFilter}` : ""}`);
      setItems(payload.items ?? payload.nodes ?? []); setEdges(payload.edges ?? []);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao carregar o módulo"); }
  }, [definition.endpoint, graphFilter, section]);
  useEffect(() => { queueMicrotask(() => void load()); }, [load]);
  useEffect(() => {
    if (section !== "medicos" && section !== "servicos" && section !== "exames") return;
    queueMicrotask(() => void Promise.all([backofficeGet("/catalog/specialties"), backofficeGet("/catalog/units"), backofficeGet("/catalog/insurers")]).then(([specialties, units, insurers]) => { setCatalogs({ specialties: specialties.items, units: units.items, insurers: insurers.items }); setSpecialtyId(String(specialties.items[0]?.id ?? "")); setUnitId(String(units.items[0]?.id ?? "")); setInsurerId(String(insurers.items[0]?.id ?? "")); }));
  }, [section]);

  async function save(event: FormEvent) {
    event.preventDefault(); if (!name) return;
    const doctor = section === "medicos"; if (!doctor && !definition.catalog) return;
    const payload = doctor ? { name, crm, specialty_id: specialtyId, unit_id: unitId, insurer_ids: insurerId ? [insurerId] : [] } : { name, description: "", address: section === "unidades" ? "Endereço a definir" : "", specialty_id: section === "servicos" ? specialtyId : null, unit_ids: section === "exames" && unitId ? [unitId] : [], duration_minutes: 30 };
    const path = doctor ? `/backoffice/doctors${editingId ? `/${editingId}` : ""}` : `/backoffice/catalog/${definition.catalog}${editingId ? `/${editingId}` : ""}`;
    const response = await apiFetch(path, { method: editingId ? (doctor ? "PUT" : "PATCH") : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) { setError((await response.json()).detail ?? "Não foi possível salvar"); return; }
    setName(""); setCrm(""); setEditingId(undefined); await load();
  }

  function edit(item: Record<string, unknown>) { setEditingId(String(item.id)); setName(String(item.name ?? "")); setCrm(String(item.crm ?? "")); setSpecialtyId(String(item.specialty_id ?? specialtyId)); setUnitId(String(item.unit_id ?? unitId)); setInsurerId(String((item.insurer_ids as string[] | undefined)?.[0] ?? insurerId)); }
  async function remove(id: string) { if (!window.confirm("Confirma a exclusão?")) return; const path = section === "medicos" ? `/backoffice/doctors/${id}` : `/backoffice/catalog/${definition.catalog}/${id}`; const response = await apiFetch(path, { method: "DELETE" }); if (!response.ok) { setError((await response.json()).detail ?? "Não foi possível excluir"); return; } await load(); }
  async function ticketStatus(id: string, status: string) { await apiFetch(`/backoffice/tickets/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }); await load(); }
  async function saveClinic(event: FormEvent) { event.preventDefault(); await apiFetch("/backoffice/clinic", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(clinic) }); await load(); }
  async function createUser(event: FormEvent) { event.preventDefault(); const response = await apiFetch("/backoffice/users", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(user) }); if (!response.ok) { setError((await response.json()).detail ?? "Não foi possível criar usuário"); return; } setUser({ name: "", email: "", role: "receptionist", password: "" }); await load(); }
  async function removeUser(id: string) { await apiFetch(`/backoffice/users/${id}`, { method: "DELETE" }); await load(); }

  const mutable = Boolean(definition.catalog || section === "medicos");
  const columns = items.length ? Object.keys(items[0]).filter((key) => !["metadata", "fields", "insurer_ids", "embedding"].includes(key)).slice(0, 7) : [];
  return <main className="backoffice-shell"><Sidebar active={definition.title} /><section className="backoffice-main"><header className="page-heading"><p className="eyebrow">Backoffice</p><h1>{definition.title}</h1><p>Informações operacionais isoladas por clínica.</p></header>
    {mutable && <form className="inline-form panel" onSubmit={save}><label>Nome<input value={name} onChange={(event) => setName(event.target.value)} required /></label>{section === "medicos" && <label>CRM<input value={crm} onChange={(event) => setCrm(event.target.value)} required /></label>}{["medicos", "servicos"].includes(section) && <label>Especialidade<select value={specialtyId} onChange={(event) => setSpecialtyId(event.target.value)}>{catalogs.specialties?.map((item) => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}</select></label>}{["medicos", "exames"].includes(section) && <label>Unidade<select value={unitId} onChange={(event) => setUnitId(event.target.value)}>{catalogs.units?.map((item) => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}</select></label>}{section === "medicos" && <label>Convênio<select value={insurerId} onChange={(event) => setInsurerId(event.target.value)}>{catalogs.insurers?.map((item) => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}</select></label>}<button className="button button-primary" type="submit">{editingId ? <Save /> : <Plus />} {editingId ? "Salvar" : "Cadastrar"}</button></form>}
    {section === "configuracoes" && <><form className="inline-form panel" onSubmit={saveClinic}><label>Nome da clínica<input value={clinic.name} onChange={(event) => setClinic((current) => ({ ...current, name: event.target.value }))} /></label><label>Fuso horário<input value={clinic.timezone} onChange={(event) => setClinic((current) => ({ ...current, timezone: event.target.value }))} /></label><label>Antecedência para cancelar (horas)<input type="number" min="0" value={clinic.cancellation_notice_hours} onChange={(event) => setClinic((current) => ({ ...current, cancellation_notice_hours: Number(event.target.value) }))} /></label><button className="button button-primary"><Save /> Salvar clínica</button></form><form className="inline-form panel" onSubmit={createUser}><label>Nome<input value={user.name} onChange={(event) => setUser((current) => ({ ...current, name: event.target.value }))} required /></label><label>E-mail<input type="email" value={user.email} onChange={(event) => setUser((current) => ({ ...current, email: event.target.value }))} required /></label><label>Perfil<select value={user.role} onChange={(event) => setUser((current) => ({ ...current, role: event.target.value }))}><option value="receptionist">Recepção</option><option value="admin">Administrador</option></select></label><label>Senha<input type="password" value={user.password} onChange={(event) => setUser((current) => ({ ...current, password: event.target.value }))} required /></label><button className="button button-primary"><Plus /> Criar usuário</button></form></>}
    {section === "grafo" && <div className="panel graph-toolbar"><label>Filtrar entidade<select value={graphFilter} onChange={(event) => setGraphFilter(event.target.value)}><option value="">Todas</option>{["Clinic", "Doctor", "Specialty", "Unit", "Insurer", "Exam", "Service", "Document", "Chunk"].map((item) => <option key={item}>{item}</option>)}</select></label><span>Somente leitura · {items.length} nós · {edges.length} relações</span></div>}
    {error && <p role="alert" className="error-text">{error}</p>}
    {(definition.endpoint || section === "configuracoes") && <div className="panel table-wrap">{items.length === 0 ? <div className="data-empty"><Database /><p>Nenhum registro encontrado.</p></div> : <table><thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}{(mutable || section === "tickets" || section === "configuracoes") && <th>Ações</th>}</tr></thead><tbody>{items.map((item, index) => <tr key={String(item.id ?? index)}>{columns.map((column) => <td key={column}>{typeof item[column] === "object" ? JSON.stringify(item[column]) : String(item[column] ?? "—")}</td>)}{mutable && <td className="table-actions"><button aria-label="Editar" onClick={() => edit(item)}><Pencil /></button><button aria-label="Excluir" onClick={() => void remove(String(item.id))}><Trash2 /></button></td>}{section === "tickets" && <td><select value={String(item.status)} onChange={(event) => void ticketStatus(String(item.id), event.target.value)}><option value="open">Aberto</option><option value="in_progress">Em atendimento</option><option value="resolved">Resolvido</option></select></td>}{section === "configuracoes" && <td><button aria-label="Excluir usuário" onClick={() => void removeUser(String(item.id))}><Trash2 /></button></td>}</tr>)}</tbody></table>}</div>}
    {section === "grafo" && edges.length > 0 && <div className="panel graph-relations"><h2>Relacionamentos</h2>{edges.slice(0, 100).map((edge, index) => <code key={`${String(edge.source)}-${String(edge.target)}-${index}`}>{String(edge.source)} —[{String(edge.type)}]→ {String(edge.target)}</code>)}</div>}
  </section></main>;
}
