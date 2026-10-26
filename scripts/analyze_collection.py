#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量分析一批学位论文 PDF，输出「结构 + 引用体例 + 排版可信度」报告。

典型用途
--------
手头有一批同门/同校的学位论文（例如 Zotero 里某个「毕业论文模板」集合），
想快速搞清楚：
  1. 哪些能当排版范本（学校提交版），哪些只能看结构（知网裁边版）；
  2. 章节骨架的主流形态是什么（几章、什么逻辑链）；
  3. 大家实际用什么引注体例（法学体例 / GB/T 7714）；
  4. 字数、摘要长度、参考文献数量的分布。

用法
----
    python analyze_collection.py --collection GC7ZATAJ --out report.md
    python analyze_collection.py --pdf "a.pdf" "b.pdf" --out report.md
    python analyze_collection.py --dir D:/theses --out report.md
    python analyze_collection.py --collection GC7ZATAJ --json

依赖：pymupdf；若用 --collection 还需 zotero.py 与运行中的 Zotero。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics as st
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pdf_probe as P
except ImportError:
    sys.exit("找不到 pdf_probe.py，请与本脚本放在同一目录")

LOGIC_KW = OrderedDict([
    ("导论", r"导论|绪论|引言"),
    ("概述界定", r"概述|基础理论|基本理论|法律释义|概念|界定|理论|认定"),
    ("现状检视", r"现状|实证|考察|检视|梳理|沿革"),
    ("问题困境", r"问题|困境|障碍|不足|局限|挑战|冲突"),
    ("成因分析", r"成因|原因|根源|缘由"),
    ("域外借鉴", r"域外|境外|国外|比较|借鉴|经验|评析"),
    ("完善建议", r"完善|建议|路径|构建|建构|对策|改进|优化|规制|救济"),
    ("结论", r"结论|结语|总结|余论|展望"),
])


