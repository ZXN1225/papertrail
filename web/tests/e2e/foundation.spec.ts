import { test, expect } from "@playwright/test";

test("real API empty state and all three local draft paths", async ({
  page,
  request,
}, testInfo) => {
  const response = await request.get(
    "http://127.0.0.1:8000/api/v1/platform/status",
  );
  expect(response.status()).toBe(200);
  expect((await response.json()).recommendation_available).toBe(false);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "先核实，再推荐" }),
  ).toBeVisible();
  await page.getByRole("spinbutton", { name: "预算上限（元）" }).fill("6000");
  await page.getByRole("button", { name: "预览需求" }).click();
  await expect(
    page.getByText("组装台式机 · 预算上限 6000 元 · 办公学习 · 仅主机"),
  ).toBeVisible();
  await page.getByRole("button", { name: /挑选笔记本/ }).click();
  await expect(page.getByRole("combobox", { name: "预算包含" })).toHaveValue(
    "笔记本整机",
  );
  await expect(page.getByText("本页需求草稿")).toHaveCount(0);
  await page.getByRole("button", { name: "预览需求" }).click();
  await expect(
    page.getByText("挑选笔记本 · 预算上限 6000 元 · 办公学习 · 笔记本整机"),
  ).toBeVisible();
  await page.getByRole("button", { name: /选择单个零件/ }).click();
  await page.getByRole("combobox", { name: "零件类别" }).selectOption("GPU");
  await page.getByRole("button", { name: "预览需求" }).click();
  await expect(
    page.getByText("选择单个零件 · 预算上限 6000 元 · 办公学习 · GPU"),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.reload();
  await expect(
    page.getByRole("spinbutton", { name: "预算上限（元）" }),
  ).toHaveValue("");
  await expect(
    page.getByRole("heading", { name: "先核实，再推荐" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("homepage.png"),
    fullPage: true,
  });
});

test("API network failure is visible and retry recovers", async ({ page }) => {
  await page.route("**/api/v1/platform/status", (route) =>
    route.abort("failed"),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "暂时无法连接服务" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "先核实，再推荐" }),
  ).toHaveCount(0);
  await page.unroute("**/api/v1/platform/status");
  await page.getByRole("button", { name: "重新连接" }).click();
  await expect(
    page.getByRole("heading", { name: "先核实，再推荐" }),
  ).toBeVisible();
});

test("keyboard navigation and invalid budget", async ({ page }) => {
  await page.goto("/");
  const budget = page.getByRole("spinbutton", { name: "预算上限（元）" });
  await budget.fill("0");
  await page.getByRole("button", { name: "预览需求" }).click();
  expect(
    await budget.evaluate(
      (element: HTMLInputElement) => element.validity.valid,
    ),
  ).toBe(false);
  await expect(page.getByText("本页需求草稿")).toHaveCount(0);
  await page.getByRole("button", { name: /挑选笔记本/ }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: /挑选笔记本/ }),
  ).toHaveAttribute("aria-pressed", "true");
});
