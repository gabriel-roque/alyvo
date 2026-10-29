import { expect, test } from "@playwright/test";

test("public home leads to scheduling", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Cuidado inteligente/i })).toBeVisible();
  await page.getByRole("link", { name: /Agendar consulta/i }).first().click();
  await expect(page.getByRole("heading", { name: "Agendar consulta" })).toBeVisible();
  await page.getByRole("button", { name: /Confirmar agendamento/i }).click();
  await expect(page.getByRole("heading", { name: "Consulta confirmada" })).toBeVisible();
});

test("OCR review requires explicit save", async ({ page }) => {
  await page.goto("/documentos/revisao");
  await expect(page.getByRole("heading", { name: "Confirmar dados do documento" })).toBeVisible();
  await page.getByRole("button", { name: /Confirmar e salvar/i }).click();
  await expect(page.getByRole("heading", { name: "Documento confirmado" })).toBeVisible();
});

test("knowledge is only published after approval", async ({ page }) => {
  await page.goto("/backoffice/conhecimento");
  await expect(page.getByRole("heading", { name: "Revisar ingestão" })).toBeVisible();
  await page.getByRole("button", { name: /Aprovar e publicar/i }).click();
  await expect(page.getByRole("heading", { name: "Conhecimento publicado" })).toBeVisible();
});

