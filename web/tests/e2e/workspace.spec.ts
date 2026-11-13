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
  claims: [
    {
      text: "TEST answer: the agent should cite retrieved evidence.",
      evidence: [
        {
          source_id: "TEST-ARXIV-002",
          quote: "TEST evidence excerpt used only by this browser test.",
          evidence_type: "fulltext",
          source_field: "excerpt",
          chunk_id: "TEST-CHUNK-001",
        },
      ],
    },
  ],
  warnings: [],
  tool_calls: 1,
  model_steps: 2,
  model_input_tokens: 100,
  model_output_tokens: 25,
  total_observed_tokens: 125,
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
  await page.route("**/api/auth", (route) =>
    route.fulfill({ json: { id: "TEST-USER-001" } }),
  );
  await page.route("**/api/conversations", (route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        json: {
          id: "00000000-0000-4000-8000-000000000001",
          title: "TEST conversation",
        },
      });
    }
    return route.fulfill({ json: [] });
  });
  await page.route("**/api/conversations/*/messages", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/library", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/documents**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { status: "ready", checks: { llm: "configured" } } }),
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

async function openAssistant(page: Page) {
  await page.getByRole("button", { name: "科研助手" }).click();
}

test("registers an account and enters the research workspace", async ({
  page,
}) => {
  let signedIn = false;
  await page.route("**/api/auth", async (route) => {
    if (route.request().method() === "GET") {
      return signedIn
        ? route.fulfill({ json: { id: "TEST-USER-001" } })
        : route.fulfill({
            status: 401,
            json: { detail: "authentication_required" },
          });
    }
    const body = route.request().postDataJSON();
    if (body.action === "logout") signedIn = false;
    if (body.action === "login") signedIn = true;
    return route.fulfill({
      status: body.action === "register" ? 201 : 200,
      json: { id: "TEST-USER-001" },
    });
  });
  await page.route("**/api/conversations", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          json: { id: "00000000-0000-4000-8000-000000000001", title: "新对话" },
        })
      : route.fulfill({ json: [] }),
  );
  await page.route("**/api/library", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { status: "ready" } }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "创建新账号" }).click();
  await page.getByLabel("账号").fill("TEST_Researcher");
  await page.getByLabel("密码").fill("correct horse battery staple");
  await page.getByRole("button", { name: "注册账号" }).click();

  await expect(page.getByRole("button", { name: "发现论文" })).toBeVisible();
  await expect(page.getByRole("button", { name: "科研助手" })).toBeVisible();
  await expect(page.locator(".assistant-workspace")).toBeHidden();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "使用说明" }).click();
  await expect(page.getByRole("region", { name: "使用说明" })).toContainText(
    "不会下载 PDF",
  );
  await page.getByRole("button", { name: "科研助手" }).click();
  await expect(page.getByLabel("你的研究问题")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

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

test("keeps the newest discovery search when an older response arrives last", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.route("**/api/search?**", async (route) => {
    const query = new URL(route.request().url()).searchParams.get("q");
    if (query === "TEST slow query") {
      await new Promise((resolve) => setTimeout(resolve, 500));
      return route.fulfill({
        json: { source: "openalex", total: 1, items: [papers[0]] },
      });
    }
    return route.fulfill({
      json: { source: "openalex", total: 1, items: [papers[1]] },
    });
  });
  await page.goto("/");
  const query = page.getByLabel("检索主题或关键词");
  const searchButton = page.getByRole("button", { name: /开始检索/ });
  await query.fill("TEST slow query");
  await searchButton.click();
  await query.fill("TEST latest query");
  await searchButton.click();
  await expect(page.getByText(papers[1].title)).toBeVisible();
  await expect(page.getByText(papers[0].title)).toHaveCount(0);
});

