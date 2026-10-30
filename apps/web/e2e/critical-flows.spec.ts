import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs/promises";
import path from "node:path";

const api = process.env.API_URL ?? "http://127.0.0.1:8000/api/v1";
const root = path.resolve(import.meta.dirname, "../../..");

async function patientToken(request: APIRequestContext) {
  const start = await request.post(`${api}/auth/patient/start`, {
    data: { tenant_id: "clinic-alyvo", cpf: "123.456.789-09" },
  });
  expect(start.ok()).toBeTruthy();
  const verify = await request.post(`${api}/auth/patient/verify`, {
    data: { tenant_id: "clinic-alyvo", cpf: "123.456.789-09", code: "123456" },
  });
  expect(verify.ok()).toBeTruthy();
  return verify.json();
}

async function authenticatePatient(page: Page, request: APIRequestContext) {
  const tokens = await patientToken(request);
  await page.addInitScript((payload) => {
    localStorage.setItem("alyvo_access_token", payload.access_token);
    localStorage.setItem("alyvo_refresh_token", payload.refresh_token);
  }, tokens);
}

test("public GraphRAG answer exposes approved sources", async ({ page }) => {
  await page.goto("/chat");
  await page.getByRole("textbox", { name: "Mensagem", exact: true }).fill("Quais cardiologistas aceitam Vida+ na Unidade Centro?");
  await page.getByRole("button", { name: "Enviar mensagem" }).click();
  await expect(page.getByText(/Marina Lopes|Lucas Ferreira/).last()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText(/Fontes consultadas/).last()).toBeVisible();
});

test("patient authenticates, books and cancels a real slot", async ({ page, request }) => {
  await authenticatePatient(page, request);
  await page.goto("/agendar");
  await expect(page.getByText("Horários disponíveis")).toBeVisible();
  await page.getByRole("button", { name: "Confirmar agendamento" }).click();
  await expect(page.getByRole("heading", { name: "Consulta confirmada" })).toBeVisible();
  await page.reload();
  const cancelButtons = page.getByRole("button", { name: "Cancelar" });
  await expect(cancelButtons.first()).toBeVisible();
  const beforeCancel = await cancelButtons.count();
  expect(beforeCancel).toBeGreaterThan(0);
  page.once("dialog", (dialog) => dialog.accept());
  await cancelButtons.last().click();
  await expect(cancelButtons).toHaveCount(beforeCancel - 1);
});

test("patient document is reviewed before persistence", async ({ page, request }) => {
  await authenticatePatient(page, request);
  await page.goto("/documentos/revisao");
  await page.locator('input[type="file"]').setInputFiles(
    path.join(root, "datasets/synthetic-documents/carteirinha-limpo.png"),
  );
  await expect(page.getByText("Dados extraídos")).toBeVisible({ timeout: 175_000 });
  await page.getByRole("button", { name: "Confirmar e salvar" }).click();
  await expect(page.getByRole("heading", { name: "Documento confirmado" })).toBeVisible();
});

test("chat completes authentication and transactional scheduling inline", async ({ page }) => {
  await page.goto("/chat");
  await page.getByRole("textbox", { name: "Mensagem", exact: true }).fill("Quero agendar uma consulta");
  await page.getByRole("button", { name: "Enviar mensagem" }).click();
  await expect(page.getByRole("button", { name: "Enviar código" })).toBeVisible();
  await page.getByRole("button", { name: "Enviar código" }).click();
  await page.getByLabel("Código temporário").fill("123456");
  await page.getByRole("button", { name: "Validar código" }).click();
  const confirm = page.getByRole("button", { name: "Confirmar agendamento" }).last();
  await expect(confirm).toBeVisible({ timeout: 120_000 });
  await confirm.click();
  await expect(page.getByText("Operação concluída e auditada.").last()).toBeVisible({ timeout: 120_000 });
});

test("chat uploads, reviews and confirms OCR fields inline", async ({ page, request }) => {
  await authenticatePatient(page, request);
  await page.goto("/chat");
  await page.locator('input[type="file"]').setInputFiles(path.join(root, "datasets/synthetic-documents/pedido-medico-limpo.png"));
  await expect(page.getByText(/Revise a extração/)).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "Confirmar dados" }).click();
  await expect(page.getByText("Documento confirmado e liberado à recepção.")).toBeVisible();
});

test("administrator publishes ingestion only after review", async ({ page, request }) => {
  const ingestionTitle = `Guia institucional E2E ${Date.now()}`;
  await page.goto("/backoffice/login");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/backoffice$/);
  const token = await page.evaluate(() => localStorage.getItem("alyvo_access_token"));
  expect(token).toBeTruthy();
  const upload = await request.post(`${api}/backoffice/ingestions/upload`, {
    headers: { Authorization: `Bearer ${token}`, "X-Tenant-ID": "clinic-alyvo" },
    multipart: {
      title: ingestionTitle,
      file: {
        name: "guia-institucional.pdf",
        mimeType: "application/pdf",
        buffer: await fs.readFile(path.join(root, "datasets/synthetic-documents/guia-institucional.pdf")),
      },
    },
  });
  expect(upload.ok()).toBeTruthy();
  const documentId = (await upload.json()).id;
  let status = "uploaded";
  for (let attempt = 0; attempt < 120 && ["uploaded", "processing"].includes(status); attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const list = await request.get(`${api}/backoffice/ingestions`, {
      headers: { Authorization: `Bearer ${token}`, "X-Tenant-ID": "clinic-alyvo" },
    });
    const item = (await list.json()).items.find((candidate: { id: string }) => candidate.id === documentId);
    status = item?.status ?? status;
  }
  expect(status).toBe("review_required");
  await page.goto("/backoffice/conhecimento");
  await page.getByRole("button", { name: new RegExp(ingestionTitle) }).click();
  await page.getByRole("button", { name: "Aprovar e publicar" }).click();
  await expect(page.getByText(/Conhecimento aprovado/)).toBeVisible();
});

test("uncovered question offers and creates a reception ticket", async ({ page }) => {
  await page.goto("/chat");
  await page.getByRole("textbox", { name: "Mensagem", exact: true }).fill("A cafeteria serve almoço vegano?");
  await page.getByRole("button", { name: "Enviar mensagem" }).click();
  const ticket = page.getByRole("button", { name: "Criar ticket" });
  await expect(ticket).toBeVisible({ timeout: 120_000 });
  await ticket.click();
  await expect(page.getByText("Ticket criado para a recepção.")).toBeVisible();
});

