#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按《法学引注手册》式体例（对外经贸大学法学院 2020）生成参考文献表与脚注。

为什么不用 CSL
--------------
法学院体例是「中文法学手册格式 + 英文 Bluebook」的混合体，字段要求也与 CSL 不同：
必须有页码（脚注）、不出现"卷"、网络资源不加网站名、参考文献一律不得有页码。
任何现成 CSL 都无法直接对上，所以这里用模板拼装，输出可粘贴文本，再由人工微调。

用法
----
    # 从一个 Zotero 集合生成参考文献表
    python gen_references.py --collection GC7ZATAJ --out refs.md

    # 只取指定条目
    python gen_references.py --keys ABC12345 DEF67890

    # 生成单条脚注（带页码）
    python gen_references.py --footnote ABC12345 --page 20
    python gen_references.py --footnote ABC12345 --page 20 --prefix 参见

    # 离线模式：读取事先导出的 Zotero items JSON
    python gen_references.py --from-json items.json --out refs.md

输出：Markdown 文本，五个分类按法学院体例排列，条目缺字段会以 ⚠ 标出。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GROUPS = ["一、中文著作", "二、中文论文", "三、中文学位论文", "四、英文著作", "五、英文论文"]


def has_cjk(s: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))


def year_of(d: dict) -> str:
    m = re.search(r"(\d{4})", d.get("date") or "")
    return m.group(1) if m else ""


def cjk_author(c: dict) -> str:
    last = (c.get("lastName") or "").strip()
    first = (c.get("firstName") or "").strip()
    name = (c.get("name") or "").strip()
    if name:
        return name
    if not first:
        return last
    # 中文条目常把全名放在 lastName，或 firstName 是名
    return last + first


def en_author(c: dict, upper: bool = False) -> str:
    last = (c.get("lastName") or c.get("name") or "").strip()
    first = (c.get("firstName") or "").strip()
    if not last and not first:
        return ""
    s = f"{last} {first}".strip() if first else last
    return s.upper() if upper else s


def authors(d: dict, en: bool = False, upper: bool = False, limit: int = 3) -> str:
    cs = [c for c in (d.get("creators") or []) if c.get("creatorType") in (None, "author", "editor", "translator", "contributor")]
    if not cs:
        return ""
    fmt = (lambda c: en_author(c, upper)) if en else cjk_author
    names = [fmt(c) for c in cs]
    names = [n for n in names if n]
    if len(names) > limit:
        return ("、".join(names[:limit]) if not en else ", ".join(names[:limit])) + ("等" if not en else " et al.")
    return "、".join(names) if not en else ", ".join(names)


def venue(d: dict) -> str:
    return (d.get("publicationTitle") or d.get("bookTitle") or "").strip()


def publisher(d: dict) -> str:
    return (d.get("publisher") or d.get("university") or "").strip()


def issue(d: dict) -> str:
    return (d.get("issue") or "").strip()


def thesis_type(d: dict) -> str:
    t = (d.get("thesisType") or "").strip()
    if "博士" in t:
        return "博士论文"
    if "硕士" in t:
        return "硕士论文"
    return "学位论文"


def is_en(d: dict) -> bool:
    return not has_cjk(d.get("title") or "")


def classify(d: dict):
    """→ (组名, 是否需要人工补字段)"""
    t = d.get("itemType")
    en = is_en(d)
    if t in ("book", "bookSection"):
        return (GROUPS[3] if en else GROUPS[0]), False
    if t == "thesis":
        return (GROUPS[2] if not en else GROUPS[4]), False
    if t in ("journalArticle", "magazineArticle", "newspaperArticle", "conferencePaper"):
        return (GROUPS[4] if en else GROUPS[1]), False
    return "", True


def entry_ref(d: dict):
    """参考文献条目（无页码）；返回 (文本, 警告列表)"""
    grp, manual = classify(d)
    warn = []
    if not grp:
        return "", [f"不支持的文献类型 {d.get('itemType')}（参考文献只收著作/论文/学位论文）"]
    au = authors(d, en=is_en(d))
    yr = year_of(d)
    title = (d.get("title") or "").strip().rstrip(".")
    if not au:
        warn.append("缺作者")
    if not yr:
        warn.append("缺年份")

    if grp == GROUPS[0]:      # 中文著作
        pub = publisher(d)
        if not pub:
            warn.append("缺出版社")
        return f"{au}：《{title}》，{pub}{yr}年版。", warn
    if grp == GROUPS[1]:      # 中文论文
        v, i = venue(d), issue(d)
        if not v:
            warn.append("缺期刊名")
        if not i:
            warn.append("缺期号")
        return f"{au}：《{title}》，载《{v}》{yr}年第{i}期。", warn
    if grp == GROUPS[2]:      # 中文学位论文
        pub = publisher(d)
        if not pub:
            warn.append("缺学位授予单位")
        return f"{au}：《{title}》，{pub}{yr}年{thesis_type(d)}。", warn
    if grp == GROUPS[3]:      # 英文著作
        pub, upp = publisher(d), (d.get("title") or "").upper()
        a = authors(d, en=True, upper=True)
        if not pub:
            warn.append("缺出版社")
        return f"{a}, {upp} ({pub}, {yr}).", warn
    # 英文论文
    v = venue(d).upper()
    vol = (d.get("volume") or "").strip()
    pages = (d.get("pages") or "").strip()
    a = authors(d, en=True)
    if not v:
        warn.append("缺期刊名")
    if not vol:
        warn.append("缺卷号（Bluebook 要求 卷号 期刊名 起始页）")
    if not pages:
        warn.append("缺页码")
    mid = f"{vol} {v}" if vol else v
    return f"{a}, {title}, {mid} {pages} ({yr}).".replace("  ", " "), warn


