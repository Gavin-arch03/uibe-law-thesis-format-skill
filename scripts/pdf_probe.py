#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF 排版参数探针：量页面、页边距、字号、行距、字体，并提取目录骨架。

为什么需要它
------------
判断一篇论文 PDF 是「学校提交版」还是「知网裁边版」，靠的就是页面尺寸与字号：
学校提交版恒为 A4（210x297mm）、正文 12pt；知网版常见 197-206 x 288-294mm、
正文 10.2/10.5pt。前者可当排版范本，后者只能看结构。

子命令
------
    python pdf_probe.py layout   FILE [--pages 11-20]
    python pdf_probe.py outline  FILE
    python pdf_probe.py sections FILE
    python pdf_probe.py dump     FILE [--pages 1-3]
    python pdf_probe.py version  FILE          # 学校版 / 知网版判定
所有子命令均支持 --json 输出结构化结果。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter

try:
    import pymupdf
except ImportError:  # pragma: no cover
    try:
        import fitz as pymupdf  # type: ignore
    except ImportError:
        sys.exit("需要 PyMuPDF：pip install pymupdf")

MM = 25.4 / 72
FW = str.maketrans("０１２３４５６７８９．：（）　，；", "0123456789.:() ,;")
CJK = r"[\u4e00-\u9fffa-zA-Z（）()、·\-—－“”\"'/]"


# ---------- 工具 ----------
def parse_pages(spec: str, total: int):
    """'1-3' / '5' / '11-' → 0-based 索引列表。"""
    if not spec:
        return list(range(total))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a else 1
            b = int(b) if b else total
        else:
            a = b = int(part)
        out.extend(i - 1 for i in range(a, min(b, total) + 1))
    return sorted({i for i in out if 0 <= i < total})


def norm(s: str) -> str:
    s = s.translate(FW)
    s = re.sub(r"[\u3000\s]+", "", s)
    s = s.replace("…", "").replace("...", "")
    return re.sub(r"\.{2,}", "", s)


