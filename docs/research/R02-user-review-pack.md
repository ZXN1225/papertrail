# R02 原文与解析结果对照

## 文件身份与边界

- 源文件：`An integrated diffusion-weighted.pdf`，29 页。
- 本机 SHA-256：`7d664debd8dc5c83119c0b1b64a9d8ef2a277eca54cea402dd786fd9d311ce31`。
- 论文文件未被改写。以下表格内容为 `pdfplumber-layout-v6` 从原件生成的检索 chunk；截图中的 PDF 原文应当与首次下载时完全相同。
- `retrieval chunk` 是送入 RAG 检索的规范化文本；`evidence excerpt` 保留表格数据行在源文本中的连续摘录和 locator。重复表头只作检索上下文，不混入数据行 excerpt。

## 第 6 页：Table 1

PDF 原文把最后一列的词折到下一物理行（`stream-` / `ing`，`denois-` / `ing`）。当前检索 chunk 为：

```text
Component | Version | Role in the platform
Python | 3.10 | Implementation language
Flask / Flask-SocketIO | 2.3 / 5.5 | Web server and real-time progress streaming
PyTorch | 2.6 (CUDA 12.6) | Deep-learning models (distortion, denoising, fitting)
pydicom | 3.0.1 | DICOM reading and metadata extraction
nibabel | 5.3.2 | NIfTI input/output
SimpleITK | 2.4.1 | Reorientation, resampling, geometry
MONAI | 1.4.0 | Medical-image transforms
NumPy / SciPy | 1.26 / 1.15 | Numerical computation and optimization
LangChain / LangGraph | n/a | Agent orchestration and tool calling
Azure OpenAI (GPT-5.1) | n/a | Large-language-model reasoning
|  | (HIPAA-compliant)
```

Locator：`第 6 页 · 2 Methods / 2.1 System overview and architecture · table · 行 3-15`。

## 第 14 页：Table 2

截图确认原表可见列为 Attribute、Categories (examples)、Coverage。当前 chunk 已将物理提取中的空表头子列归回 Categories：

```text
Attribute | Categories (examples) | Coverage
Tumor type | Glioblastoma / glioma / brain metastases | predominant
| Pancreatic adenocarcinoma; head and neck; | secondary
| prostate |
Parameters | ADC | 28 papers
| IVIM (f , D , D ) p t p | 13 papers
Setting | MR-Linac / MR-guided radiotherapy; |
| chemoradiation |
Evidence | Original studies, systematic reviews/meta-analyses, position statements | mixed
```

Locator：`第 14 页 · 2 Methods / 2.5 Retrieval-augmented clinical-interpretation agent · table · 行 3-6,8-12`。

## 第 18、19 页：Figure 6、Figure 7

区域坐标格式为 PDF points：`[x0, top, x1, bottom]`，原点位于页面左上。它们只定位矢量图外框，不表示解析了图内曲线或数据。

| PDF 页 | 图注 | 矢量区域 bbox | 图注 bbox | 关系 |
| --- | --- | --- | --- | --- |
| 18 | Figure 6: A representative longitudinal GBM case… | `[95.4, 152.55, 516.6, 561.74]` | `[72.0, 572.4, 540.0, 583.31]` | matched，`vector_boundary` |
| 19 | Figure 7: Independent expert ratings… | `[107.1, 72.0, 504.91, 315.75]` | `[72.0, 326.4, 540.0, 337.31]` | matched，`vector_boundary` |

## 第 20 页：Table 3

当前 chunk 抽到均值 ± 标准差；`±` 的 Unicode 码点是 U+00B1。

```text
Clinical-reasoning soundness | 5.00±0.00 | 4.22±1.20 | 4.61±0.92
Literature-citation quality | 4.56±0.53 | 4.44±1.33 | 4.50±0.99
Overall clinical utility | 4.78±0.44 | 4.89±0.33 | 4.83±0.38
Overall | 4.78±0.42 | 4.52±1.05 | 4.65±0.80
```

## 已确认范围与 v6 补充

用户在 2026-10-12 回复“看起来没什么问题，请你继续”，据此记录所展示的单篇表格和 Figure 6/7 locator 抽样可继续使用。此后 v6 将 x_tolerance=2 用于定位文字抽取，在原 PDF 重新解析及索引检索中确认图注间距已恢复：

```text
Figure 7: Independent expert ratings of agent-generated reports by metric and rater (mean ± SD;
Table 3: Expert evaluation of agent-generated reports on nine longitudinal GBM cases. Values are
```

v6 图注修复通过回归并已做本机索引检索验证，尚未单独做用户视觉复核。Table 2 IVIM 下标错序、无 OCR、无图表语义读取仍是已知限制；该样本不证明一般 PDF 准确率。
