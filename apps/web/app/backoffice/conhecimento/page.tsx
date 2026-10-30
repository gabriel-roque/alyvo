"use client";

import { BookOpen, Check, FileText, Network, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { apiFetch, backofficeGet } from "@/lib/api";

type Ingestion = { id: string; title: string; status: string; preview: string; entities: { type: string; name: string }[] };

export default function KnowledgePage() {
  const [items, setItems] = useState<Ingestion[]>([]);
  const [selected, setSelected] = useState<Ingestion | null>(null);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const result = await backofficeGet("/ingestions");
    setItems(result.items);
    setSelected((current) => result.items.find((item: Ingestion) => item.id === current?.id) ?? result.items[0] ?? null);
  }, []);
  useEffect(() => {
    queueMicrotask(() => void load().catch(() => setMessage("Entre como administrador para gerenciar o conhecimento.")));
  }, [load]);

  async function upload(file: File) {
    const body = new FormData();
    body.append("file", file);
    body.append("title", file.name.replace(/\.[^.]+$/, ""));
    const response = await apiFetch("/backoffice/ingestions/upload", { method: "POST", body });
    if (!response.ok) { setMessage((await response.json()).detail ?? "Falha no upload"); return; }
    setMessage("Documento enviado. O worker está extraindo texto e entidades.");
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await load();
  }

  async function review(action: "approve" | "reject") {
    if (!selected) return;
    const response = await apiFetch(`/backoffice/ingestions/${selected.id}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: action === "approve" ? JSON.stringify({ entities: selected.entities ?? [], confirmed: true }) : undefined });
    if (!response.ok) { setMessage((await response.json()).detail ?? "Não foi possível concluir a revisão"); return; }
    setMessage(action === "approve" ? "Conhecimento aprovado e enviado para projeção no Neo4j." : "Ingestão rejeitada sem alterar o conhecimento publicado.");
    await load();
  }

  return <main className="backoffice-shell"><Sidebar active="Conhecimento" /><section className="backoffice-main knowledge-page"><header className="review-heading"><div><p className="eyebrow">Conhecimento institucional</p><h1>Ingestão e publicação</h1><p>Nenhum documento chega ao GraphRAG antes de revisão administrativa.</p></div><label className="button button-primary"><Upload /> Enviar documento<input hidden type="file" accept="application/pdf,text/plain,text/markdown,image/png,image/jpeg" onChange={(event) => event.target.files?.[0] && void upload(event.target.files[0])} /></label></header>{message && <div className="info-box" role="status">{message}</div>}<div className="ingestion-grid"><article className="panel entities-panel"><header><span>01</span> Fila de ingestões</header>{items.map((item) => <button className={selected?.id === item.id ? "selected ingestion-row" : "ingestion-row"} onClick={() => setSelected(item)} key={item.id}><FileText /><span><strong>{item.title}</strong><small>{item.status}</small></span></button>)}</article>{selected && <><article className="panel document-panel"><header><span>02</span> Prévia</header><div className="file-meta"><BookOpen /><div><strong>{selected.title}</strong><small>{selected.status}</small></div></div><p className="knowledge-preview">{selected.preview || "Processamento em andamento…"}</p></article><aside className="panel graph-panel"><header><span>03</span> Publicação</header><div className="graph-canvas"><Network size={64} /><strong>{selected.entities?.length ?? 0} entidades identificadas</strong><p>A projeção cria documento, chunks, embeddings e relacionamentos isolados por clínica.</p></div>{selected.status === "review_required" && <div className="confirmation-actions"><button className="button button-secondary" onClick={() => review("reject")}><Trash2 /> Rejeitar</button><button className="button button-primary" onClick={() => review("approve")}><Check /> Aprovar e publicar</button></div>}</aside></>}</div></section></main>;
}
