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
  answer:
    "TEST answer: **evidence-first**.\n\n- Source: [OpenAlex](https://openalex.org/WTEST001).\n- Unsafe: [blocked](javascript:alert(1))",
  citations: [
    {
      source: "arxiv",
      openalex_id: null,
      arxiv_id: "TEST-ARXIV-002",
      title: papers[1].title,
      source_url: papers[1].sourceUrl,
      doi: null,
      publication_year: null,
      citation_relationships: [],
      alternate_sources: [],
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
    {
      source: "openalex",
      openalex_id: "WTEST900",
      arxiv_id: null,
      title: "TEST: Citation Graph Candidate",
      source_url: "https://openalex.org/WTEST900",
      doi: "https://doi.org/10.5555/TEST-SHARED",
      publication_year: 2024,
      citation_relationships: [
        { direction: "references", seed_openalex_id: "WTEST001" },
        { direction: "cited_by", seed_openalex_id: "WTEST002" },
      ],
      alternate_sources: [
        {
          source: "arXiv",
          identifier: "TEST-ARXIV-900",
          source_url: "https://arxiv.org/abs/TEST-ARXIV-900",
        },
      ],
      license_id: null,
      license_url: null,
      attribution: null,
      evidence: [],
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
      name: "TEST search_arxiv_metadata",
      status: "error",
      error_code: "arxiv_unavailable",
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

test("loads the next search page without replacing the first batch", async ({
  page,
}) => {
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { status: "ready" } }),
  );
  const requestedPages: string[] = [];
  const requestedYearRanges: string[] = [];
  await page.route("**/api/search?**", (route) => {
    const url = new URL(route.request().url());
    const requestedPage = url.searchParams.get("page") ?? "1";
    requestedPages.push(requestedPage);
    requestedYearRanges.push(
      `${url.searchParams.get("from_year")}-${url.searchParams.get("to_year")}`,
    );
    const items =
      requestedPage === "1"
        ? Array.from({ length: 10 }, (_, index) => ({
            ...papers[0],
            id: `TEST-OPENALEX-PAGE-${index + 1}`,
            title: `TEST paginated paper ${index + 1}`,
          }))
        : [
            {
              ...papers[0],
              id: "TEST-OPENALEX-PAGE-11",
              title: "TEST paginated paper 11",
            },
          ];
    return route.fulfill({
      json: {
        source: "openalex",
        total: 11,
        page: Number(requestedPage),
        hasMore: requestedPage === "1",
        items,
      },
    });
  });

  await page.goto("/");
  await page.getByLabel("检索主题或关键词").fill("TEST pagination");
  await page.getByLabel("起始年份").fill("2022");
  await page.getByLabel("结束年份").fill("2024");
  await page.getByRole("button", { name: /开始检索/ }).click();
  await expect(
    page.getByRole("heading", { name: "TEST paginated paper 1", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "TEST paginated paper 10", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /加载更多论文/ }).click();
  await expect(
    page.getByRole("heading", { name: "TEST paginated paper 11", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "TEST paginated paper 1", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /加载更多论文/ })).toHaveCount(
    0,
  );
  expect(requestedPages).toEqual(["1", "2"]);
  expect(requestedYearRanges).toEqual(["2022-2024", "2022-2024"]);
});

test("shows agent answer with trace, license, and cited evidence", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.goto("/");
  await page.getByLabel("你的研究问题").fill("TEST what does the paper say?");
  await page.getByRole("button", { name: /询问研究助理/ }).click();

  await expect(page.locator(".answer-text strong")).toHaveText(
    "evidence-first",
  );
  await expect(page.locator(".answer-text a")).toHaveAttribute(
    "href",
    "https://openalex.org/WTEST001",
  );
  await expect(page.getByText("[blocked](javascript:alert(1))")).toBeVisible();
  await expect(page.locator('.answer-text a[href^="javascript:"]')).toHaveCount(
    0,
  );
  await expect(page.getByText("TEST-CC-BY-4.0")).toBeVisible();
  await expect(page.getByText("种子论文的参考文献 · WTEST001")).toBeVisible();
  await expect(page.getByText("引用种子论文 · WTEST002")).toBeVisible();
  await expect(page.getByText("OpenAlex · WTEST900 · 2024")).toBeVisible();
  await expect(page.getByText("同一 DOI 的其他来源：")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "arxiv · TEST-ARXIV-900 ↗" }),
  ).toHaveAttribute("href", "https://arxiv.org/abs/TEST-ARXIV-900");
  await expect(
    page.getByText(agentAnswer.citations[0].evidence[0].excerpt),
  ).toBeVisible();
  await page.getByText("运行记录与工程指标").click();
  await expect(page.getByText("TEST-RUN-001")).toBeVisible();
  await expect(page.getByText("error · arxiv_unavailable")).toBeVisible();
  await expect(page.getByText("TEST search_arxiv_metadata")).toBeVisible();
});

