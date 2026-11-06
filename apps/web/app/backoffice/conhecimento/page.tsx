"use client";

import { BookOpen, Check, FileText, Network, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  listKnowledgeDocuments,
  publishKnowledge,
  rejectKnowledge,
  uploadKnowledge,
} from "@/features/backoffice/knowledge/api";
import type { KnowledgeDocument as Ingestion } from "@/lib/api";


export default function KnowledgePage() {
  const [items, setItems] = useState<Ingestion[]>([]);
  const [selected, setSelected] = useState<Ingestion | null>(null);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    const result = await listKnowledgeDocuments();
    setItems(result.items);
    setSelected((current) => result.items.find((item) => item.id === current?.id) ?? result.items[0] ?? null);
  }, []);
  useEffect(() => {
    queueMicrotask(() => void load().catch(() => setMessage("Entre como administrador para gerenciar o conhecimento.")));
  }, [load]);

  async function upload(file: File) {
    await uploadKnowledge(file);
    setMessage("Documento enviado. O worker está extraindo texto e entidades.");
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await load();
  }

  async function review(action: "approve" | "reject") {
    if (!selected) return;
    if (action === "approve") await publishKnowledge(selected.id, selected.entities ?? []);
    else await rejectKnowledge(selected.id);
    setMessage(action === "approve" ? "Conhecimento aprovado e enviado para projeção no Neo4j." : "Documento rejeitado sem alterar o conhecimento publicado.");
    await load();
  }

  return <section className="knowledge-page"><header className="review-heading"><div><p className="eyebrow">Conhecimento institucional</p><h1>Ingestão e publicação</h1><p>Nenhum documento chega ao GraphRAG antes de revisão administrativa.</p></div><label className="button button-primary"><Upload /> Enviar documento<input hidden type="file" accept="application/pdf,text/plain,text/markdown,image/png,image/jpeg" onChange={(event) => event.target.files?.[0] && void upload(event.target.files[0])} /></label></header>{message && <div className="info-box" role="status">{message}</div>}<div className="ingestion-grid"><article className="panel entities-panel"><header><span>01</span> Fila de ingestões</header>{items.map((item) => <button className={selected?.id === item.id ? "selected ingestion-row" : "ingestion-row"} onClick={() => setSelected(item)} key={item.id}><FileText /><span><strong>{item.title}</strong><small>{item.status} · grafo {item.sync_status}</small></span></button>)}</article>{selected && <><article className="panel document-panel"><header><span>02</span> Prévia</header><div className="file-meta"><BookOpen /><div><strong>{selected.title}</strong><small>{selected.status} · sincronização {selected.sync_status}</small></div></div><p className="knowledge-preview">{selected.preview || "Processamento em andamento…"}</p></article><aside className="panel graph-panel"><header><span>03</span> Publicação</header><div className="graph-canvas"><Network size={64} /><strong>{selected.entities?.length ?? 0} entidades identificadas</strong><p>A projeção cria documento, chunks, embeddings e relacionamentos da clínica.</p></div>{selected.status === "review_required" && <div className="confirmation-actions"><button className="button button-secondary" onClick={() => review("reject")}><Trash2 /> Rejeitar</button><button className="button button-primary" onClick={() => review("approve")}><Check /> Aprovar e publicar</button></div>}</aside></>}</div></section>;
}
