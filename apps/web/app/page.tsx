import { ArrowRight, CalendarDays, Check, CreditCard, MessageCircle, ShieldCheck, Stethoscope } from "lucide-react";
import Link from "next/link";
import { PublicHeader } from "@/components/public-header";
import { DoctorDirectory } from "@/components/doctor-directory";

export default function Home() {
  return (
    <main>
      <PublicHeader />
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">Saúde com inteligência</p>
          <h1>Cuidado inteligente para uma vida mais plena.</h1>
          <p className="hero-lead">Encontre profissionais, tire dúvidas administrativas e agende sua consulta com clareza e segurança.</p>
          <div className="button-row">
            <Link className="button button-primary" href="/agendar"><CalendarDays size={20} /> Agendar consulta</Link>
            <a className="button button-secondary" href="#especialidades"><Stethoscope size={20} /> Ver especialidades</a>
          </div>
          <p className="microcopy"><ShieldCheck size={16} /> Ambiente demonstrativo com dados totalmente sintéticos.</p>
        </div>
        <div className="hero-visual" aria-label="Ilustração abstrata de cuidado conectado">
          <div className="cobalt-plane" />
          <div className="care-orbit orbit-one"><Stethoscope /></div>
          <div className="care-orbit orbit-two"><CalendarDays /></div>
          <div className="care-orbit orbit-three"><MessageCircle /></div>
          <div className="care-core"><span>A</span><small>assistência<br />administrativa</small></div>
        </div>
      </section>

      <section className="benefit-strip" aria-label="Benefícios">
        <article><ShieldCheck /><div><strong>Informações verificadas</strong><p>Respostas ancoradas na base aprovada da clínica.</p></div></article>
        <article><CalendarDays /><div><strong>Agendamento simples</strong><p>Horários reais e confirmação antes de reservar.</p></div></article>
        <article><CreditCard /><div><strong>Seu convênio em foco</strong><p>Encontre opções compatíveis com sua cobertura.</p></div></article>
      </section>

      <section className="editorial-section" id="especialidades">
        <div className="section-number">01</div>
        <div className="section-heading">
          <p className="eyebrow">Especialidades</p>
          <h2>Comece pelo cuidado que você procura.</h2>
          <p>Cardiologia, pediatria e uma rede em evolução. A Alyvo cruza especialidade, unidade e convênio sem inventar informações.</p>
        </div>
        <div className="service-list">
          {["Cardiologia", "Pediatria", "Clínica geral"].map((name, index) => (
            <Link key={name} href="/chat" className="service-row"><span>0{index + 1}</span><strong>{name}</strong><ArrowRight /></Link>
          ))}
        </div>
      </section>

      <section className="editorial-section professionals" id="profissionais">
        <div className="section-number">02</div>
        <div className="section-heading">
          <p className="eyebrow">Profissionais</p>
          <h2>Uma equipe próxima, com agenda transparente.</h2>
        </div>
        <DoctorDirectory />
      </section>

      <section className="closing-cta" id="convenios">
        <p className="eyebrow">Alyvo assistente</p>
        <h2>Uma dúvida administrativa pode começar aqui.</h2>
        <p>Pergunte sobre médicos, convênios, unidades, documentos e preparo administrativo.</p>
        <Link className="button button-primary" href="/chat">Iniciar conversa <ArrowRight size={20} /></Link>
      </section>

      <footer className="footer"><strong>Alyvo</strong><span>Projeto de portfólio · dados sintéticos · sem orientação clínica</span><span id="unidades"><Check size={15} /> Unidade Centro · Unidade Sul</span></footer>
      <Link href="/chat" className="chat-launcher"><MessageCircle size={19} /> Fale com a Alyvo</Link>
    </main>
  );
}

