"use client";

import { Archive, Check, ChevronRight, Pencil, Plus, Search, X } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { backofficeGet, backofficeMutate } from "@/lib/api";

type Item = Record<string, unknown> & { id: string; name?: string; active?: boolean };
type Definition = { title: string; endpoint: string; kind?: string; description: string };

const definitions: Record<string, Definition> = {
  medicos: { title: "Médicos", endpoint: "/doctors", description: "Profissionais, especialidades, unidades e convênios." },
  especialidades: { title: "Especialidades", endpoint: "/catalog/specialties", kind: "specialties", description: "Áreas de atendimento disponíveis na clínica." },
  convenios: { title: "Convênios", endpoint: "/catalog/insurers", kind: "insurers", description: "Operadoras aceitas pelos profissionais." },
  exames: { title: "Exames", endpoint: "/catalog/exams", kind: "exams", description: "Exames, preparos e unidades de realização." },
  unidades: { title: "Unidades", endpoint: "/catalog/units", kind: "units", description: "Locais de atendimento da clínica." },
  pacientes: { title: "Pacientes", endpoint: "/patients", description: "Consulta segura dos pacientes identificados." },
};

const blank = { name: "", crm: "", specialty_id: "", unit_id: "", insurer_ids: [] as string[], description: "", address: "", preparation: "", unit_ids: [] as string[], active: true };