test("saves a paper snapshot and searches the personal library", async ({
  page,
}) => {
  await installCommonMocks(page);
  let savedPaper: (typeof papers)[number] | null = null;
  let privateDocuments: {
    id: string;
    library_entry_id: string;
    original_filename: string;
    size_bytes: number;
    state: "queued" | "processing" | "indexed" | "failed";
    chunk_count: number;
  }[] = [];
  await page.route("**/api/library", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      savedPaper = body.metadata;
      return route.fulfill({
        json: {
          id: "TEST-LIBRARY-ENTRY-001",
          source: body.source,
          source_id: body.source_id,
          metadata: body.metadata,
        },
      });
    }
    return route.fulfill({
      json: savedPaper
        ? [
            {
              id: "TEST-LIBRARY-ENTRY-001",
              source: "openalex",
              source_id: savedPaper.id,
              metadata: savedPaper,
            },
          ]
        : [],
    });
  });
  await page.route("**/api/search?**", (route) => {
    const params = new URL(route.request().url()).searchParams;
    const source = params.get("source");
    if (source === "library") {
      const terms = (params.get("q") ?? "")
        .toLowerCase()
        .split(/\s+/)
        .filter(Boolean);
      const searchable = JSON.stringify(savedPaper ?? {})
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, " ");
      const matchingPaper =
        savedPaper && terms.every((term) => searchable.includes(term));
      return route.fulfill({
        json: {
          source,
          total: matchingPaper ? 1 : 0,
          items: matchingPaper ? [savedPaper] : [],
        },
      });
    }
    return route.fulfill({
      json: { source: "openalex", total: papers.length, items: papers },
    });
  });
  await page.route("**/api/documents**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/TEST-PRIVATE-DOCUMENT-001")) {
      if (route.request().method() === "DELETE") {
        privateDocuments = [];
        return route.fulfill({ status: 204, body: "" });
      }
      return route.fulfill({ status: 404, json: { detail: "not_found" } });
    }
    if (route.request().method() === "POST") {
      privateDocuments = [
        {
          id: "TEST-PRIVATE-DOCUMENT-001",
          library_entry_id: "TEST-LIBRARY-ENTRY-001",
          original_filename: "TEST-manuscript.pdf",
          size_bytes: 2_048,
          state: "indexed",
          chunk_count: 7,
        },
      ];
      return route.fulfill({ status: 202, json: privateDocuments[0] });
    }
    return route.fulfill({ json: privateDocuments });
  });
  await page.goto("/");
  await page.getByLabel("检索主题或关键词").fill("TEST saved paper");
  await page.getByRole("button", { name: /开始检索/ }).click();
  await page.getByRole("button", { name: "加入个人库" }).first().click();
  await expect(
    page.getByRole("button", { name: "已加入个人库" }).first(),
  ).toBeVisible();

  await page.getByRole("button", { name: "我的文献库" }).click();
  await page.getByLabel("检索主题或关键词").fill("evidence aware research");
  await page.getByRole("button", { name: /开始检索/ }).click();

  await expect(
    page
      .locator(".paper-list")
      .first()
      .getByRole("heading", { name: papers[0].title }),
  ).toBeVisible();
  await expect(
    page
      .locator(".paper-list")
      .first()
      .getByRole("button", { name: "加入个人库" }),
  ).toHaveCount(0);
  await page
    .locator(".paper-list")
    .first()
    .getByRole("button", { name: /查看详情/ })
    .click();
  await expect(page.getByRole("dialog")).toContainText(papers[0].title);
  await expect(
    page.getByRole("dialog").getByRole("link", { name: /查看原始记录/ }),
  ).toHaveAttribute("href", papers[0].sourceUrl);
  await page.getByRole("button", { name: "关闭论文详情" }).click();

  const savedCard = page
    .locator(".paper-list")
    .last()
    .locator(".paper-card")
    .filter({ hasText: papers[0].title });
  const sourceLinkBounds = await savedCard
    .getByRole("link", { name: "打开原文页" })
    .boundingBox();
  const removeButtonBounds = await savedCard
    .getByRole("button", { name: "移除" })
    .boundingBox();
  expect(sourceLinkBounds).not.toBeNull();
  expect(removeButtonBounds).not.toBeNull();
  expect(
    removeButtonBounds!.x > sourceLinkBounds!.x + sourceLinkBounds!.width ||
      removeButtonBounds!.y > sourceLinkBounds!.y,
  ).toBe(true);
  await savedCard.locator('input[type="file"]').setInputFiles({
    name: "TEST-manuscript.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-TEST synthetic document"),
  });
  await savedCard.getByRole("checkbox").check();
  await savedCard.getByRole("button", { name: "上传并解析" }).click();
  await expect(savedCard).toContainText(
    "7 个解析片段（图表内容暂不可用于问答）",
  );
  await savedCard.getByRole("button", { name: "删除 PDF" }).click();
  await expect(savedCard).not.toContainText("TEST-manuscript.pdf");
});

