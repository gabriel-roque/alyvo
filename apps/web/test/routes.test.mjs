import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const routes = [
  ["app/page.tsx", "Cuidado inteligente"],
  ["app/chat/page.tsx", "Fontes consultadas"],
  ["app/agendar/page.tsx", "Confirmar agendamento"],
  ["app/documentos/revisao/page.tsx", "Confirmar e salvar"],
  ["app/backoffice/agenda/page.tsx", "Pendências"],
  ["app/backoffice/conhecimento/page.tsx", "Aprovar e publicar"],
];

for (const [route, marker] of routes) {
  test(`${route} exposes its critical user action`, async () => {
    const source = await readFile(new URL(`../${route}`, import.meta.url), "utf8");
    assert.match(source, new RegExp(marker, "i"));
  });
}

test("design tokens preserve the Editorial Premium palette", async () => {
  const css = await readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  for (const token of ["#f7f7f2", "#101828", "#2457ff", "#b8f34a", "#d8dde6"]) {
    assert.ok(css.includes(token), `missing design token ${token}`);
  }
});

