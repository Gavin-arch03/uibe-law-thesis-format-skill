---
name: law-thesis-format
description: 中国法学学位论文的格式、结构与引注核查。当用户要撰写或修改法学学位论文、核对格式是否符合学校或学院规范、从 Zotero 文献库生成法学体例的参考文献表与脚注、从一批样本论文中反推排版参数与章节目录骨架、或体检 .docx 论文格式问题时使用。内置对外经济贸易大学法学院 2020 体例 profile。
agent_created: true
---

# 法学学位论文格式核查

## 用途

把「学校/学院的文字规定」与「一批真实论文 PDF」两条线索合起来，产出一份可执行的写作标准，然后据此核查用户的稿子。

核心判断：**同一所学校，学院细则通常与学校总规范冲突**（结论是否带章号、脚注编号方式、参考文献体例、行距、页边距）。学院优先，依据是学校规范里"各培养单位可另行制订"的授权条款。不要把这些冲突留成"建议问导师"，要裁决并记录理由。

## 何时使用

- 用户要写/改法学学位论文，问格式怎么设
- 用户给了一份学校或学院的写作规范 PDF，要提炼成可执行清单
- 用户要把 Zotero 里的文献生成参考文献表或脚注
- 用户给了一批往届论文，要摸清结构与引注习惯
- 用户要体检自己的 .docx 是否符合规范

## 工作流

### A. 建立规范基线（每个学校做一次）

1. 读全部规范 PDF。用 `scripts/pdf_probe.py dump` 导出文本便于检索。
2. 用 `scripts/pdf_probe.py layout` 量**官方格式示例**的真实参数。**示例实测值优先于文本描述**——文字写 3.6cm、示例实际 2.8cm 是常见情况（本项目即如此）。
3. 列出文件之间的冲突点，按下面的顺序裁决：
   - 学院细则 > 学校总规范
   - 专管某事项的文件（《…体例》）> 综合示例（《…格式示例》）
   - 仍无法裁决 → 取样本库多数做法，记入 profile 的 `known_conflicts`
4. 把结论写进 `assets/profiles/<id>.json` 与 `references/<id>.md`。迁移方法见 `references/adapting-other-schools.md`。

### B. 从样本库提炼结构与引注

1. **先做版本判定**，否则会把知网裁边版的假参数当真：

   ```bash
   python scripts/pdf_probe.py version 某篇.pdf
   ```

   学校提交版 = A4 210×297mm、正文 12pt；知网裁边版 = 197–206 × 288–294mm、正文 10.2/10.5pt。
   **只有 A4 版能读排版参数；结构、逻辑链、引注体例则任何版本都可信。**

2. 批量分析（Zotero 集合或目录）：

   ```bash
   python scripts/analyze_collection.py --collection <key> --out 样本报告.md
   python scripts/analyze_collection.py --dir D:/theses --out 样本报告.md
   ```

   产出：版本可信度、逐篇明细、章数分布、逻辑链模式、引注体例分布、各部分覆盖率。

3. 单篇看骨架：

   ```bash
   python scripts/pdf_probe.py outline 某篇.pdf
   ```

   解析器已做全角数字归一化，兼容知网版被拆成碎行的目录。若某篇只报出「1 章」，是目录解析失败，**不要采信该篇章数**，需人工看目录页。

### C. 生成参考文献与脚注

```bash
# 整个集合 → 参考文献表（五分类、【N】、类内时间降序、无页码）
python scripts/gen_references.py --collection <key> --out refs.md

# 单条脚注（必须有页码）
python scripts/gen_references.py --footnote <itemKey> --page 20
python scripts/gen_references.py --footnote <itemKey> --page 20 --prefix 参见
```

**不要试图用 CSL 自动生成法学体例**：法学院体例是「中文法学手册格式 + 英文 Bluebook」的混合体，要求必须有页码、期刊不出现"卷"、网络资源不写网站名、参考文献一律无页码——任何现成 CSL 都对不上。用脚本拼装后人工微调。

脚本会在 stderr 列出缺字段的条目。**先回 Zotero 补齐字段再重跑，比在 Word 里手改更稳。**

### D. 体检 .docx

```bash
python scripts/check_docx.py 论文.docx --profile uibe-law-2020
python scripts/check_docx.py 论文.docx --out 体检报告.md
```

检查项：纸张/页边距/页眉/页码域、正文抽样字体字号行距缩进、四级编号、标题内标点、标题过短、结论章号、章号连续性、摘要字数、关键词分隔符与个数、参考文献括号类型/误带页码/分类/类内排序/条目数、脚注编号符号/"前引"用法/缺页码、中文总字数。

只做可机械判定的项。标题好不好、论证是否成立不在此列。

### E. 出目录草案

按 `references/structure-patterns.md` 的三种逻辑链选型，套官方范本的对仗规则：**问题清单与对策清单一一咬合，问题几条对策就几条**。

## 脚本

| 脚本 | 作用 |
|---|---|
| `scripts/zotero.py` | Zotero 本地 API 只读客户端（stats / collections / items / search / children / paths / tags） |
| `scripts/pdf_probe.py` | PDF 探针：`layout` 量排版、`outline` 提骨架、`sections` 查 12 部分、`version` 判版本、`dump` 导文本 |
| `scripts/analyze_collection.py` | 批量分析一批论文，出 Markdown 报告 |
| `scripts/gen_references.py` | 生成法学体例参考文献表与单条脚注 |
| `scripts/check_docx.py` | 按 profile 体检 .docx |

依赖：`pymupdf`、`python-docx`。Zotero 相关功能需客户端运行且已勾选 编辑→设置→高级→「允许此计算机上的其他应用程序与 Zotero 通信」。

## 参考文档

- `references/uibe-law-2020.md` — 对外经贸大学法学院 2020 完整规则（含 11 项冲突裁决、实测排版参数、数量下限）
- `references/citation-law-cn.md` — 中文九类脚注格式 + Bluebook 英文引注 + 参考文献五分类
- `references/structure-patterns.md` — 三种逻辑链、官方目录范本、标题拟定的反例正例、样本统计
- `references/adapting-other-schools.md` — 迁移到其他学校、从样本反推规则、常见坑

## 回答用户时的口径

- 先给结论（采用哪个值），再给依据（哪份文件、哪条原文、或哪次实测）
- 涉及冲突时**必须裁决**，不要输出"两者都可以，建议问导师"
- 引用格式问题说明用的是哪个体例（法学院体例 / GB/T 7714 / Bluebook）
- 排错按「现象 → 原因 → 解决」三步
- 涉及删除、合并、批量改库等破坏性操作，先提醒备份 Zotero data directory
- 收尾给可核对的交付件（表格或可粘贴文本），不要只给口头清单
