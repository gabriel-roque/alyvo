import { Menu } from "lucide-react";
import Link from "next/link";
import { Brand } from "./brand";

export function PublicHeader() {
  return (
    <header className="public-header">
      <Brand />
      <nav aria-label="Navegação principal" className="public-nav">
        <a href="#especialidades">Especialidades</a>
        <a href="#profissionais">Profissionais</a>
        <a href="#convenios">Convênios</a>
        <a href="#unidades">Unidades</a>
      </nav>
      <Link className="button button-primary compact" href="/chat">Falar com a Alyvo</Link>
      <button className="icon-button mobile-only" aria-label="Abrir menu"><Menu /></button>
    </header>
  );
}

