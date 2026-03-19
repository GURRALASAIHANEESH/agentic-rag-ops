import { test, expect, type Page } from '@playwright/test';

const ADMIN_EMAIL = 'admin@ragops.dev';
const ADMIN_PASSWORD = 'admin123';
const API = 'http://localhost:8000';

// ── helpers ──────────────────────────────────────────────────────────────────
async function loginViaUI(page: Page) {
    await page.goto('/login');
    await page.getByLabel('Email').fill(ADMIN_EMAIL);
    await page.getByLabel('Password').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForURL('**/dashboard', { timeout: 15_000 });
}

async function getToken(page: Page): Promise<string> {
    const res = await page.request.post(`${API}/auth/login`, {
        data: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD },
    });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    return body.access_token as string;
}

// ── tests ─────────────────────────────────────────────────────────────────────
test.describe('Full query flow', () => {
    test('signup → dashboard redirect (new user)', async ({ page }) => {
        const ts = Date.now();
        await page.goto('/signup');
        await page.getByLabel('Email').fill(`user_${ts}@test.dev`);
        await page.getByLabel('Password').fill('TestPass123!');
        await page.getByRole('button', { name: /create account/i }).click();
        await page.waitForURL('**/dashboard', { timeout: 15_000 });
        await expect(page.getByText(/workspace/i)).toBeVisible();
    });

    test('admin login → dashboard visible', async ({ page }) => {
        await loginViaUI(page);
        await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible();
    });

    test('create workspace', async ({ page }) => {
        await loginViaUI(page);
        await page.goto('/workspace');
        await page.getByRole('button', { name: /new workspace/i }).click();
        const nameInput = page.getByPlaceholder(/workspace name/i);
        await nameInput.fill('E2E Workspace');
        await page.getByRole('button', { name: /create/i }).click();
        await expect(page.getByText('E2E Workspace')).toBeVisible({ timeout: 10_000 });
    });

    test('upload document', async ({ page }) => {
        await loginViaUI(page);
        await page.goto('/upload');
        // workspace selector must be visible
        const wsSelect = page.getByRole('combobox', { name: /workspace/i });
        await wsSelect.waitFor({ timeout: 5_000 });
        await wsSelect.selectOption({ index: 0 }); // pick first workspace

        const [fileChooser] = await Promise.all([
            page.waitForEvent('filechooser'),
            page.getByRole('button', { name: /choose file|upload/i }).click(),
        ]);
        await fileChooser.setFiles({
            name: 'sample.txt',
            mimeType: 'text/plain',
            buffer: Buffer.from('RAG stands for Retrieval-Augmented Generation.'),
        });
        await page.getByRole('button', { name: /upload/i }).click();
        await expect(page.getByText(/ingested|success/i)).toBeVisible({ timeout: 20_000 });
    });

    test('run query → streaming response → citation card visible', async ({ page }) => {
        await loginViaUI(page);
        await page.goto('/query');

        const wsSelect = page.getByRole('combobox', { name: /workspace/i });
        await wsSelect.waitFor({ timeout: 5_000 });
        await wsSelect.selectOption({ index: 0 });

        const queryInput = page.getByRole('textbox', { name: /query|ask/i });
        await queryInput.fill('What is RAG?');
        await page.getByRole('button', { name: /submit|send/i }).click();

        // streaming output should appear progressively
        const responseArea = page.locator('[data-testid="streaming-output"]');
        await expect(responseArea).not.toBeEmpty({ timeout: 30_000 });

        // citation card must be present
        const citationCard = page.locator('[data-testid="citation-card"]').first();
        await expect(citationCard).toBeVisible({ timeout: 30_000 });
    });

    test('API: SSE stream returns chunk + citation events', async ({ page }) => {
        const token = await getToken(page);

        // Get first workspace id via API
        const wsRes = await page.request.get(`${API}/workspaces`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        expect(wsRes.ok()).toBeTruthy();
        const workspaces = await wsRes.json();
        expect(workspaces.length).toBeGreaterThan(0);
        const wsId: string = workspaces[0].id;

        // Fire SSE request — Playwright doesn't natively stream, so we verify headers
        const queryRes = await page.request.post(`${API}/query`, {
            headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
                Accept: 'text/event-stream',
            },
            data: { query: 'What is RAG?', workspace_id: wsId },
        });
        expect(queryRes.ok()).toBeTruthy();
        const contentType = queryRes.headers()['content-type'] ?? '';
        expect(contentType).toContain('text/event-stream');

        const body = await queryRes.text();
        expect(body).toContain('event: chunk');
        expect(body).toContain('event: citation');
    });
});
