"use client";

import { LockKeyhole } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Brand } from "@/components/brand";
import { staffLogin } from "@/lib/api";

export default function BackofficeLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@alyvo.local");
  const [password, setPassword] = useState("alyvo-demo");
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await staffLogin(email, password);
      router.push("/backoffice");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha no login");
    }
  }

  return <main className="login-page"><form className="panel auth-panel" onSubmit={submit}><Brand /><LockKeyhole /><p className="eyebrow">Equipe da clínica</p><h1>Entrar no backoffice</h1><label>E-mail<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label><label>Senha<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>{error && <p role="alert" className="error-text">{error}</p>}<button className="button button-primary" type="submit">Entrar</button></form></main>;
}
