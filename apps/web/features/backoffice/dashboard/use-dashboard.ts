"use client";

import { useEffect, useState } from "react";
import { getDashboard } from "@/lib/api";

type Dashboard = Awaited<ReturnType<typeof getDashboard>>;

export function useDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    void getDashboard().then(setData).catch(() => setError("Entre com uma conta da equipe para continuar."));
  }, []);
  return { data, error };
}