test("uploads a personal manuscript and retries a failed parse", async ({
  page,
}) => {
  await installCommonMocks(page);
  const personalId = "00000000-0000-4000-8000-000000000021";
  let document = {
    id: personalId,
    library_entry_id: null,
    source_type: "personal",
    source_id: personalId,
    source_url: "",
    title: "TEST My manuscript",
    original_filename: "TEST-my-manuscript.pdf",
    size_bytes: 2048,
    state: "failed",
    error_code: "mineru_timeout",
    chunk_count: 0,
  };
  let uploaded = false;
  await page.route("**/api/documents**", async (route) => {
    const request = route.request();
    if (request.url().endsWith(`/${document.id}/retry`)) {
      document = { ...document, state: "queued", error_code: "" };
      return route.fulfill({ json: document });
    }
    if (
      request.url().endsWith(`/${document.id}`) &&
      request.method() === "DELETE"
    ) {
      uploaded = false;
      return route.fulfill({ status: 204, body: "" });
    }
    if (request.method() === "POST") {
      expect(request.postData()).toContain('name="title"');
      expect(request.postData()).toContain("TEST My manuscript");
      expect(request.postData()).toContain('name="rights_attested"');
      expect(request.postData()).not.toContain('name="library_entry_id"');
      uploaded = true;
      return route.fulfill({ status: 202, json: document });
    }
    return route.fulfill({ json: uploaded ? [document] : [] });
  });
  await page.goto("/");
  const manuscripts = page.getByRole("region", { name: "我的稿件" });
  await expect(manuscripts).toContainText("还没有上传稿件");
  await manuscripts.getByLabel("稿件标题").fill("TEST My manuscript");
  await manuscripts.getByLabel("选择 PDF").setInputFiles({
    name: "TEST-my-manuscript.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-TEST synthetic document"),
  });
  await manuscripts.getByRole("checkbox").check();
  await manuscripts.getByRole("button", { name: "上传并解析" }).click();
  await expect(manuscripts).toContainText("解析失败 · 解析超时");
  await expect(manuscripts.getByRole("link")).toHaveCount(0);
  await manuscripts.getByRole("button", { name: "重试解析" }).click();
  await expect(manuscripts).toContainText("等待解析");
  await expect(
    manuscripts.getByRole("button", { name: "删除 PDF" }),
  ).toBeDisabled();
});

