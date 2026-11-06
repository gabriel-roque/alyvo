import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const routes = [
  ["app/page.tsx", "Conversar com a Alyvo"],
  ["app/chat/page.tsx", "Conversa anônima"],
  ["app/agendar/page.tsx", "permanentRedirect"],
  ["app/backoffice/page.tsx", "revisões de conhecimento"],
  ["app/backoffice/agenda/page.tsx", "Horários recorrentes"],
  ["app/backoffice/conhecimento/page.tsx", "Aprovar e publicar"],
  ["app/backoffice/[section]/page.tsx", "Registro arquivado"],
];

for (const [route, marker] of routes) {
  test(`${route} exposes its critical user action`, async () => {
    const source = await readFile(new URL(`../${route}`, import.meta.url), "utf8");
    assert.match(source, new RegExp(marker, "i"));
  });
}

test("design tokens preserve the Alyvo palette and reduced motion", async () => {
  const files = ["../app/globals.css", "../styles/tokens.css", "../styles/base.css"];
  const css = (await Promise.all(files.map((file) => readFile(new URL(file, import.meta.url), "utf8")))).join("\n");
  for (const token of ["#f7f7f2", "#101828", "#2457ff", "#b8f34a", "#d8dde6", "prefers-reduced-motion"]) {
    assert.ok(css.includes(token), `missing design token ${token}`);
  }
});
