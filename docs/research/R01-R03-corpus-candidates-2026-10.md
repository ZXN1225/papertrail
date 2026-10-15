# R01–R03 新增许可语料候选（2026-10）

状态：候选清单，**尚未获用户逐篇确认，也未下载或导入 PDF**。核查日期：2026-10-13。目标是从当前 4 篇真实许可全文扩至 10–12 篇；建议先选 6–8 篇，并尽量覆盖 Agent/RAG、长篇综述、复杂表格、密集图注/实验结果和跨栏正文。

## 候选论文

| 选择 | arXiv | 建议评测价值 | arXiv 页面显示的版本/长度 | 许可核验 | 选择后由用户提供 |
|---|---|---|---|---|---|
| [ ] | [2609.09203](https://arxiv.org/abs/2609.09203) OpenDiscoveryTrace: Process Traces for Evaluating AI Scientist Workflows | Agent 执行轨迹、工具调用、错误分类及基准定义；适合 Agent/harness 主张和流程证据定位 | v1；arXiv 页面未列页数 | 页面 `view license` 链接指向 CC BY 4.0；摘要说明公开数据集/轨迹采用 CC BY 4.0。**论文 PDF 的具体复用仍需用户对照页面许可入口确认** | 本机 PDF 路径，或确认由你从 arXiv 下载指定版本；逐篇许可确认 |
| [ ] | [2308.06374](https://arxiv.org/abs/2308.06374) Large Language Models and Knowledge Graphs: Opportunities and Challenges | 30 页长综述/立场论文；适合多节标题、长距离段落、表格和引用密集检索 | v1；30 页 | arXiv `view license` 链接指向 CC BY 4.0 | 本机 PDF 路径/版本确认 |
| [ ] | [2407.08012](https://arxiv.org/abs/2407.08012) Measurement of boosted Higgs bosons … using LHC proton-proton collision data | CMS 实验论文；多图、置信区间、物理量下标和结果表，适合检查图注/表格与数值对齐 | v2；arXiv 页面未列页数 | arXiv `view license` 链接指向 CC BY 4.0 | 本机 PDF 路径/版本确认 |
| [ ] | [2303.17357](https://arxiv.org/abs/2303.17357) Measurement of the Sensitivity of Two-Particle Correlations in pp Collisions … | ATLAS 实验论文；页面说明 34 页、8 figures；适合双栏、图注、物理量和多组条件对齐 | v2；34 页 | arXiv `view license` 链接指向 CC BY 4.0 | 本机 PDF 路径/版本确认 |
| [ ] | [2302.14165](https://arxiv.org/abs/2302.14165) GAM Coach: Towards Interactive and User-centered Algorithmic Recourse | 20 页、12 figures，含交互系统、用户研究和可视化；适合图文混排与方法/结果表述 | v2；20 页、12 figures | arXiv `view license` 链接指向 CC BY 4.0 | 本机 PDF 路径/版本确认 |
| [ ] | [2608.16042](https://arxiv.org/abs/2608.16042) TR-GS: High-Fidelity Sparse-View CT Volumetric Rendering via t-Distribution Gaussian Splatting and Ray-Confidence Modeling | 医学影像/3D 可视化；约 20 MB 的较大 PDF，可检查长图注、公式/符号和图文边界；只评文本/定位，不评图像像素或临床结论 | v1；PDF 约 20,324 KB | arXiv 页面摘要明确写明 CC BY 4.0，`view license` 也指向 CC BY 4.0 | 本机 PDF 路径/版本确认 |

这 6 篇是经过 arXiv 页面许可入口初筛的候选，并非已确认可导入清单。arXiv 页面报告页数不完整时，导入前仍要从用户提供的具体 PDF 确认版本、页数和许可页。请勿依据数据集、代码或关联期刊的单独许可推断论文 PDF 许可。

## 不纳入本候选表的例子

- [2312.10997](https://arxiv.org/abs/2312.10997) 与 [2401.03428](https://arxiv.org/abs/2401.03428) 的 arXiv 许可入口显示为 arXiv non-exclusive distribution license，不符合当前项目仅接收 CC0/CC BY-4.0 的导入白名单。即使主题相关也不导入。
- [2606.29243](https://arxiv.org/abs/2606.29243) 页面许可入口同样显示 arXiv non-exclusive distribution license；论文摘要提到 benchmark/resource 发布，不等于论文 PDF 使用 CC BY。
- 许可白名单和仓库保留署名/来源/版本/哈希的要求见 [项目全文许可边界](../PROJECT_SPEC.md)。CC BY 要求署名、许可链接并标明修改；候选 PDF 仍由用户逐篇确认。

## 下一步

1. 从本表选择至少 6 篇，或告诉我优先侧重的学科/版式，我继续扩充清单；为了达到 10–12 篇语料目标，当前 4 篇加齐 6 篇可到 10 篇。
2. 为每篇核对**具体 arXiv 版本**的许可页，提供本机 PDF 路径并确认许可；我再检查文件 SHA、版本、版式特征和 manifest。
3. 许可通过后才本机导入。论文全文、PDF、SQLite、模型报告不进入 Git。
4. 冻结语料与任务前，独立复核 v15 A1/B2 新输出；随后开展离线检索/解析评测，付费模型评测另需新授权。
