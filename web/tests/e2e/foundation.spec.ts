import { test, expect, type Page } from "@playwright/test";

test.beforeEach(async ({}, testInfo) => {
  testInfo.annotations.push({
    type: "synthetic",
    description: "true; TEST-I02 browser profile; test_* database only",
  });
});

async function open(page: Page) {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "保存需求", exact: true }),
  ).toBeEnabled();
}
async function saved(page: Page, budget = "6000.01") {
  await page.getByLabel("预算上限（元）").fill(budget);
  await page.getByLabel("不考虑的品牌").fill("TEST-BRAND");
  await page.getByRole("button", { name: "保存需求", exact: true }).click();
  await expect(
    page.getByText("需求已保存 · 版本 1", { exact: true }),
  ).toBeVisible();
}

test("published catalog has an honest empty state without test products", async ({
  page,
}) => {
  await page.goto("/catalog");
  await expect(
    page.getByRole("heading", { name: "尚无可公开的商品" }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "只有经过来源许可、证据核验和版本发布的精确 SKU 才会出现在这里。",
    ),
  ).toBeVisible();
});

test("save, restore, patch and all three device modes through real API", async ({
  page,
}, testInfo) => {
  await open(page);
  await expect(page.getByText("先核实，再推荐", { exact: true })).toBeVisible();
  await page.getByLabel("需要无线网络").check();
  await page.getByLabel("软件开发", { exact: true }).check();
  await saved(page);
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    "computer_session",
  );
  await page.reload();
  await expect(page.getByLabel("预算上限（元）")).toHaveValue("6000.01");
  await expect(page.getByLabel("需要无线网络")).toBeChecked();
  await expect(page.getByLabel("软件开发", { exact: true })).toBeChecked();
  await page.getByRole("button", { name: /挑选笔记本/ }).click();
  await page.getByLabel("重量上限（克，可选）").fill("1800");
  await page.getByRole("button", { name: "保存需求", exact: true }).click();
  await expect(
    page.getByText("需求已保存 · 版本 2", { exact: true }),
  ).toBeVisible();
  const current = await (
    await page.request.get("/api/v1/sessions/current")
  ).json();
  expect(current.profile.profile.budget_max_minor).toBe(600001);
  expect(current.profile.profile.excluded_brands).toEqual(["TEST-BRAND"]);
  expect(current.profile.profile.pc_constraints).toBeNull();
  await page.getByRole("button", { name: /选择单个零件/ }).click();
  await page.getByLabel("零件类别").selectOption("gpu");
  await page.getByRole("button", { name: "保存需求", exact: true }).click();
  await expect(
    page.getByText("需求已保存 · 版本 3", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("零件类别")).toHaveValue("gpu");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("saved-profile.png"),
    fullPage: true,
  });
});

test("two tabs reject stale revision and reload without overwriting", async ({
  page,
  context,
}) => {
  await open(page);
  await saved(page);
  const second = await context.newPage();
  await open(second);
  await expect(second.getByLabel("预算上限（元）")).toHaveValue("6000.01");
  await page.getByLabel("预算上限（元）").fill("7000.02");
  await page.getByRole("button", { name: "保存需求", exact: true }).click();
  await expect(
    page.getByText("需求已保存 · 版本 2", { exact: true }),
  ).toBeVisible();
  await second.getByLabel("预算上限（元）").fill("8000.03");
  await second.getByRole("button", { name: "保存需求", exact: true }).click();
  await expect(
    second.getByRole("alert").filter({ hasText: "另一页面已修改需求" }),
  ).toContainText("另一页面已修改需求");
  await expect(second.getByLabel("预算上限（元）")).toHaveValue("8000.03");
  await second.getByRole("button", { name: "读取最新需求" }).click();
  await expect(second.getByLabel("预算上限（元）")).toHaveValue("7000.02");
  await expect(second.getByLabel("不考虑的品牌")).toHaveValue("TEST-BRAND");
  await second.close();
});

test("new demand and deletion clear saved data and other contexts cannot read", async ({
  page,
  browser,
}) => {
  await open(page);
  await saved(page);
  const current = await (
    await page.request.get("/api/v1/sessions/current")
  ).json();
  const isolated = await browser.newContext({
    baseURL: "http://127.0.0.1:3001",
  });
  expect(
    (
      await isolated.request.get(`/api/v1/profiles/${current.profile.id}`)
    ).status(),
  ).toBe(404);
  await isolated.close();
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "开始新需求" }).click();
  await expect(page.getByLabel("预算上限（元）")).toHaveValue("");
  await expect(page.getByLabel("不考虑的品牌")).toHaveValue("");
  expect(
    (await page.request.get(`/api/v1/profiles/${current.profile.id}`)).status(),
  ).toBe(404);
  await saved(page, "4000");
  await page.getByRole("button", { name: "删除已保存需求" }).click();
  await expect(
    page.getByText("已删除保存的需求与会话。", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("预算上限（元）")).toHaveValue("");
  expect((await page.request.get("/api/v1/sessions/current")).status()).toBe(
    404,
  );
});

test("failed save preserves the draft and does not claim success", async ({
  page,
}) => {
  await open(page);
  await page.route("**/api/v1/profiles", (route) => route.abort());
  await page.getByLabel("预算上限（元）").fill("5000");
  await page.getByRole("button", { name: "保存需求", exact: true }).click();
  await expect(
    page
      .getByRole("alert")
      .filter({ has: page.getByRole("button", { name: "读取最新需求" }) }),
  ).toBeVisible();
  await expect(page.getByLabel("预算上限（元）")).toHaveValue("5000");
  await expect(page.getByText(/需求已保存 ·/)).toHaveCount(0);
});

test("platform network error can retry and keyboard rejects invalid budget", async ({
  page,
}) => {
  await page.route("**/api/v1/platform/status", (route) => route.abort());
  await open(page);
  await expect(
    page.getByText("暂时无法连接服务", { exact: true }),
  ).toBeVisible();
  await page.unroute("**/api/v1/platform/status");
  await page.getByRole("button", { name: "重新连接" }).click();
  await expect(page.getByText("先核实，再推荐", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /挑选笔记本/ }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("button", { name: /挑选笔记本/ }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("预算上限（元）").fill("0");
  await page.getByRole("button", { name: "保存需求", exact: true }).click();
  expect(
    await page
      .getByLabel("预算上限（元）")
      .evaluate((el: HTMLInputElement) => el.validity.valid),
  ).toBe(false);
  expect((await page.request.get("/api/v1/sessions/current")).status()).toBe(
    404,
  );
});
