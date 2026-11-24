import { ArrowRight, MessageCircle, ShieldCheck } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { Brand } from "@/components/brand";

export default function Home() {
  return (
    <main className="landing">
      <header className="landing-header">
        <Brand />
        <Link className="button button-primary compact" href="/backoffice/login">
          Backoffice
        </Link>
      </header>
      <section className="landing-hero">
        <div className="landing-copy">
          <p className="eyebrow">Assistente administrativo de saúde</p>
          <h1>Cuidado inteligente começa com uma conversa simples.</h1>
          <p>
            Tire dúvidas sobre médicos, convênios, exames e horários. Quando
            precisar acessar seus dados, a Alyvo pedirá sua identificação com
            segurança.
          </p>
          <Link className="button button-primary landing-cta" href="/chat">
            <MessageCircle size={20} /> Conversar com a Alyvo <ArrowRight size={18} />
          </Link>
          <span className="landing-trust">
            <ShieldCheck size={17} /> Informações administrativas baseadas na clínica.
          </span>
        </div>
        <div className="landing-art" aria-hidden="true">
          <span className="art-orbit art-one"><MessageCircle /></span>
          <span className="art-orbit art-two"><ShieldCheck /></span>
          <Image
            className="landing-illustration"
            src="/alyvo-hero-clinician.png"
            alt=""
            width={1392}
            height={1130}
            sizes="(max-width: 900px) 82vw, 45vw"
            priority
          />
        </div>
      </section>
    </main>
  );
}
