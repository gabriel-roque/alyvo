import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Alyvo — Cuidado inteligente",
  description: "Assistente administrativo multimodal para clínicas, com dados demonstrativos sintéticos.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}