def clean_leader(s: str) -> str:
    s = s.replace("\u3000", " ")
    s = re.sub(r"[.·…]{3,}\s*\d{1,3}\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------- layout ----------
def layout(path: str = "", pages_spec: str = "", exclude_footer: bool = True, doc=None):
    own = doc is None
    if own:
        doc = pymupdf.open(path)
    total = doc.page_count
    idx = parse_pages(pages_spec, total)
    size_cnt, font_cnt = Counter(), Counter()
    size_chars, gaps = Counter(), Counter()
    tops, bots, lefts, rights = [], [], [], []

    for pi in idx:
        pg = doc[pi]
        W, H = pg.rect.width, pg.rect.height
        size_cnt[f"{W*MM:.0f}x{H*MM:.0f}"] += 1
        dd = pg.get_text("dict")
        rows = []
        for b in dd["blocks"]:
            if b.get("type") != 0:
                continue
            for ln in b.get("lines", []):
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                if not txt:
                    continue
                sz = max(round(s["size"], 1) for s in ln["spans"])
                fn = Counter(s["font"] for s in ln["spans"]).most_common(1)[0][0]
                rows.append((ln["bbox"][1], ln["bbox"][3], ln["bbox"][0], ln["bbox"][2], sz, fn, txt))
                size_chars[sz] += len(txt)
                font_cnt[fn] += len(txt)
        if not rows:
            continue
        body = rows
        if exclude_footer:
            body = [r for r in rows
                    if not (r[0] * MM > H * MM * 0.85 and len(r[6]) <= 4 and r[6].strip().isdigit())]
            body = body or rows
        tops.append(min(r[0] for r in body) * MM)
        bots.append(H * MM - max(r[1] for r in body) * MM)
        lefts.append(min(r[2] for r in body) * MM)
        rights.append(W * MM - max(r[3] for r in body) * MM)
        rows.sort()
        for i in range(1, len(rows)):
            dy = rows[i][0] - rows[i - 1][0]
            if 8 < dy < 32 and rows[i][4] == rows[i - 1][4] and len(rows[i][6]) > 15:
                gaps[round(dy, 1)] += 1

    if own:
        doc.close()

    def stat(v):
        if not v:
            return None
        c = Counter(round(x, 1) for x in v).most_common()
        return {"mode": c[0][0], "min": round(min(v), 1), "max": round(max(v), 1),
                "top3": c[:3], "n_pages": len(v)}

    return {
        "file": path,
        "pages": total,
        "page_sizes": size_cnt.most_common(),
        "margins_mm": {"top": stat(tops), "bottom": stat(bots),
                       "left": stat(lefts), "right": stat(rights)},
        "font_sizes_pt": size_chars.most_common(8),
        "fonts": font_cnt.most_common(6),
        "line_gap_pt": gaps.most_common(6),
    }


def print_layout(r: dict):
    print(f"文件：{r['file']}")
    print(f"页数：{r['pages']}")
    print("页面尺寸：" + "；".join(f"{k}mm×{v}页" for k, v in r["page_sizes"]))
    print("\n页边距（正文区外沿实测）：")
    for k, v in r["margins_mm"].items():
        if v:
            print(f"  {k:<7} 众数 {v['mode']}mm  范围 {v['min']}–{v['max']}mm（{v['n_pages']} 页样本）")
    print("\n字号分布（pt / 字符数）：")
    for fs, n in r["font_sizes_pt"]:
        print(f"  {fs:<6} {n}")
    print("\n行间距（pt / 出现次数）：")
    for g, n in r["line_gap_pt"]:
        print(f"  {g:<6} {n}")
    print("\n字体（字符数）：")
    for f, n in r["fonts"]:
        print(f"  {f:<34} {n}")


# ---------- version ----------
def judge_version(r: dict):
    sizes = r["page_sizes"]
    main = sizes[0][0] if sizes else ""
    m = re.match(r"(\d+)x(\d+)", main)
    w, h = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    body = r["font_sizes_pt"][0][0] if r["font_sizes_pt"] else 0
    if abs(w - 210) <= 2 and abs(h - 297) <= 2:
        verdict, why = "school_submission", "页面为标准 A4"
    elif 190 <= w <= 208 and 282 <= h <= 296:
        verdict, why = "cnki_cropped", "页面被裁边（约 197-206 × 288-294mm），非标准 A4"
    else:
        verdict, why = "unknown", f"页面 {main}mm 不匹配常见规格"
    return {"verdict": verdict, "reason": why, "page": main, "body_size_pt": body,
            "template_usable": verdict == "school_submission"}


# ---------- outline ----------
def parse_outline(raw: str):
    """从目录原文解析章/节骨疗。目录常被拆行，故先归一化再匹配。"""
    t = norm(raw)
    chaps, secs, tails = [], [], []
    for m in re.finditer(r"第(\d{1,2})章(" + CJK + r"{2,45})", t):
        title = re.sub(r"\d+$", "", m.group(2))
        chaps.append((int(m.group(1)), title))
    seen, ded = set(), []
    for n, ti in chaps:
        if n in seen:
            continue
        seen.add(n)
        ded.append((n, ti))
    for m in re.finditer(r"(\d{1,2})\.(\d{1,2})(" + CJK + r"{2,40})", t):
        secs.append(f"{m.group(1)}.{m.group(2)} {re.sub(r'[0-9]+$', '', m.group(3))}")
    for kw in ["结论", "结语", "余论", "总结", "参考文献", "致谢", "附录", "个人简历"]:
        if kw in t:
            tails.append(kw)
    return ded, secs, tails


def parse_outline_from_lines(text: str):
    """正文兜底解析：只看独立成行的「第N章 ××」，避免正文里的交叉引用污染。"""
    chaps, seen = [], set()
    for line in text.splitlines():
        s = line.strip()
        if not s or len(s) > 40:
            continue
        m = re.match(r"^第\s*([0-9０-９一二三四五六七八九十]{1,3})\s*章\s*(.+)$", s)
        if not m:
            continue
        num = m.group(1).translate(FW)
        if not num.isdigit():
            cn = "一二三四五六七八九十"
            num = str(cn.index(num) + 1) if num in cn else ""
        if not num:
            continue
        n = int(num)
        if n in seen:
            continue
        seen.add(n)
        chaps.append((n, m.group(2).strip()[:40]))
    chaps.sort(key=lambda x: x[0])
    return chaps


def outline(path: str = "", doc=None):
    own = doc is None
    if own:
        doc = pymupdf.open(path)
    texts = [p.get_text("text") for p in doc]
    toc_idx = []
    for i, t in enumerate(texts[:28]):
        nt = norm(t)
        if "目录" in nt[:30] and (t.count("…") >= 3 or len(re.findall(r"\.{4,}", t)) >= 3
                                  or len(re.findall(r"第\d章", nt)) >= 2):
            toc_idx.append(i)
    raw = ""
    if toc_idx:
        start = toc_idx[0]
        block = [texts[start]]
        j = start + 1
        while j < len(texts) and j < start + 5:
            nt = norm(texts[j])
            if re.search(r"第\d+章", nt) or re.match(r"^(结论|参考文献|致谢|附录)", nt):
                block.append(texts[j])
                j += 1
            else:
                break
        raw = "\n".join(block)
    chaps, secs, tails = parse_outline(raw)
    from_body = False
    if not chaps:
        chaps = parse_outline_from_lines("\n".join(texts))
        _, secs, tails = parse_outline("\n".join(texts))
        from_body = True
    if own:
        doc.close()
    return {"file": path, "toc_found": bool(toc_idx), "toc_pages": [i + 1 for i in toc_idx],
            "from_body": from_body, "chapters": chaps, "sections": secs, "tails": tails,
            "raw_toc": raw}


def print_outline(r: dict):
    print(f"文件：{r['file']}")
    print(f"目录页：{r['toc_pages'] or '未找到'}" + ("（章标题取自正文）" if r["from_body"] else ""))
    print(f"章数：{len(r['chapters'])}  节数：{len(r['sections'])}")
    for n, t in r["chapters"]:
        print(f"  第{n}章 {t}")
    if r["tails"]:
        print("  尾部：" + " / ".join(r["tails"]))


# ---------- sections ----------
MARKS = {
    "原创性声明": [r"原创性声明", r"独创性声明"],
    "版权授权书": [r"版权使用授权书"],
    "中文摘要": [r"摘\s*要"],
    "英文摘要": [r"(?i:abstract)"],
    "目录": [r"目\s*录"],
    "正文": [r"第\s*[1１]\s*章", r"第一章"],
    "参考文献": [r"参考文献"],
    "附录": [r"附\s*录"],
    "致谢": [r"致\s*谢"],
    "个人简历": [r"个人简历", r"在学期间.{0,8}科研成果"],
}


def sections(path: str = "", doc=None):
    own = doc is None
    if own:
        doc = pymupdf.open(path)
    full = "\n".join(p.get_text("text") for p in doc)
    if own:
        doc.close()
    out = {}
    for name, pats in MARKS.items():
        out[name] = any(re.search(p, full) for p in pats)
    return {"file": path, "sections": out, "coverage": f"{sum(out.values())}/{len(out)}"}


def print_sections(r: dict):
    print(f"文件：{r['file']}")
    print(f"识别到的部分：{r['coverage']}")
    for k, v in r["sections"].items():
        print(f"  {'✅' if v else '❌'} {k}")


# ---------- dump ----------
def dump(path: str, pages_spec: str):
    doc = pymupdf.open(path)
    idx = parse_pages(pages_spec, doc.page_count)
    print(f"# {path}  pages={doc.page_count}")
    for i in idx:
        print(f"\n===== PAGE {i+1} =====")
        print(doc[i].get_text("text").rstrip())
    doc.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="PDF 排版参数探针")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("layout", help="量页面/页边距/字号/行距/字体")
    p1.add_argument("file")
    p1.add_argument("--pages", default="", help="如 11-20，默认全部")
    p1.add_argument("--keep-footer", action="store_true", help="不排除页脚页码行")

    p2 = sub.add_parser("outline", help="提取目录与章/节骨架")
    p2.add_argument("file")

    p3 = sub.add_parser("sections", help="检查 12 个组成部分是否齐全")
    p3.add_argument("file")

    p4 = sub.add_parser("dump", help="导出文本")
    p4.add_argument("file")
    p4.add_argument("--pages", default="")

    p5 = sub.add_parser("version", help="判定学校提交版还是知网裁边版")
    p5.add_argument("file")
    p5.add_argument("--pages", default="")

    args = ap.parse_args(argv)

    if args.cmd == "layout":
        r = layout(args.file, args.pages, exclude_footer=not args.keep_footer)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            print_layout(r)
    elif args.cmd == "version":
        r = judge_version(layout(args.file, args.pages))
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            print(f"判定：{r['verdict']}")
            print(f"理由：{r['reason']}")
            print(f"页面：{r['page']}mm　正文主字号：{r['body_size_pt']}pt")
            print("可否作为排版范本：" + ("可以" if r["template_usable"] else "不可以（仅结构/引用可参考）"))
    elif args.cmd == "outline":
        r = outline(args.file)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            print_outline(r)
    elif args.cmd == "sections":
        r = sections(args.file)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            print_sections(r)
    elif args.cmd == "dump":
        dump(args.file, args.pages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