test("shows personal citations with a private page locator and no public link", async ({
  page,
}) => {
  await installCommonMocks(page);
  const personalId = "00000000-0000-4000-8000-000000000021";
  await page.route("**/api/agent", (route) =>
    route.fulfill({
      json: {
        ...agentAnswer,
        citations: [
          {
            source: "personal",
            openalex_id: null,
            arxiv_id: null,
            personal_id: personalId,
            title: "TEST My manuscript",
            source_url: "",
            license_id: null,
            license_url: null,
            attribution: null,
            private_processing: true,
            evidence: [
              {
                chunk_id: "TEST-CHUNK-PERSONAL",
                locator: "第 2 页",
                excerpt: "TEST private excerpt.",
              },
              {
                chunk_id: "visual:TEST-PERSONAL:TEST-FIGURE",
                locator: "Page 3 · MinerU 图表区域",
                excerpt: "Figure 1. TEST original caption",
                evidence_type: "visual_analysis",
                visual_description: "TEST unverified line rises",
                verification_status: "model_generated_unverified",
              },
            ],
          },
        ],
        claims: [
          {
            text: "TEST private claim",
            evidence: [
              {
                source_id: personalId,
                quote: "TEST private excerpt.",
                evidence_type: "fulltext",
                source_field: "excerpt",
                chunk_id: "TEST-CHUNK-PERSONAL",
              },
              {
                source_id: personalId,
                quote: "TEST unverified line rises",
                evidence_type: "visual_analysis",
                source_field: "visual_description",
                chunk_id: "visual:TEST-PERSONAL:TEST-FIGURE",
              },
            ],
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("后端已连接 · 模型未验证");
  await openAssistant(page);
  await page
    .getByLabel("你的研究问题")
    .fill("TEST personal manuscript question");
  await page.getByRole("button", { name: "发送" }).click();
  const citation = page.locator(".citation-card");
  await expect(citation).toContainText("我的稿件");
  await expect(citation).toContainText("第 2 页");
  await expect(citation).toContainText("MinerU AI 图表解读 · 未核验");
  await expect(citation).toContainText("TEST original caption");
  await expect(citation).toContainText("TEST unverified line rises");
  await expect(citation.getByRole("link")).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "逐条主张与证据" }),
  ).toContainText("第 2 页");
  await expect(
    page.getByRole("region", { name: "逐条主张与证据" }),
  ).toContainText("MinerU AI 图表解读 · 未核验");
});

test("distinguishes a disabled model from backend readiness", async ({ page }) => {
  await installCommonMocks(page);
  await page.route("**/api/status", (route) =>
    route.fulfill({ json: { status: "ready", checks: { llm: "disabled" } } }),
  );
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("后端已连接 · 模型未启用");
});

test("shows submitted message before the agent responds", async ({ page }) => {
  await installCommonMocks(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/agent", async (route) => {
    await gate;
    await route.fulfill({ json: agentAnswer });
  });
  await page.goto("/");
  await openAssistant(page);
  await page.getByLabel("你的研究问题").fill("TEST pending question");
  await page.getByRole("button", { name: "发送" }).click();
  try {
    await expect(page.locator(".conversation-turn.user p").last()).toHaveText(
      "TEST pending question",
    );
    await expect(page.getByLabel("你的研究问题")).toHaveValue("");
    await expect(page.locator(".conversation-turn.assistant")).toHaveCount(0);
  } finally {
    release();
  }
  await expect(
    page.locator(".conversation-turn.assistant p").last(),
  ).toHaveText(agentAnswer.answer);
  await expect(page.locator(".conversation-turn.user")).toHaveCount(1);
});

test("composer supports newline and enter submission", async ({ page }) => {
  await installCommonMocks(page);
  await page.route("**/api/agent", (route) =>
    route.fulfill({ json: agentAnswer }),
  );
  await page.goto("/");
  await openAssistant(page);
  const input = page.getByLabel("你的研究问题");
  await input.fill("TEST first line");
  await input.press("Shift+Enter");
  await input.pressSequentially("second line");
  await expect(input).toHaveValue("TEST first line\nsecond line");
  await input.press("Enter");
  await expect(input).toHaveValue("");
  await expect(
    page.locator(".conversation-turn.assistant p").last(),
  ).toHaveText(agentAnswer.answer);
});

test("shows agent answer with trace, license, and cited evidence", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.route("**/api/agent", (route) =>
    route.fulfill({
      json: {
        ...agentAnswer,
        trace: [
          ...agentAnswer.trace,
          {
            ...agentAnswer.trace[0],
            sequence: 2,
            kind: "model",
            name: "responses",
            status: "incomplete",
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await openAssistant(page);
  await page.getByLabel("你的研究问题").fill("TEST what does the paper say?");
  await page.getByRole("button", { name: "发送" }).click();

  const chatPanel = page.locator(".chat-panel");
  const evidencePane = page.locator(".evidence-pane");
  await expect(evidencePane).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const chatBounds = await chatPanel.boundingBox();
  const evidenceBounds = await evidencePane.boundingBox();
  expect(chatBounds).not.toBeNull();
  expect(evidenceBounds).not.toBeNull();
  if ((page.viewportSize()?.width ?? 0) <= 820) {
    expect(evidenceBounds!.y).toBeGreaterThan(chatBounds!.y);
  } else {
    expect(evidenceBounds!.x).toBeGreaterThan(chatBounds!.x);
  }
  await expect(
    page.locator(".conversation-turn.assistant p").last(),
  ).toHaveText(agentAnswer.answer);
  await expect(page.getByText("TEST-CC-BY-4.0")).toBeVisible();
  await expect(page.getByText("逐条主张与证据")).toBeVisible();
  await expect(page.getByText("TEST-CHUNK-001").first()).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "逐条主张与证据" })
      .getByText(agentAnswer.citations[0].evidence[0].excerpt),
  ).toBeVisible();
  await page.getByText("运行记录与工程指标").click();
  await expect(page.getByText("TEST-RUN-001")).toBeVisible();
  await expect(page.getByText("TEST retrieve_paper_evidence")).toBeVisible();
  await expect(page.getByText("输出未完成")).toBeVisible();
});

test("supports bounded request-scoped follow-up context and reset", async ({
  page,
}) => {
  await installCommonMocks(page);
  const requests: {
    question: string;
    history: { role: string; content: string }[];
  }[] = [];
  await page.route("**/api/agent", async (route) => {
    requests.push(route.request().postDataJSON());
    await route.fulfill({ json: agentAnswer });
  });
  await page.goto("/");
  await openAssistant(page);
  await expect(page.getByText(/对话保存在你的账号中/)).toBeVisible();

  await page.getByLabel("你的研究问题").fill("TEST first question");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(
    page.locator(".conversation-turn.assistant p").last(),
  ).toHaveText(agentAnswer.answer);
  await expect(
    page.getByText(/最近原文与研究摘要共同提供上下文/),
  ).toBeVisible();

  await page.getByLabel("你的研究问题").fill("TEST follow-up correction");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(
    page.locator(".conversation-turn.assistant p").last(),
  ).toHaveText(agentAnswer.answer);
  expect(requests[0].history).toEqual([]);
  expect(requests[1].history).toEqual([
    { role: "user", content: "TEST first question" },
    { role: "assistant", content: agentAnswer.answer },
  ]);

  await page.getByRole("button", { name: "清空对话" }).click();
  await page.getByLabel("你的研究问题").fill("TEST new conversation");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(
    page.locator(".conversation-turn.assistant p").last(),
  ).toHaveText(agentAnswer.answer);
  expect(requests[2].history).toEqual([]);
});

test("explains when the account daily agent token budget is exhausted", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.route("**/api/agent", (route) =>
    route.fulfill({
      status: 429,
      json: {
        detail: {
          code: "daily_agent_token_budget_exceeded",
          daily_token_budget: 100,
        },
      },
    }),
  );
  await page.goto("/");
  await openAssistant(page);
  await page.getByLabel("你的研究问题").fill("TEST daily budget limit");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(
    page.getByText("今日科研助手 token 额度已用完，请明日再试或联系管理员。"),
  ).toBeVisible();
});

test("shows the Agent model failure returned by the backend", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.route("**/api/agent", (route) =>
    route.fulfill({
      status: 503,
      json: {
        status: "model_unavailable",
        answer: "TEST 模型暂时不可用，请稍后重试。",
        citations: [],
        claims: [],
        trace: [],
      },
    }),
  );
  await page.goto("/");
  await openAssistant(page);
  await page.getByLabel("你的研究问题").fill("TEST model failure");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.locator(".inline-error")).toContainText(
    "TEST 模型暂时不可用，请稍后重试。",
  );
});

test("switching conversations isolates delayed history and active replies", async ({
  page,
}) => {
  await installCommonMocks(page);
  const ids = [
    "00000000-0000-4000-8000-000000000011",
    "00000000-0000-4000-8000-000000000012",
    "00000000-0000-4000-8000-000000000013",
  ];
  await page.route("**/api/conversations", (route) =>
    route.fulfill({
      json: ids.map((id, index) => ({ id, title: `TEST chat ${index}` })),
    }),
  );
  await page.route("**/api/conversations/*/messages", async (route) => {
    const id = new URL(route.request().url()).pathname.split("/")[3];
    if (id === ids[1]) await new Promise((resolve) => setTimeout(resolve, 800));
    await route.fulfill({
      json: [{ role: "user", content: `TEST history ${id}` }],
    });
  });
  await page.route("**/api/agent", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await route.fulfill({ json: agentAnswer }).catch(() => undefined);
  });
  await page.route("**/api/agent/cancel", (route) =>
    route.fulfill({ json: {} }),
  );
  await page.goto("/");
  await openAssistant(page);
  const sidebar = page.getByRole("complementary", { name: "对话列表" });
  await page.getByLabel("你的研究问题").fill("TEST pending request");
  await page.getByRole("button", { name: "发送" }).click();
  await sidebar
    .getByRole("button", { name: "TEST chat 1", exact: true })
    .click();
  await page.getByLabel("你的研究问题").fill("TEST waiting for history");
  await expect(page.getByRole("button", { name: "发送" })).toBeDisabled();
  await sidebar
    .getByRole("button", { name: "TEST chat 2", exact: true })
    .click();
  await expect(page.getByText(`TEST history ${ids[2]}`)).toBeVisible();
  await page.waitForTimeout(1500);
  await expect(page.getByText(`TEST history ${ids[1]}`)).toHaveCount(0);
  await expect(page.getByText(agentAnswer.answer)).toHaveCount(0);
});

