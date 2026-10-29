"use client";

import { Check, FileCheck2, Image as ImageIcon, Info, RotateCw, ScanLine, ShieldCheck, SunMedium } from "lucide-react";
import { useState } from "react";
import { Sidebar } from "@/components/sidebar";

const initial = { nome: "Juliana Silva", convenio: "Vida+", numero: "VIDA-102938", validade: "12/2027" };
const confidence = { nome: 98, convenio: 99, numero: 84, validade: 97 };

export default function DocumentReviewPage() {
  const [fields, setFields] = useState(initial);
  const [saved, setSaved] = useState(false);
  return (
    <main className="backoffice-shell"><Sidebar active="Documentos" /><section className="backoffice-main">
      <header className="review-heading"><div><p className="eyebrow">Processamento de documento</p><h1>{saved ? "Documento confirmado" : "Confirmar dados do documento"}</h1><p>Revise as informações extraídas pela Alyvo antes de salvar. Nada é persistido sem esta confirmação.</p></div><ol className="compact-steps"><li className="done"><Check />Enviado</li><li className="done"><Check />Processado</li><li className={saved ? "done" : "current"}>{saved ? <Check /> : "3"}Revisão</li><li className={saved ? "done" : ""}>{saved ? <Check /> : "4"}Salvo</li></ol></header>
      {saved ? <div className="success-state document-success"><span><FileCheck2 /></span><h2>Dados salvos com segurança.</h2><p>O documento confirmado está disponível para a recepção e nunca será incluído no conhecimento institucional.</p><button className="button button-secondary" onClick={() => setSaved(false)}>Voltar à revisão</button></div> : <div className="review-grid">
        <article className="panel preview-panel"><header><span>01</span> Prévia do documento <small><i /> OCR concluído</small></header><div className="insurance-card"><div className="card-mark"><span>+</span> Vida<strong>Mais</strong></div><small>Plano empresarial</small><div className="scan-field name"><b>1</b><label>Nome do beneficiário</label><strong>JULIANA SILVA</strong></div><div className="scan-field number"><b>3</b><label>Nº da carteirinha</label><strong>VIDA-102938</strong></div><div className="card-footer"><span>Convênio<strong>Vida+ Saúde</strong></span><span>Validade<strong>12/2027</strong></span></div></div><footer><button><RotateCw /> Girar</button><span>100%</span><button><ScanLine /> Tela cheia</button></footer></article>
        <article className="panel extracted-panel"><header><span>02</span> Dados extraídos (OCR) <small>Edite se necessário</small></header><div className="field-stack">{Object.entries(fields).map(([key, value], index) => <label key={key}><span className="field-label"><b>{index + 1}</b><strong>{key === "numero" ? "Número da carteirinha" : key[0].toUpperCase() + key.slice(1)}</strong><em className={confidence[key as keyof typeof confidence] < 90 ? "warning" : ""}>{confidence[key as keyof typeof confidence]}%</em></span><input value={value} onChange={(event) => setFields((items) => ({ ...items, [key]: event.target.value }))} />{confidence[key as keyof typeof confidence] < 90 && <small>Confira este campo antes de confirmar.</small>}</label>)}</div></article>
        <aside className="panel confirmation-panel"><header><span>03</span> Revisão e confirmação</header><div className="info-box"><Info /><div><strong>Revise os dados antes de salvar</strong><p>Você pode editar qualquer campo. O documento original permanece privado e isolado por clínica e paciente.</p></div></div><h3>Dicas para uma boa leitura</h3><ul><li><ImageIcon /> Use uma imagem nítida e sem reflexos.</li><li><SunMedium /> Prefira fotos com boa iluminação.</li><li><ScanLine /> Mantenha o documento completo.</li></ul><h3>O que acontece depois</h3><ul className="check-list"><li><Check /> Os campos são salvos no cadastro.</li><li><Check /> A recepção pode revisar as informações.</li><li><ShieldCheck /> O documento não entra no GraphRAG.</li></ul><div className="confirmation-actions"><button className="button button-secondary"><RotateCw /> Corrigir documento</button><button className="button button-primary" onClick={() => setSaved(true)}>Confirmar e salvar</button></div></aside>
      </div>}
    </section></main>
  );
}

