import { expect, test, type Page } from "@playwright/test";

const papers = [
  {
    id: "TEST-OPENALEX-001",
    source: "openalex",
    title: "TEST: Evidence-Aware Research Agents",
    authors: ["TEST Author One", "TEST Author Two"],
    year: 2024,
    abstract: "TEST synthetic abstract about evidence-aware research agents.",
    sourceUrl: "https://openalex.org/WTEST001",
    doi: null,
    venue: "TEST Journal",
    citationCount: 12,
    categories: [],
    synthetic: true,
  },
  {
    id: "TEST-ARXIV-002",
    source: "arxiv",
    title: "TEST: Retrieval and Verifiable Answers",
    authors: ["TEST Author Three"],
    year: 2023,
    abstract: "TEST synthetic abstract about retrieval and citations.",
    sourceUrl: "https://arxiv.org/abs/TEST-ARXIV-002",
    doi: null,
    venue: "TEST cs.AI",
    citationCount: null,
    categories: ["cs.AI"],
    synthetic: true,
  },
];

const agentAnswer = {
  status: "completed",
  answer: "TEST answer: the agent should cite retrieved evidence.",
  citations: [
    {
      source: "arxiv",
      openalex_id: null,
      arxiv_id: "TEST-ARXIV-002",
      title: papers[1].title,
      source_url: papers[1].sourceUrl,
      license_id: "TEST-CC-BY-4.0",
      license_url: "https://example.invalid/TEST-license",
      attribution: "TEST Author Three, synthetic fixture, TEST license.",
      evidence: [
        {
          chunk_id: "TEST-CHUNK-001",
          locator: "TEST section 1 · characters 0-42",
          excerpt: "TEST evidence excerpt used only by this browser test.",
        },
      ],
    },
  ],
  warnings: [],
  tool_calls: 1,
  model_steps: 2,
  model_input_tokens: 100,
  model_output_tokens: 25,
  run_id: "TEST-RUN-001",
  duration_ms: 321,
  trace: [
    {
      sequence: 1,
      kind: "tool",
      name: "TEST retrieve_paper_evidence",
      status: "ok",
      duration_ms: 12,
      input_tokens: 0,
      output_tokens: 0,
    },
  ],
};

async function installCommonMocks(page: Page) {
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { status: "ready" } }),
  );
  await page.route("**/api/search?**", (route) =>
    route.fulfill({
      json: { source: "openalex", total: papers.length, items: papers },
    }),
  );
  await page.route("**/api/paper?**", (route) => {
    const id = new URL(route.request().url()).searchParams.get("id");
    const found = papers.find((paper) => paper.id === id);
    return found
      ? route.fulfill({ json: found })
      : route.fulfill({
          status: 404,
          json: { detail: "TEST paper not found" },
        });
  });
  await page.route("**/api/agent", (route) =>
    route.fulfill({ json: agentAnswer }),
  );
}

test("searches papers, opens details, and compares metadata", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.goto("/");
  await page.getByLabel("检索主题或关键词").fill("TEST agent evidence");
  await page.getByRole("button", { name: /开始检索/ }).click();

  await expect(page.getByText(papers[0].title)).toBeVisible();
  await expect(page.getByText("合成测试数据").first()).toBeVisible();
  await page
    .getByRole("button", { name: /查看详情/ })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText(papers[0].title);
  await page.getByRole("button", { name: "关闭论文详情" }).click();

  await page
    .getByRole("checkbox", { name: `选择比较：${papers[0].title}` })
    .check();
  await page
    .getByRole("checkbox", { name: `选择比较：${papers[1].title}` })
    .check();
  await expect(
    page.getByRole("region", { name: "论文元数据对比" }),
  ).toContainText("发表载体");
  await expect(
    page.getByRole("region", { name: "论文元数据对比" }),
  ).toContainText("TEST Journal");
});

test("shows agent answer with trace, license, and cited evidence", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.goto("/");
  await page.getByLabel("你的研究问题").fill("TEST what does the paper say?");
  await page.getByRole("button", { name: /询问研究助理/ }).click();

  await expect(page.getByText(agentAnswer.answer)).toBeVisible();
  await expect(page.getByText("TEST-CC-BY-4.0")).toBeVisible();
  await expect(
    page.getByText(agentAnswer.citations[0].evidence[0].excerpt),
  ).toBeVisible();
  await page.getByText("运行记录与工程指标").click();
  await expect(page.getByText("TEST-RUN-001")).toBeVisible();
  await expect(page.getByText("TEST retrieve_paper_evidence")).toBeVisible();
});

test("shows empty and failure states and supports retry", async ({ page }) => {
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { status: "ready" } }),
  );
  let attempt = 0;
  await page.route("**/api/search?**", (route) => {
    attempt += 1;
    if (attempt === 1) {
      return route.fulfill({
        status: 503,
        json: { detail: "TEST upstream unavailable" },
      });
    }
    return route.fulfill({ json: { source: "openalex", total: 0, items: [] } });
  });
  await page.goto("/");
  await page.getByLabel("检索主题或关键词").fill("TEST no paper");
  await page.getByRole("button", { name: /开始检索/ }).click();
  await expect(page.locator(".error-state")).toContainText(
    "TEST upstream unavailable",
  );
  await page.getByRole("button", { name: "重试" }).click();
  await expect(page.getByText("没有找到匹配论文")).toBeVisible();
});

test("offers keyboard-accessible source and query controls", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.goto("/");
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "PaperTrail 工作区首页" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "arXiv" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "arXiv" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByLabel("检索主题或关键词")).toHaveAttribute(
    "placeholder",
    "试试：retrieval augmented generation",
  );
});

test("validates Agent proxy payloads before contacting the backend", async ({
  request,
}) => {
  const invalid = await request.post("/api/agent", {
    data: {
      question: "TEST valid length",
      backend_url: "https://example.invalid",
    },
  });
  expect(invalid.status()).toBe(422);

  const oversized = await request.post("/api/agent", {
    data: JSON.stringify({ question: "TEST ".padEnd(17_000, "x") }),
    headers: { "Content-Type": "application/json" },
  });
  expect(oversized.status()).toBe(413);
});