test("hands current web search results and prior Agent turns into follow-ups", async ({
  page,
}) => {
  await installCommonMocks(page);
  const requests: Record<string, unknown>[] = [];
  await page.route("**/api/agent", async (route) => {
    requests.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({ json: agentAnswer });
  });

  await page.goto("/");
  await page.getByLabel("检索主题或关键词").fill("TEST retrieval agents");
  await page.getByLabel("起始年份").fill("2022");
  await page.getByLabel("结束年份").fill("2024");
  await page.getByRole("button", { name: /开始检索/ }).click();
  await expect(page.getByText(papers[0].title)).toBeVisible();

  const firstQuestion = "请用 OpenAlex 检索并列出论文元数据。";
  await page.getByLabel("你的研究问题").fill(firstQuestion);
  await page.getByRole("button", { name: /询问研究助理/ }).click();
  await expect(page.getByRole("heading", { name: "来源与证据" })).toBeVisible();

  const followUp = "根据刚才的检索结果，列出年份和来源链接。";
  await page.getByLabel("你的研究问题").fill(followUp);
  await page.getByRole("button", { name: /询问研究助理/ }).click();
  await expect(page.getByRole("heading", { name: "来源与证据" })).toBeVisible();

  expect(requests).toHaveLength(2);
  expect(requests[0].search_context).toEqual({
    source: "openalex",
    query: "TEST retrieval agents",
    from_year: 2022,
    to_year: 2024,
    pages: 1,
  });
  expect(requests[0].history).toEqual([]);
  expect(requests[1].history).toEqual([
    { role: "user", content: firstQuestion },
    { role: "assistant", content: agentAnswer.answer },
  ]);
  expect(requests[1].search_context).toEqual(requests[0].search_context);
});

test("shows empty and failure states and supports retry", async ({ page }) => {
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { status: "ready" } }),
  );
  const agentRequests: Record<string, unknown>[] = [];
  await page.route("**/api/agent", async (route) => {
    agentRequests.push(
      route.request().postDataJSON() as Record<string, unknown>,
    );
    await route.fulfill({ json: agentAnswer });
  });
  let attempt = 0;
  await page.route("**/api/search?**", (route) => {
    attempt += 1;
    if (attempt === 1 || attempt === 3) {
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

  await page.getByLabel("检索主题或关键词").fill("TEST unavailable new search");
  await page.getByRole("button", { name: /开始检索/ }).click();
  await expect(page.locator(".error-state")).toContainText(
    "TEST upstream unavailable",
  );
  await page.getByLabel("你的研究问题").fill("根据当前检索结果列出标题。");
  await page.getByRole("button", { name: /询问研究助理/ }).click();
  await expect(page.getByRole("heading", { name: "来源与证据" })).toBeVisible();
  expect(agentRequests.at(-1)?.search_context).toBeNull();
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
    data: JSON.stringify({ question: "TEST ".padEnd(70_000, "x") }),
    headers: { "Content-Type": "application/json" },
  });
  expect(oversized.status()).toBe(413);
});
