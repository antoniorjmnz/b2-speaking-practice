import { expect, test } from "@playwright/test";

const viewports = [
  { name: "móvil", width: 390, height: 844 },
  { name: "tableta", width: 768, height: 1024 },
] as const;

for (const viewport of viewports) {
  test(`el menú es utilizable sin desbordamiento en ${viewport.name}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(
      page.getByRole("heading", { name: "Elige cómo quieres practicar" }),
    ).toBeVisible();
    await expect(page.locator('[data-mode="individual"]')).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Individual \+ IA/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Dos personas/ }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /pendiente/i })).toHaveCount(
      0,
    );
    await expect(
      page.getByRole("button", { name: /Comenzar/ }).last(),
    ).toBeVisible();

    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    );
    expect(hasHorizontalOverflow).toBe(false);
  });
}

test("el menú principal expone estructura y navegación por teclado", async ({
  page,
}) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");

  await expect(page.locator("main")).toHaveCount(1);
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);

  const aiMode = page.getByRole("button", { name: /Individual \+ IA/ });
  await aiMode.focus();
  await expect(aiMode).toBeFocused();
  await aiMode.press("Enter");
  await expect(aiMode).toHaveAttribute("aria-pressed", "true");

  const lastPractice = page.getByRole("button", { name: /Práctica 12/ });
  await lastPractice.focus();
  await expect(lastPractice).toBeFocused();
  await lastPractice.press("Enter");
  await expect(lastPractice).toHaveAttribute("aria-pressed", "true");
});