test("deleting last conversation succeeds even if replacement request fails", async ({
  page,
}) => {
  await installCommonMocks(page);
  const id = "00000000-0000-4000-8000-000000000021";
  await page.route("**/api/conversations", (route) =>
    route.request().method() === "POST"
      ? route.abort("failed")
      : route.fulfill({ json: [{ id, title: "TEST last chat" }] }),
  );
  await page.route("**/api/conversations/*", (route) =>
    route.request().method() === "DELETE"
      ? route.fulfill({ status: 204, body: "" })
      : route.fallback(),
  );
  await page.goto("/");
  await openAssistant(page);
  const sidebar = page.getByRole("complementary", { name: "对话列表" });
  await sidebar.getByRole("button", { name: "删除：TEST last chat" }).click();
  await sidebar.getByRole("button", { name: "删除", exact: true }).click();
  await expect(
    sidebar.getByRole("button", { name: "TEST last chat", exact: true }),
  ).toHaveCount(0);
  await expect(sidebar.getByText("删除对话失败，请稍后重试。")).toHaveCount(0);
});

test("loads and switches between saved conversations", async ({ page }) => {
  await installCommonMocks(page);
  await page.route("**/api/conversations", (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      json: [
        {
          id: "00000000-0000-4000-8000-000000000011",
          title: "TEST first conversation",
        },
        {
          id: "00000000-0000-4000-8000-000000000012",
          title: "TEST second conversation",
        },
      ],
    });
  });
  await page.route("**/api/conversations/*/messages", (route) => {
    const id = new URL(route.request().url()).pathname.split("/")[3];
    return route.fulfill({
      json: [
        { role: "user", content: `TEST message from ${id}` },
        { role: "assistant", content: `TEST reply from ${id}` },
      ],
    });
  });
  await page.goto("/");
  await openAssistant(page);

  await expect(
    page.getByText("TEST message from 00000000-0000-4000-8000-000000000011"),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "TEST second conversation", exact: true })
    .click();
  await expect(
    page.getByText("TEST message from 00000000-0000-4000-8000-000000000012"),
  ).toBeVisible();
});