def cjk_len(s: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def logic_chain(chapters):
    body = [(n, t) for n, t in chapters
            if not re.search(LOGIC_KW["结论"], t) and not (n == 1 and re.search(LOGIC_KW["导论"], t))]
    tags = []
    for _, t in body:
        hit = next((k for k, p in LOGIC_KW.items() if k not in ("结论", "导论") and re.search(p, t)), "其他")
        if not tags or tags[-1] != hit:
            tags.append(hit)
    return tags


def cite_style(full: str):
    nianban = len(re.findall(r"年版", full))
    gbt = len(re.findall(r"\[[MJDCGNS]\]", full))
    if nianban > 5 and nianban > gbt * 2:
        return "法学体例（《》+年版）", nianban, gbt
    if gbt >= 10:
        return "GB/T 7714（[M]/[J]）", nianban, gbt
    if nianban or gbt:
        return "混合/待定", nianban, gbt
    return "未识别", nianban, gbt


def ref_count(full: str):
    idx = full.rfind("参考文献")
    if idx < 0:
        return 0
    seg = full[idx:]
    n = len(re.findall(r"(?m)^\s*[\[【]\s*\d{1,3}\s*[\]】]", seg))
    if n == 0:
        n = len(re.findall(r"(?m)^\s*\d{1,3}[.．、]\s*\S", seg))
    return n


def abstract_len(full: str):
    m = re.search(r"摘\s*要(.{200,6000}?)(关键词|关键字)", full, re.S)
    return cjk_len(m.group(1)) if m else 0


def analyze_one(path: str, title: str = "", key: str = ""):
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf

    doc = pymupdf.open(path)
    try:
        full = "\n".join(p.get_text("text") for p in doc)
        pages = doc.page_count
        # 排版测量只抽样正文中段约 10 页，避免整本做字形级解析（30 篇规模会非常慢）
        start = max(1, pages // 3)
        spec = f"{start}-{min(pages, start + 9)}" if pages > 16 else ""
        lay = P.layout(pages_spec=spec, doc=doc)
        sec = P.sections(doc=doc)["sections"]
        out = P.outline(doc=doc)
    finally:
        doc.close()

    ver = P.judge_version(lay)
    style, nianban, gbt = cite_style(full)
    chap_all = out["chapters"]
    return {
        "key": key,
        "title": title or os.path.basename(path),
        "path": path,
        "pages": pages,
        "chars": cjk_len(full),
        "page_size": ver["page"],
        "body_size_pt": ver["body_size_pt"],
        "version": ver["verdict"],
        "template_usable": ver["template_usable"],
        "sections": sec,
        "n_chapter": len(chap_all),
        "chapters": chap_all,
        "conclusion_numbered": any(re.search(LOGIC_KW["结论"], t) for _, t in chap_all),
        "logic_chain": logic_chain(chap_all),
        "cite_style": style,
        "n_nianban": nianban,
        "n_gbt": gbt,
        "n_refs": ref_count(full),
        "abstract_chars": abstract_len(full),
        "n_canjian": full.count("参见"),
        "n_fig": len(re.findall(r"图\s*\d{1,2}[.\-－]\d{1,2}", full)),
        "n_tab": len(re.findall(r"表\s*\d{1,2}[.\-－]\d{1,2}", full)),
    }


def collect_paths(args):
    if args.collection:
        from zotero import Zotero
        z = Zotero()
        if not z.ping():
            sys.exit("连不上 Zotero。请确认客户端已启动且已开启本地 API。")
        items = z.collection_items(args.collection)
        out = []
        for i in items:
            d = i["data"]
            pdfs = z.pdfs(d["key"])
            out.append((pdfs[0] if pdfs else None, d.get("title", ""), d["key"]))
        return out
    if args.dir:
        out = []
        for f in sorted(os.listdir(args.dir)):
            if f.lower().endswith(".pdf"):
                out.append((os.path.join(args.dir, f), os.path.splitext(f)[0], ""))
        return out
    return [(p, "", "") for p in (args.pdf or [])]


def median(vals):
    vals = [v for v in vals if v is not None]
    return st.median(vals) if vals else 0


def render(rows, meta=""):
    ok = [r for r in rows if "error" not in r]
    L = []
    L.append("# 学位论文样本分析报告")
    if meta:
        L.append(f"\n> {meta}")
    L.append(f"\n样本数：{len(rows)}　可分析：{len(ok)}")

    school = [r for r in ok if r["version"] == "school_submission"]
    cnki = [r for r in ok if r["version"] == "cnki_cropped"]
    L.append("\n## 一、版本可信度\n")
    L.append("| 判定 | 篇数 | 含义 |")
    L.append("|---|---|---|")
    L.append(f"| 学校提交版（A4） | {len(school)} | 排版 + 结构 + 引用全部可信 |")
    L.append(f"| 知网裁边版 | {len(cnki)} | 仅结构 / 逻辑 / 引用可信，排版不可信 |")
    L.append(f"| 其他 | {len(ok) - len(school) - len(cnki)} | 需人工判断 |")
    if school:
        L.append("\n**可作排版范本：**")
        for r in school:
            L.append(f"- {r['title'][:50]}（{r['page_size']}mm，正文 {r['body_size_pt']}pt）")

    L.append("\n## 二、逐篇明细\n")
    L.append("| # | 论文 | 页 | 字数 | 章 | 摘要字 | 参考条 | 引注体例 | 可信 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(ok, 1):
        L.append(f"| {i} | {r['title'][:26]} | {r['pages']} | {r['chars']} | {r['n_chapter']} | "
                 f"{r['abstract_chars']} | {r['n_refs']} | {r['cite_style']} | "
                 f"{'✅排版' if r['template_usable'] else '结构' } |")

    L.append("\n## 三、结构统计\n")
    cc = Counter(r["n_chapter"] for r in ok if r["n_chapter"] > 0)
    L.append("**章数分布：** " + "、".join(f"{k} 章 {v} 篇" for k, v in sorted(cc.items())))
    L.append(f"\n**字数：** 中位 {median([r['chars'] for r in ok]):.0f}　"
             f"范围 {min(r['chars'] for r in ok)}–{max(r['chars'] for r in ok)}")
    L.append(f"\n**摘要字数：** 中位 {median([r['abstract_chars'] for r in ok if r['abstract_chars'] > 100]):.0f}")
    L.append(f"\n**页数：** 中位 {median([r['pages'] for r in ok]):.0f}")
    L.append("")

    chain_cnt = Counter(" → ".join(r["logic_chain"]) for r in ok if r["logic_chain"])
    L.append("**逻辑链模式（按章标题关键词自动归纳）：**\n")
    L.append("| 篇数 | 逻辑链 |")
    L.append("|---|---|")
    for k, v in chain_cnt.most_common(10):
        L.append(f"| {v} | {k or '（未识别）'} |")

    L.append("\n## 四、引注体例\n")
    sc = Counter(r["cite_style"] for r in ok)
    for k, v in sc.most_common():
        L.append(f"- {k}：{v} 篇")
    L.append(f"\n「参见」出现次数中位：{median([r['n_canjian'] for r in ok]):.0f}（反映脚注式引用强度）")

    L.append("\n## 五、结论号与图表\n")
    L.append(f"- 结论带章号：{sum(1 for r in ok if r['conclusion_numbered'])}/{len(ok)} 篇")
    L.append(f"- 有分章编号图表：{sum(1 for r in ok if r['n_fig'] or r['n_tab'])}/{len(ok)} 篇"
             f"（法学论文普遍不用图表）")

    L.append("\n## 六、各部分覆盖率\n")
    secs = ["原创性声明", "版权授权书", "中文摘要", "英文摘要", "目录", "参考文献", "附录", "致谢", "个人简历"]
    L.append("| 部分 | 篇数 |")
    L.append("|---|---|")
    for s in secs:
        L.append(f"| {s} | {sum(1 for r in ok if r['sections'].get(s))}/{len(ok)} |")

    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="批量分析学位论文样本")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--collection", help="Zotero 集合 key")
    src.add_argument("--dir", help="PDF 所在目录")
    src.add_argument("--pdf", nargs="+", help="一个或多个 PDF 路径")
    ap.add_argument("--out", help="输出 Markdown 路径")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    targets = collect_paths(args)
    rows = []
    for path, title, key in targets:
        if not path or not os.path.exists(path):
            rows.append({"title": title, "key": key, "error": "PDF 文件不存在"})
            continue
        try:
            r = analyze_one(path, title, key)
            rows.append(r)
            if not args.quiet:
                print(f"✓ {r['title'][:40]:<42} 页{r['pages']:<4} 章{r['n_chapter']:<3} "
                      f"{r['cite_style']:<18} {'A4' if r['template_usable'] else '裁边'}", file=sys.stderr)
        except Exception as e:
            rows.append({"title": title, "key": key, "error": str(e)})
            print(f"✗ {title[:40]} — {e}", file=sys.stderr)

    if args.json:
        text = json.dumps(rows, ensure_ascii=False, indent=1)
    else:
        meta = f"来源：{'Zotero 集合 ' + args.collection if args.collection else (args.dir or 'PDF 列表')}"
        text = render(rows, meta)

    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
        print(f"\n已写入 {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