def entry_footnote(d: dict, page: str = "", prefix: str = ""):
    """脚注条目（必须有页码）"""
    grp, _ = classify(d)
    au = authors(d, en=is_en(d))
    yr = year_of(d)
    title = (d.get("title") or "").strip().rstrip(".")
    pg = f"，第{page}页" if page else ""
    pre = prefix or ""
    if not page:
        pre = (pre + "⚠需补页码 ").strip()

    if grp == GROUPS[0]:
        s = f"{au}：《{title}》，{publisher(d)}{yr}年版{pg}。"
    elif grp == GROUPS[1]:
        s = f"{au}：《{title}》，载《{venue(d)}》{yr}年第{issue(d)}期{pg}。"
    elif grp == GROUPS[2]:
        s = f"{au}：《{title}》，{publisher(d)}{yr}年{thesis_type(d)}{pg}。"
    elif grp == GROUPS[3]:
        s = f"{authors(d, en=True, upper=True)}, {(d.get('title') or '').upper()} {page} ({publisher(d)}, {yr})."
    elif grp == GROUPS[4]:
        s = f"{authors(d, en=True)}, {title}, {(d.get('volume') or '')} {venue(d).upper()} {(d.get('pages') or '')} ({yr})."
    else:
        s = f"⚠ 不支持的文献类型 {d.get('itemType')}"
    return f"{pre}{s}"


def load_items(args):
    if args.from_json:
        data = json.load(open(args.from_json, encoding="utf-8"))
        return [x if "data" in x else {"data": x} for x in data]
    from zotero import Zotero
    z = Zotero()
    if not z.ping():
        sys.exit("连不上 Zotero。请确认客户端已启动且已开启本地 API。")
    if args.collection:
        return z.collection_items(args.collection)
    if args.keys:
        return [z.item(k) for k in args.keys]
    sys.exit("需要 --collection / --keys / --from-json 之一")


def build(items, group_titles=True):
    buckets = {g: [] for g in GROUPS}
    skipped, warnings = [], []
    for it in items:
        d = it["data"]
        if d.get("itemType") in ("attachment", "note"):
            continue
        text, warn = entry_ref(d)
        if not text:
            skipped.append(d.get("title", "")[:40])
            continue
        grp, _ = classify(d)
        buckets[grp].append({"year": year_of(d) or "0000", "text": text,
                             "title": d.get("title", ""), "warn": warn})
        if warn:
            warnings.append((d.get("title", "")[:40], "、".join(warn)))

    lines = ["参考文献", ""]
    n = 0
    for g in GROUPS:
        rows = buckets[g]
        if not rows:
            continue
        rows.sort(key=lambda r: r["year"], reverse=True)   # 类内时间降序
        if group_titles:
            lines.append(g)
        for r in rows:
            n += 1
            lines.append(f"【{n}】{r['text']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n", n, skipped, warnings


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成法学体例参考文献 / 脚注")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--collection", help="Zotero 集合 key")
    src.add_argument("--keys", nargs="+", help="若干 Zotero 条目 key")
    src.add_argument("--from-json", help="离线 items JSON")
    src.add_argument("--footnote", help="生成单条脚注，值为条目 key")
    ap.add_argument("--page", default="", help="脚注页码，如 20 或 20-22")
    ap.add_argument("--prefix", default="", help="脚注前缀，如 参见 / 转引自")
    ap.add_argument("--out", help="输出文件")
    ap.add_argument("--no-group-titles", action="store_true", help="不输出五大类标题")
    args = ap.parse_args(argv)

    if args.footnote:
        from zotero import Zotero
        z = Zotero()
        it = z.item(args.footnote)
        print(entry_footnote(it["data"], args.page, args.prefix))
        return 0

    items = load_items(args)
    text, n, skipped, warnings = build(items, not args.no_group_titles)

    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
        print(f"已写入 {args.out}（{n} 条）", file=sys.stderr)
    else:
        print(text)

    if skipped:
        print(f"\n跳过 {len(skipped)} 条（类型不在参考文献范围）：", file=sys.stderr)
        for s in skipped[:8]:
            print(f"  - {s}", file=sys.stderr)
    if warnings:
        print(f"\n⚠ {len(warnings)} 条需人工补字段：", file=sys.stderr)
        for t, w in warnings[:20]:
            print(f"  - {t}：{w}", file=sys.stderr)
        print("\n提示：先在 Zotero 里补齐字段再重跑，比在 Word 里手改更稳。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