test("creates, renames, and switches conversations from the left sidebar", async ({
  page,
}) => {
  await installCommonMocks(page);
  const conversations = [
    {
      id: "00000000-0000-4000-8000-000000000031",
      title: "TEST existing conversation",
    },
  ];
  const messages: Record<
    string,
    { role: "user" | "assistant"; content: string }[]
  > = {
    [conversations[0].id]: [
      { role: "user", content: "TEST first conversation question" },
      { role: "assistant", content: "TEST first conversation answer" },
    ],
  };
  let nextId = 32;
  await page.route("**/api/conversations", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: conversations });
    }
    if (route.request().method() === "POST") {
      const created = {
        id: `00000000-0000-4000-8000-${String(nextId++).padStart(12, "0")}`,
        title: "新对话",
      };
      conversations.unshift(created);
      messages[created.id] = [];
      return route.fulfill({ status: 201, json: created });
    }
    return route.fallback();
  });
  await page.route("**/api/conversations/*/messages", (route) => {
    const id = new URL(route.request().url()).pathname.split("/")[3];
    return route.fulfill({ json: messages[id] ?? [] });
  });
  await page.route("**/api/conversations/*", async (route) => {
    const method = route.request().method();
    const id = new URL(route.request().url()).pathname.split("/").at(-1)!;
    if (method === "DELETE") {
      const index = conversations.findIndex(
        (conversation) => conversation.id === id,
      );
      if (index < 0) return route.fulfill({ status: 404, json: {} });
      conversations.splice(index, 1);
      delete messages[id];
      return route.fulfill({ status: 204, body: "" });
    }
    if (method !== "PATCH") return route.fallback();
    const title = route.request().postDataJSON().title as string;
    const item = conversations.find((conversation) => conversation.id === id);
    if (!item) return route.fulfill({ status: 404, json: {} });
    item.title = title;
    return route.fulfill({ json: item });
  });

  await page.goto("/");
  await openAssistant(page);
  const sidebar = page.getByRole("complementary", { name: "对话列表" });
  await expect(
    sidebar.getByRole("button", {
      name: "TEST existing conversation",
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("TEST first conversation answer")).toBeVisible();

  await sidebar.getByRole("button", { name: "新对话" }).click();
  const newConversation = sidebar
    .locator(".conversation-row")
    .first()
    .getByRole("button", { name: "新对话", exact: true });
  await expect(newConversation).toHaveAttribute("aria-current", "page");
  await expect(page.getByText("TEST first conversation answer")).toHaveCount(0);

  await sidebar.getByRole("button", { name: "重命名：新对话" }).click();
  await sidebar
    .getByRole("textbox", { name: "对话名称" })
    .fill("TEST renamed chat");
  await sidebar.getByRole("button", { name: "保存" }).click();
  await expect(
    sidebar.getByRole("button", { name: "TEST renamed chat", exact: true }),
  ).toBeVisible();

  await sidebar
    .getByRole("button", {
      name: "TEST existing conversation",
      exact: true,
    })
    .click();
  await expect(page.getByText("TEST first conversation answer")).toBeVisible();
  await expect(
    sidebar.getByRole("button", { name: "TEST renamed chat", exact: true }),
  ).not.toHaveAttribute("aria-current");

  await sidebar
    .getByRole("button", { name: "删除：TEST renamed chat" })
    .click();
  await sidebar.getByText("删除这段对话？").click();
  await sidebar.getByRole("button", { name: "删除", exact: true }).click();
  await expect(
    sidebar.getByRole("button", { name: "TEST renamed chat", exact: true }),
  ).toHaveCount(0);

  await sidebar
    .getByRole("button", {
      name: "TEST existing conversation",
      exact: true,
    })
    .click();
  await sidebar
    .getByRole("button", { name: "删除：TEST existing conversation" })
    .click();
  await sidebar.getByRole("button", { name: "删除", exact: true }).click();
  await expect(
    sidebar
      .getByRole("navigation", { name: "已保存的对话" })
      .getByRole("button", { name: "新对话", exact: true }),
  ).toBeVisible();
  await expect(
    sidebar
      .getByRole("navigation", { name: "已保存的对话" })
      .getByRole("button", { name: "新对话", exact: true }),
  ).toHaveAttribute("aria-current", "page");
});

