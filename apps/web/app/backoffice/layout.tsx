"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";

export default function BackofficeLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/backoffice/login") return children;

  return (
    <main className="backoffice-shell">
      <Sidebar />
      <section className="backoffice-main">{children}</section>
    </main>
  );
}
