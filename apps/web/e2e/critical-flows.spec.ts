import { expect, test } from "@playwright/test";

test("landing is reduced to hero, chat CTA and backoffice access", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Cuidado inteligente/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Conversar com a Alyvo/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Backoffice" })).toBeVisible();
  await expect(page.locator("main section")).toHaveCount(1);
});

test("anonymous RAG answer exposes approved sources", async ({ page }) => {
  await page.goto("/chat");
  await page.getByRole("textbox", { name: "Mensagem", exact: true }).fill("Onde fica a Unidade Centro?");
  await page.getByRole("button", { name: "Enviar mensagem" }).click();
  const response = page.locator(".chat-message.assistant").last();
  await expect(response).toContainText(/Unidade Centro|informações aprovadas|base aprovada/i, { timeout: 120_000 });
  await response.getByText(/Fontes consultadas/).click();
  await expect(response.getByText(/Base institucional aprovada/).first()).toBeVisible();
});

test("personal query requests CPF and birth date contextually", async ({ page }) => {
  await page.goto("/chat");
  await page.getByRole("textbox", { name: "Mensagem", exact: true }).fill("Quais são minhas consultas?");
  await page.getByRole("button", { name: "Enviar mensagem" }).click();
  await expect(page.getByText("Confirme sua identidade")).toBeVisible({ timeout: 120_000 });
  await page.getByLabel("CPF").fill("123.456.789-09");
  await page.getByLabel("Data de nascimento").fill("1990-01-15");
  await page.getByRole("button", { name: "Continuar" }).click();
  await expect(page.getByText("Juliana Silva")).toBeVisible();
  await expect(page.getByText(/Estas são as suas consultas|não possui consultas/)).toBeVisible();
});

test("backoffice shows the simplified navigation and operational agenda", async ({ page }) => {
  await page.goto("/backoffice/login");
  await page.getByLabel("E-mail").fill("admin@alyvo.local");
  await page.getByLabel("Senha").fill("alyvo-demo");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/backoffice$/);
  await page.getByRole("link", { name: /Agenda/ }).click();
  await expect(page.getByRole("heading", { name: "Agenda" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Disponibilidade" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Nova consulta" })).toBeVisible();
});

test("catalog UI uses search, drawer and human labels", async ({ page }) => {
  await page.goto("/backoffice/login");
  await page.getByLabel("E-mail").fill("admin@alyvo.local");
  await page.getByLabel("Senha").fill("alyvo-demo");
  await page.getByRole("button", { name: "Entrar" }).click();
  await page.getByRole("link", { name: "Convênios" }).click();
  await expect(page.getByPlaceholder(/Buscar em convênios/)).toBeVisible();
  await page.getByRole("button", { name: "Novo cadastro" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByLabel("Nome")).toBeVisible();
});