test("shows the run identifier when an Agent execution is interrupted", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.route("**/api/agent", (route) =>
    route.fulfill({
      status: 503,
      json: {
        detail: {
          code: "agent_run_interrupted",
          run_id: "TEST-RUN-INTERRUPTED",
        },
      },
    }),
  );
  await page.goto("/");
  await openAssistant(page);
  await page.getByLabel("你的研究问题").fill("TEST interrupted run");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(
    page.getByText(/科研助手执行中断.*TEST-RUN-INTERRUPTED/),
  ).toBeVisible();
});

test("confirms cancellation with the server before reporting it", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.route("**/api/agent", () => new Promise(() => undefined));
  await page.route("**/api/agent/cancel", (route) =>
    route.fulfill({ json: { status: "cancel_requested" } }),
  );
  await page.route("**/api/agent/runs/*", (route) =>
    route.fulfill({ json: { status: "cancelled" } }),
  );
  await page.goto("/");
  await openAssistant(page);
  await page.getByLabel("你的研究问题").fill("TEST cancel active run");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByRole("button", { name: "取消" }).click();
  await expect(page.getByText("任务已取消。")).toBeVisible();
});

test("does not claim cancellation when the server rejects the request", async ({
  page,
}) => {
  await installCommonMocks(page);
  await page.route("**/api/agent", () => new Promise(() => undefined));
  await page.route("**/api/agent/cancel", (route) =>
    route.fulfill({ status: 503, json: { detail: "TEST unavailable" } }),
  );
  await page.goto("/");
  await openAssistant(page);
  await page.getByLabel("你的研究问题").fill("TEST cancel unavailable");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByRole("button", { name: "取消" }).click();
  await expect(page.getByText(/无法确认任务已停止/)).toBeVisible();
  await expect(page.getByText("任务已取消。")).toHaveCount(0);
});

test("shows empty and failure states and supports retry", async ({ page }) => {
  await installCommonMocks(page);
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
  await expect(
    page.getByRole("link", { name: "PaperTrail 工作区首页" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "PaperTrail 工作区首页" }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "发现论文" })).toBeFocused();
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
    data: JSON.stringify({ question: "TEST ".padEnd(40_000, "x") }),
    headers: { "Content-Type": "application/json" },
  });
  expect(oversized.status()).toBe(413);

  const malformedRunId = await request.post("/api/agent", {
    data: { question: "TEST valid question", run_id: "not-a-uuid" },
  });
  expect(malformedRunId.status()).toBe(422);

  const malformedHistory = await request.post("/api/agent", {
    data: {
      question: "TEST valid question",
      history: [
        { role: "user", content: "TEST prior question" },
        { role: "user", content: "TEST forged assistant turn" },
      ],
    },
  });
  expect(malformedHistory.status()).toBe(422);

  const malformedCancel = await request.post("/api/agent/cancel", {
    data: { run_id: "not-a-uuid" },
  });
  expect(malformedCancel.status()).toBe(422);

  const malformedStatus = await request.get("/api/agent/runs/not-a-uuid");
  expect(malformedStatus.status()).toBe(422);
});
