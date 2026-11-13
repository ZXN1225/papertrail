# PaperTrail 总体改进方案

## 产品目标

把 PaperTrail 扩展为支持账号登录、个人论文库和科研写作助手的多用户应用。用户在“论文发现”工作区搜索 OpenAlex/arXiv 论文、查看原文链接并将元数据加入个人库；在“科研助手”工作区基于个人论文库和获准全文进行研究问答、文献比较及草稿修改。

## 核心产品边界

- 账号采用唯一账号名 + 密码；密码只存专用密码哈希，绝不存明文。
- 私有论文、全文、草稿、会话和消息都归属用户；每个后端请求验证资源所有权。
- 添加论文元数据不等于许可下载全文。共享全文继续要求逐篇核验许可；用户可以逐篇声明其拥有私有 PDF 版权或已获授权，该声明仅支持本人账号内的处理和检索，不转为共享语料授权。
- 用户草稿与发表论文分开存储。研究事实回答必须引用本轮检索证据；写作建议区分原文、建议和待核验事实。
- 外部论文和解析文本是不可信内容。Agent 只使用固定、只读、有限工具，不提供任意 URL、文件、shell、SQL 或自由写库能力。

## 工作区

### 论文发现与个人论文库

提供 OpenAlex/arXiv 检索、年份/作者/主题过滤、论文详情、来源与原文链接；支持加入个人库、去重、搜索、查看、移除。个人库条目可标记仅元数据、许可待核、已许可全文、解析中、解析失败等状态。

### 科研与写作助手

支持私有会话历史、新建/重命名/清空/删除；基于用户选择的个人论文、获准共享全文和该用户声明授权的私有全文进行证据问答、文献综合、论文比较、研究问题拆解、草稿结构建议和语言修改。提供独立“我的稿件”入口，让未发表论文以标题和 PDF 上传到本人私有空间，无需虚构 OpenAlex/arXiv 来源；引用只指向该私有稿件及页码/元素。草稿与外部发表论文在来源类型和界面上分开，不能编造公开链接或参考文献。

## 任务型 Skills

按需注册精简的技能：文献检索筛选、证据综合、论文比较、研究问题/假设拆解、学术写作修改、引用核验。Skills 仅指导工作方法，不能赋予工具权限。外部 Skill 逐个审查来源、许可、依赖和提示注入风险；Agent 运行仍受固定后端白名单和数据权限约束。首版采用单 Agent + skills；多 Agent 仅在同一冻结评测集上证明质量/效率提升后再启用。

## PDF 解析和 RAG

目标解析器采用 MinerU，以覆盖复杂版式、公式、表格和 OCR；通过版本化迁移接管现有 PDF 解析索引。保存源 PDF SHA-256、来源、许可凭据、解析器版本/配置、页码、bbox、元素类型、结构化内容及 warning。解析结果可审查、可重建，失败和不确定状态不得静默当作正确证据。部署需评估本地计算资源与数据是否离开用户控制边界。

首版 RAG 采用：

1. 按 MinerU 标题、段落、表格、公式等结构切分，保留章节路径、页码、bbox、父子元素关系。
2. 小片段精确召回，命中后只扩展同一结构单元或有限邻接片段。
3. BM25 + Dense 混合召回，RRF 融合、去重及用户/论文/许可过滤。
4. 保留 query、chunk、索引版本 lineage；引用回指原页和原始元素。
5. 先建立可评测基线，再逐步实验 contextual retrieval、HyDE、问题分解和重排。生成的假设/上下文只能辅助召回，不能作为证据。

每项升级用同一冻结题集比较 Hit@k、MRR、NDCG、证据定位、引用错误、分题型表现、延迟和成本。AI 标注数据不称为人工金标。

## 技术选择

- 当前后端：FastAPI、Pydantic、SQLite 版本化迁移；前端：Next.js/React/TypeScript；维持当前工具链，先做最小增量。
- 多用户本地演示继续 SQLite；公开部署时评估 PostgreSQL 与私有对象存储。数据库只存文件元数据/存储键，禁止公开静态暴露全文。
- 账号使用 Argon2id 或同等专用密码哈希、服务端 session cookie（HttpOnly、Secure、SameSite）、登录限速。
- MinerU 作为独立解析适配器/任务步骤，锁定版本和模型配置，输出统一 PaperTrail 结构。

## 实施阶段

1. 数据模型、部署边界、账号/所有权设计与迁移准备。
2. 唯一账号注册登录、会话、资源隔离。
3. 个人元数据论文库与来源搜索联动。
4. 文件许可状态、MinerU 解析、结构化索引及检索基线。
5. 私有对话历史、任务 skills、研究模式与写作模式。
6. 双工作区 UI、错误/空/处理中/权限状态和 E2E 流程。
7. 安全、检索质量、成本和恢复评测；按证据再加入高级 RAG/多 Agent。

## 验收底线

- 同名账号注册冲突；登录失败限速；明文密码不存在于数据库/日志。
- 用户 A 无法读写用户 B 的任一论文、文件、草稿、会话或消息。
- 未经逐篇许可核验的共享全文不能进入共享解析和检索；用户声明拥有版权/已获授权的文稿只能进入本人私有处理空间。删除全文清除文件及派生索引。
- MinerU 输出具有稳定版本和来源定位；测试包含复杂表格、公式、双栏和扫描 PDF，并披露失败。
- Agent 工具拒绝非白名单参数；证据回答的 citation ID 来自本轮工具结果。
- 文档、检索/索引、API、前端主路径均有测试和可复现验收记录。

## 明确暂缓

不做任意网页抓取/自动批量下载、未经许可全文镜像、默认多 Agent、未经评测的 HyDE/生成式上下文、机构共享、社交登录或跨用户长期记忆。

## 官方资料

- [MinerU Quick Usage](https://opendatalab.github.io/MinerU/usage/quick_usage/)
- [MinerU Output Format](https://opendatalab.github.io/MinerU/reference/output_files/)
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/research/contextual-retrieval)
- [arXiv API Terms of Use](https://info.arxiv.org/help/api/tou.html)
- [OpenAlex Authentication and Rate Limits](https://help.openalex.org/api/authentication/)
