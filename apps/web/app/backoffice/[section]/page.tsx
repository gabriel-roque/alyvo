"use client";

import { Database, Plus } from "lucide-react";
import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { apiFetch, backofficeGet } from "@/lib/api";

const sections: Record<string, { title: string; endpoint?: string; catalog?: string }> = {
  agendamentos: { title: "Agendamentos", endpoint: "/agenda" },
  pacientes: { title: "Pacientes", endpoint: "/patients" },
  documentos: { title: "Documentos de pacientes", endpoint: "/patient-documents" },
  tickets: { title: "Tickets", endpoint: "/tickets" },
  medicos: { title: "Médicos", endpoint: "/doctors" },
  especialidades: { title: "Especialidades", endpoint: "/catalog/specialties", catalog: "specialties" },
  convenios: { title: "Convênios", endpoint: "/catalog/insurers", catalog: "insurers" },
  unidades: { title: "Unidades", endpoint: "/catalog/units", catalog: "units" },
  exames: { title: "Exames", endpoint: "/catalog/exams", catalog: "exams" },
  servicos: { title: "Serviços", endpoint: "/catalog/services", catalog: "services" },
  grafo: { title: "Explorador do grafo", endpoint: "/graph" },
  auditoria: { title: "Auditoria", endpoint: "/audit" },
  configuracoes: { title: "Configurações" },
};

export default function BackofficeSectionPage() {
  const { section } = useParams<{ section: string }>();
  const definition = sections[section] ?? { title: "Módulo" };
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [name, setName] = useState("");
  const [crm, setCrm] = useState("");
  const [specialtyId, setSpecialtyId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [insurerId, setInsurerId] = useState("");
  const [catalogs, setCatalogs] = useState<Record<string, Record<string, unknown>[]>>({});
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!definition.endpoint) return;
    try {
      const payload = await backofficeGet(definition.endpoint);
      setItems(payload.items ?? payload.nodes ?? []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao carregar o módulo");
    }
  }, [definition.endpoint]);
  useEffect(() => { queueMicrotask(() => void load()); }, [load]);
  useEffect(() => {
    if (section !== "medicos") return;
    queueMicrotask(() => void Promise.all([
      backofficeGet("/catalog/specialties"),
      backofficeGet("/catalog/units"),
      backofficeGet("/catalog/insurers"),
    ]).then(([specialties, units, insurers]) => {
      setCatalogs({ specialties: specialties.items, units: units.items, insurers: insurers.items });
      setSpecialtyId(String(specialties.items[0]?.id ?? ""));
      setUnitId(String(units.items[0]?.id ?? ""));
      setInsurerId(String(insurers.items[0]?.id ?? ""));
    }));
  }, [section]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name) return;
    const doctor = section === "medicos";
    if (!doctor && !definition.catalog) return;
    const response = await apiFetch(doctor ? "/backoffice/doctors" : `/backoffice/catalog/${definition.catalog}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(doctor
        ? { name, crm, specialty_id: specialtyId, unit_id: unitId, insurer_ids: insurerId ? [insurerId] : [] }
        : { name, description: "", address: "" }),
    });
    if (!response.ok) { setError((await response.json()).detail ?? "Não foi possível cadastrar"); return; }
    setName("");
    setCrm("");
    await load();
  }

  const columns = items.length ? Object.keys(items[0]).filter((key) => !["metadata", "fields", "insurer_ids"].includes(key)).slice(0, 6) : [];
  return <main className="backoffice-shell"><Sidebar active={definition.title} /><section className="backoffice-main"><header className="page-heading"><p className="eyebrow">Backoffice</p><h1>{definition.title}</h1><p>Informações operacionais isoladas por clínica.</p></header>{(definition.catalog || section === "medicos") && <form className="inline-form panel" onSubmit={create}><label>Nome<input value={name} onChange={(event) => setName(event.target.value)} required /></label>{section === "medicos" && <><label>CRM<input value={crm} onChange={(event) => setCrm(event.target.value)} required /></label><label>Especialidade<select value={specialtyId} onChange={(event) => setSpecialtyId(event.target.value)}>{catalogs.specialties?.map((item) => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}</select></label><label>Unidade<select value={unitId} onChange={(event) => setUnitId(event.target.value)}>{catalogs.units?.map((item) => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}</select></label><label>Convênio<select value={insurerId} onChange={(event) => setInsurerId(event.target.value)}>{catalogs.insurers?.map((item) => <option key={String(item.id)} value={String(item.id)}>{String(item.name)}</option>)}</select></label></>}<button className="button button-primary" type="submit"><Plus /> Cadastrar</button></form>}{section === "configuracoes" && <div className="panel data-empty"><Database /><h2>Ambiente local-first</h2><p>Ollama, PaddleOCR, BGE-M3, MinIO, Redis, PostgreSQL e Neo4j são configurados por variáveis de ambiente.</p></div>}{error && <p role="alert" className="error-text">{error}</p>}{definition.endpoint && <div className="panel table-wrap">{items.length === 0 ? <div className="data-empty"><Database /><p>Nenhum registro encontrado.</p></div> : <table><thead><tr>{columns.map((column) => <th key={column}>{column.replaceAll("_", " ")}</th>)}</tr></thead><tbody>{items.map((item, index) => <tr key={String(item.id ?? index)}>{columns.map((column) => <td key={column}>{typeof item[column] === "object" ? JSON.stringify(item[column]) : String(item[column] ?? "—")}</td>)}</tr>)}</tbody></table>}</div>}</section></main>;
}
