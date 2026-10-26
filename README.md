# law-thesis-format · 法学学位论文格式核查 Skill

一个面向**中国法学院校学位论文**的 AI Skill：把学校/学院的文字规范与真实的往届论文 PDF 两条线索合起来，产出可执行的写作标准，并据此体检你的 `.docx` 稿子。

内置 **对外经济贸易大学法学院（2020 修订）** 完整体例，同时提供一套可迁移的方法，用于其他院校。

## 解决什么问题

法学学位论文的格式规范通常有三层——学校研究生院的总规范、学院的细则、学院的格式示例——而它们**经常互相矛盾**。真实案例：

| 争议点 | 学校规范 | 学院细则 | 该用哪个 |
|---|---|---|---|
| 结论章号 | 不加章号 | 示例写「第6章 结论」 | 学院 |
| 脚注编号 | ①②③ 按页重编 | 全文连续 1、2、3 | 学院 |
| 参考文献 | GB/T 7714 | 五分类 + 【】+ 时间降序 | 学院 |
| 正文行距 | 22 磅 | 20 磅（实测 20.0pt） | 学院 |
| 页边距 | 上下 3.6cm | 实测上 2.8 / 下 2.5cm | 学院 |

人工核对这些问题要来回翻几十页 PDF、量几十个字体。这个 Skill 把它自动化了。

## 能力

| 能力 | 脚本 | 说明 |
|---|---|---|
| 判 PDF 是学校提交版还是知网裁边版 | `pdf_probe.py version` | 只有 A4 版能读排版参数；结构/引注任何版本都可读 |
| 量真实排版参数 | `pdf_probe.py layout` | 页面、页边距、字号众数、行距众数、字体 |
| 提章/节目录骨架 | `pdf_probe.py outline` | 兼容知网版被拆成碎行 + 全角数字的目录 |
| 批量分析一批论文 | `analyze_collection.py` | 出 Markdown 报告：版本可信度、章数分布、逻辑链、引注体例 |
| 从 Zotero 生成参考文献 | `gen_references.py` | 五分类、【N】、类内时间降序、无页码 |
| 生成单条脚注 | `gen_references.py --footnote` | 自动补「参见」、强制页码 |
| 体检 .docx | `check_docx.py` | 页边距、字体字号行距、四级编号、参考文献、脚注、字数等 20+ 项 |
| Zotero 只读客户端 | `zotero.py` | 本地 API 封装，可作模块复用 |

## 安装

把 `law-thesis-format/` 整个目录放进 skills 目录：

```bash
# Codex
git clone https://github.com/Gavin-arch03/uibe-law-thesis-format-skill.git ~/.codex/skills/law-thesis-format

# WorkBuddy
git clone https://github.com/Gavin-arch03/uibe-law-thesis-format-skill.git ~/.workbuddy/skills/law-thesis-format
```

或在支持 Skill 的 Agent 里直接把本目录作为 skill 加载。

依赖：

```bash
pip install pymupdf python-docx
```

Zotero 相关功能需：Zotero 7+ 客户端运行中，并勾选 **编辑 → 设置 → 高级 → 允许此计算机上的其他应用程序与 Zotero 通信**。

## 用法

### 1. 判一篇论文能不能当排版范本

```bash
python scripts/pdf_probe.py version 某篇.pdf
```

```
判定：school_submission
理由：页面为标准 A4
页面：210x297mm　正文主字号：12.0pt
可否作为排版范本：可以
```

### 2. 量官方格式示例的真实参数

```bash
python scripts/pdf_probe.py layout 格式示例.pdf --pages 11-25
```

会输出页边距众数、字号分布、行距分布。**以实测值为准，不要直接信文件里的文字描述。**

### 3. 批量分析一个 Zotero 集合

```bash
python scripts/analyze_collection.py --collection GC7ZATAJ --out 样本报告.md
```

报告含：版本可信度、逐篇明细、章数分布、逻辑链模式、引注体例分布、各部分覆盖率。

### 4. 生成参考文献

```bash
python scripts/gen_references.py --collection X7ZTNKYJ --out refs.md
```

输出：

```
参考文献

二、中文论文
【1】郑志峰：《医疗人工智能的个人信息保护》，载《法学论坛》2026年第5期。
【2】林勇涛：《医疗人工智能、医疗决策与医疗说明义务》，载《德国研究》2025年第4期。
...
```

类内自动按时间降序，跨类连续编号，一律不带页码。

### 5. 体检自己的论文

```bash
python scripts/check_docx.py 论文.docx --out 体检报告.md
```

输出「通过 / 警告 / 不通过」清单，末尾列出必须先修的项。

## 目录结构

```
law-thesis-format/
├── SKILL.md                        # 技能定义与工作流
├── README.md
├── LICENSE
├── scripts/
│   ├── zotero.py                   # Zotero 本地 API 只读客户端
│   ├── pdf_probe.py                # PDF 探针（layout / outline / sections / version / dump）
│   ├── analyze_collection.py       # 批量样本分析
│   ├── gen_references.py           # 参考文献与脚注生成
│   └── check_docx.py               # docx 格式体检
├── references/
│   ├── uibe-law-2020.md            # 对外经贸大学法学院完整规则
│   ├── citation-law-cn.md          # 中文九类脚注 + Bluebook + 参考文献五分类
│   ├── structure-patterns.md       # 三种逻辑链、官方目录范本、标题反例正例
│   └── adapting-other-schools.md   # 迁移到其他学校的方法
└── assets/
    └── profiles/
        └── uibe-law-2020.json      # 机器可读规则集
```

## 迁移到其他学校

新增一个 `assets/profiles/<id>.json` + `references/<id>.md` 即可，不需改代码。完整步骤见 `references/adapting-other-schools.md`。

要点：
1. 拿到官方格式示例，用 `pdf_probe.py layout` 量真实参数
2. 找出文件间的冲突，按「学院 > 学校」「专管文件 > 综合示例」裁决
3. 裁决理由记入 profile 的 `known_conflicts`，不要留"建议问导师"

## 已知局限

- **目录解析**：知网版目录常被拆成碎行，已做归一化，但约 10% 样本只能识别部分章。若某篇报「1 章」，是解析失败，需人工核对。
- **法学体例无现成 CSL**：中文法学手册格式 + 英文 Bluebook 的混合体，任何 CSL 都无法直接对上。`gen_references.py` 是模板拼装，输出需人工微调。
- **标题质量无法自动判定**："标题好不好"只能给人看；脚本只能查长度、标点、四级编号这类可机械判定的项。
- **OCR 错字**：知网 PDF 的文本层常有错字（如"研宄""虡假"），不影响结构判断，但引用书名须核对原书。

## 免责

- 本项目**不包含**任何学校的规定原件，仅记录公开规范的要义与实测参数，供学习与格式核对使用。
- 各校规范会修订，正式提交前请以你所在院校**最新官方文件**为准。
- 参考文献生成结果仅作初稿，条目内容准确性需自行核对。

## License

MIT