export default function BackofficeSectionPage() {
  const { section } = useParams<{ section: string }>();
  const router = useRouter();
  const definition = definitions[section];
  const [items, setItems] = useState<Item[]>([]);
  const [catalogs, setCatalogs] = useState<Record<string, Item[]>>({});
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [editing, setEditing] = useState<Item | null>(null);
  const [archive, setArchive] = useState<Item | null>(null);
  const [form, setForm] = useState(blank);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!definition) return;
    setLoading(true);
    setError("");
    try {
      const result = await backofficeGet(`${definition.endpoint}?q=${encodeURIComponent(query)}&include_inactive=true`);
      setItems(result.items as Item[]);
      if (section === "medicos" || section === "exames") {
        const [specialties, units, insurers] = await Promise.all([
          backofficeGet("/catalog/specialties"),
          backofficeGet("/catalog/units"),
          backofficeGet("/catalog/insurers"),
        ]);
        setCatalogs({ specialties: specialties.items as Item[], units: units.items as Item[], insurers: insurers.items as Item[] });
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível carregar os dados.");
    } finally {
      setLoading(false);
    }
  }, [definition, query, section]);

  useEffect(() => { if (!definition) router.replace("/backoffice"); else queueMicrotask(() => void load()); }, [definition, load, router]);

  function open(item?: Item) {
    setEditing(item ?? null);
    setForm(item ? {
      ...blank,
      name: String(item.name ?? ""),
      crm: String(item.crm ?? ""),
      specialty_id: String(item.specialty_id ?? ""),
      unit_id: String(item.unit_id ?? ""),
      insurer_ids: (item.insurer_ids as string[] | undefined) ?? [],
      description: String(item.description ?? ""),
      address: String(item.address ?? ""),
      preparation: String(item.preparation ?? ""),
      unit_ids: (item.unit_ids as string[] | undefined) ?? [],
      active: Boolean(item.active ?? true),
    } : { ...blank, specialty_id: catalogs.specialties?.[0]?.id ?? "", unit_id: catalogs.units?.[0]?.id ?? "" });
    setDrawer(true);
    setMessage("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!definition || section === "pacientes") return;
    setSaving(true);
    setError("");
    try {
      const path = section === "medicos"
        ? `/doctors${editing ? `/${editing.id}` : ""}`
        : `/catalog/${definition.kind}${editing ? `/${editing.id}` : ""}`;
      const payload = section === "medicos"
        ? { name: form.name, crm: form.crm, specialty_id: form.specialty_id, unit_id: form.unit_id, insurer_ids: form.insurer_ids, active: form.active }
        : { name: form.name, description: form.description, address: form.address, preparation: form.preparation, unit_ids: form.unit_ids, active: form.active };
      await backofficeMutate(path, { method: editing ? (section === "medicos" ? "PUT" : "PATCH") : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setDrawer(false);
      setMessage(editing ? "Alterações salvas." : "Cadastro criado.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar.");
    } finally {
      setSaving(false);
    }
  }

  async function confirmArchive() {
    if (!archive || !definition) return;
    setSaving(true);
    try {
      const path = section === "medicos" ? `/doctors/${archive.id}` : `/catalog/${definition.kind}/${archive.id}`;
      await backofficeMutate(path, { method: "DELETE" });
      setArchive(null);
      setMessage("Registro arquivado. O histórico foi preservado.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível arquivar.");
    } finally {
      setSaving(false);
    }
  }

  const columns = useMemo(() => {
    if (section === "medicos") return ["Profissional", "CRM", "Especialidade", "Unidade", "Convênios", "Situação"];
    if (section === "especialidades") return ["Especialidade", "Descrição", "Situação"];
    if (section === "convenios") return ["Convênio", "Situação"];
    if (section === "exames") return ["Exame", "Preparo", "Unidades", "Situação"];
    if (section === "unidades") return ["Unidade", "Endereço", "Situação"];
    return ["Paciente", "CPF", "Nascimento", "E-mail", "Cadastro"];
  }, [section]);

  if (!definition) return null;

  function cells(item: Item) {
    if (section === "medicos") return [item.name, item.crm, item.specialty, item.unit, (item.insurers as string[] | undefined)?.join(", ") || "—", item.active ? "Ativo" : "Arquivado"];
    if (section === "especialidades") return [item.name, item.description || "—", item.active ? "Ativa" : "Arquivada"];
    if (section === "convenios") return [item.name, item.active ? "Ativo" : "Arquivado"];
    if (section === "exames") return [item.name, item.preparation || "Sem preparo informado", `${(item.unit_ids as string[] | undefined)?.length ?? 0} unidade(s)`, item.active ? "Ativo" : "Arquivado"];
    if (section === "unidades") return [item.name, item.address || "—", item.active ? "Ativa" : "Arquivada"];
    return [item.name, item.cpf, item.birth_date ? new Date(String(item.birth_date) + "T12:00:00").toLocaleDateString("pt-BR") : "Não informado", item.email, new Date(String(item.created_at)).toLocaleDateString("pt-BR")];
  }

  return (
    <>
      <section>
        <header className="resource-heading">
          <div><p className="eyebrow">{section === "pacientes" ? "Operação" : "Cadastros"}</p><h1>{definition.title}</h1><p>{definition.description}</p></div>
          {section !== "pacientes" && <button className="button button-primary" onClick={() => open()}><Plus /> Novo cadastro</button>}
        </header>
        <div className="resource-toolbar">
          <label className="search-field"><Search /><span className="sr-only">Buscar</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`Buscar em ${definition.title.toLowerCase()}…`} /></label>
          <span>{items.length} registro(s)</span>
        </div>
        {message && <div className="success-banner" role="status"><Check /> {message}</div>}
        {error && <p className="error-text" role="alert">{error}</p>}
        {loading ? <div className="table-skeleton">{Array.from({ length: 6 }).map((_, index) => <i key={index} />)}</div> : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}<th><span className="sr-only">Ações</span></th></tr></thead>
              <tbody>{items.map((item) => <tr key={item.id}>{cells(item).map((cell, index) => <td key={columns[index]}>{String(cell ?? "—")}</td>)}<td className="row-actions">{section === "pacientes" ? <button aria-label={`Ver ${item.name}`} onClick={() => open(item)}><ChevronRight /></button> : <><button aria-label={`Editar ${item.name}`} onClick={() => open(item)}><Pencil /></button>{item.active && <button aria-label={`Arquivar ${item.name}`} onClick={() => setArchive(item)}><Archive /></button>}</>}</td></tr>)}</tbody>
            </table>
            {!items.length && <div className="data-empty"><Search /><strong>Nenhum registro encontrado</strong><p>Tente ajustar sua busca.</p></div>}
          </div>
        )}
      </section>

      {drawer && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDrawer(false); }}><aside className="side-dialog" role="dialog" aria-modal="true" aria-labelledby="drawer-title"><header><div><p className="eyebrow">{section === "pacientes" ? "Detalhes" : editing ? "Editar" : "Novo"}</p><h2 id="drawer-title">{section === "pacientes" ? editing?.name : definition.title}</h2></div><button className="icon-button" aria-label="Fechar" onClick={() => setDrawer(false)}><X /></button></header>
        {section === "pacientes" && editing ? <dl className="patient-details">{cells(editing).map((value, index) => <div key={columns[index]}><dt>{columns[index]}</dt><dd>{String(value)}</dd></div>)}</dl> :
        <form className="drawer-form" onSubmit={save}>
          <label>Nome<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
          {section === "medicos" && <><label>CRM<input required value={form.crm} onChange={(event) => setForm({ ...form, crm: event.target.value })} /></label><label>Especialidade<select value={form.specialty_id} onChange={(event) => setForm({ ...form, specialty_id: event.target.value })}>{catalogs.specialties?.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><label>Unidade<select value={form.unit_id} onChange={(event) => setForm({ ...form, unit_id: event.target.value })}>{catalogs.units?.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label><fieldset><legend>Convênios</legend>{catalogs.insurers?.map((item) => <label className="check-field" key={item.id}><input type="checkbox" checked={form.insurer_ids.includes(item.id)} onChange={(event) => setForm({ ...form, insurer_ids: event.target.checked ? [...form.insurer_ids, item.id] : form.insurer_ids.filter((id) => id !== item.id) })} />{item.name}</label>)}</fieldset></>}
          {section === "especialidades" && <label>Descrição<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>}
          {section === "unidades" && <label>Endereço<input value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></label>}
          {section === "exames" && <><label>Preparo<textarea value={form.preparation} onChange={(event) => setForm({ ...form, preparation: event.target.value })} /></label><fieldset><legend>Unidades</legend>{catalogs.units?.map((item) => <label className="check-field" key={item.id}><input type="checkbox" checked={form.unit_ids.includes(item.id)} onChange={(event) => setForm({ ...form, unit_ids: event.target.checked ? [...form.unit_ids, item.id] : form.unit_ids.filter((id) => id !== item.id) })} />{item.name}</label>)}</fieldset></>}
          <label className="check-field"><input type="checkbox" checked={form.active} onChange={(event) => setForm({ ...form, active: event.target.checked })} />Cadastro ativo</label>
          <footer><button type="button" className="button button-secondary" onClick={() => setDrawer(false)}>Cancelar</button><button className="button button-primary" disabled={saving}>{saving ? "Salvando…" : "Salvar"}</button></footer>
        </form>}
      </aside></div>}

      {archive && <div className="dialog-backdrop"><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="archive-title"><span className="danger-icon"><Archive /></span><h2 id="archive-title">Arquivar {archive.name}?</h2><p>O registro deixará de aparecer nos fluxos ativos, mas o histórico será preservado.</p><div><button className="button button-secondary" onClick={() => setArchive(null)}>Cancelar</button><button className="button button-danger" disabled={saving} onClick={() => void confirmArchive()}>Arquivar</button></div></section></div>}
    </>
  );
}
