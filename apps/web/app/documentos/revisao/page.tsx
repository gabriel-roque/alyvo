"use client";

import { Check, FileCheck2, Info, ScanLine, ShieldCheck, Upload } from "lucide-react";
import { DragEvent, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { confirmPatientDocument, getPatientDocument, uploadPatientDocument } from "@/lib/api";

type Review = { id: string; filename: string; status: string; fields: Record<string, string>; confidence: Record<string, number>; file_url?: string };

export default function DocumentReviewPage() {
  const [review, setReview] = useState<Review | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState("");

  async function upload(file: File) {
    setMessage("Enviando e processando com OCR…");
    try {
      let item = await uploadPatientDocument(file, "insurance_card");
      for (let attempt = 0; attempt < 20 && ["uploaded", "processing"].includes(item.status); attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000));
        item = await getPatientDocument(item.id);
      }
      if (item.status !== "review_required") throw new Error("O documento não ficou pronto para revisão");
      setReview(item);
      setFields(item.fields);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha ao processar o documento");
    }
  }

  async function confirm() {
    if (!review) return;
    await confirmPatientDocument(review.id, fields);
    setSaved(true);
  }

  function drop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) void upload(file);
  }

  return <main className="backoffice-shell"><Sidebar active="Documentos" /><section className="backoffice-main">
    <header className="review-heading"><div><p className="eyebrow">Documento privado do paciente</p><h1>{saved ? "Documento confirmado" : "Revisar extração OCR"}</h1><p>O arquivo fica isolado por clínica e paciente e nunca entra no GraphRAG institucional.</p></div></header>
    {!review && !saved && <section className="panel upload-panel" onDragOver={(event) => event.preventDefault()} onDrop={drop}><Upload /><h2>Envie uma carteirinha sintética</h2><p>Arraste o arquivo ou selecione PNG, JPEG ou PDF, até 10 MB.</p><label className="button button-primary">Selecionar arquivo<input hidden type="file" accept="image/png,image/jpeg,application/pdf" onChange={(event) => event.target.files?.[0] && void upload(event.target.files[0])} /></label>{message && <p role="status">{message}</p>}</section>}
    {saved && <div className="success-state document-success"><span><FileCheck2 /></span><h2>Dados salvos com segurança.</h2><p>A recepção já pode consultar o documento confirmado.</p></div>}
    {review && !saved && <div className="review-grid">
      <article className="panel preview-panel"><header><span>01</span> Arquivo privado</header><div className="document-preview"><ScanLine size={56} /><strong>{review.filename}</strong><small>OCR concluído</small></div>{review.file_url && <a className="button button-secondary" href={review.file_url} target="_blank">Abrir original temporariamente</a>}</article>
      <article className="panel extracted-panel"><header><span>02</span> Dados extraídos <small>Edite se necessário</small></header><div className="field-stack">{Object.entries(fields).map(([key, value], index) => <label key={key}><span className="field-label"><b>{index + 1}</b><strong>{key}</strong><em className={(review.confidence[key] ?? 0) < .9 ? "warning" : ""}>{Math.round((review.confidence[key] ?? 0) * 100)}%</em></span><input value={value} onChange={(event) => setFields((current) => ({ ...current, [key]: event.target.value }))} /></label>)}</div></article>
      <aside className="panel confirmation-panel"><header><span>03</span> Confirmação</header><div className="info-box"><Info /><div><strong>Revise antes de persistir</strong><p>Nenhum campo extraído é confirmado automaticamente.</p></div></div><ul className="check-list"><li><Check /> Campos editáveis.</li><li><Check /> Disponível à recepção.</li><li><ShieldCheck /> Excluído do conhecimento institucional.</li></ul><button className="button button-primary" onClick={confirm}>Confirmar e salvar</button></aside>
    </div>}
  </section></main>;
}
