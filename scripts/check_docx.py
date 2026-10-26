#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 profile 体检 .docx 学位论文，输出「通过 / 警告 / 不通过」清单。

只做**可机械判定**的检查；标题好不好、论证是否成立这类事不在此列。

检查项
------
页面      纸张、页边距、页眉是否为空、页脚是否有页码域
字体字号  正文抽样段落的东亚字体、字号、行距、首行缩进
标题      层级编号连续性、是否出现四级编号、标题内标点、标题过短、结论章号
摘要      中文字数、关键词分隔符与个数
参考文献  序号括号类型、是否误带页码、分类标题、类内排序、条目数
脚注      编号符号、是否出现「前引」、是否缺页码
字数      中文正文字数

用法
----
    python check_docx.py 论文.docx
    python check_docx.py 论文.docx --profile uibe-law-2020 --json
    python check_docx.py 论文.docx --out 体检报告.md

退出码：0 全部通过或有警告；1 存在「不通过」项。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile

try:
    from docx import Document
    from docx.enum.text import WD_LINE_SPACING
    from docx.shared import Length
except ImportError:
    sys.exit("需要 python-docx：pip install python-docx")

PROFILE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "profiles")
CM = 360000  # EMU per cm


# ---------- 底层取值 ----------
def east_asian_font(par) -> str:
    """取段落首个 run 的中文字体名（w:eastAsia）。"""
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for r in par.runs:
        if r._element.rPr is not None and r._element.rPr.rFonts is not None:
            ea = r._element.rPr.rFonts.get(ns + "eastAsia")
            if ea:
                return ea
    try:
        st = par.style
        if st is not None and st.element.rPr is not None and st.element.rPr.rFonts is not None:
            return st.element.rPr.rFonts.get(ns + "eastAsia") or ""
    except Exception:
        pass
    return ""


def run_size_pt(par):
    for r in par.runs:
        if r.font.size:
            return r.font.size.pt
    try:
        if par.style and par.style.font.size:
            return par.style.font.size.pt
    except Exception:
        pass
    return None


def line_spacing(par):
    pf = par.paragraph_format
    ls = pf.line_spacing
    if ls is None:
        return None, None
    if isinstance(ls, Length) or hasattr(ls, "pt"):
        return "exact", round(ls.pt, 1)
    return "multiple", round(float(ls), 2)


def first_line_indent_chars(par, size_pt):
    ind = par.paragraph_format.first_line_indent
    if ind is None or not size_pt:
        return None
    return round(ind.pt / size_pt, 2)


def cjk_len(s: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", s or ""))


# ---------- 脚注 ----------
def read_footnotes(path):
    """从 docx 包内读 footnotes.xml，返回脚注正文列表（不含分隔符）。"""
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            if "word/footnotes.xml" not in z.namelist():
                return out
            xml = z.read("word/footnotes.xml").decode("utf-8", "ignore")
    except Exception:
        return out
    for m in re.finditer(r'<w:footnote[^>]*w:id="(\d+)"[^>]*>(.*?)</w:footnote>', xml, re.S):
        fid = int(m.group(1))
        if fid < 1:      # 0 = separator, 1 = continuation separator
            continue
        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", m.group(2), re.S)
        txt = "".join(texts).strip()
        if txt:
            out.append(txt)
    return out


# ---------- 检查 ----------
class Report:
    def __init__(self):
        self.rows = []

    def add(self, group, item, status, detail, fix=""):
        self.rows.append({"group": group, "item": item, "status": status,
                          "detail": detail, "fix": fix})

    def count(self, status):
        return sum(1 for r in self.rows if r["status"] == status)


def check(doc_path: str, prof: dict):
    doc = Document(doc_path)
    R = Report()
    P = prof

    # --- 页面 ---
    for i, sec in enumerate(doc.sections, 1):
        w = sec.page_width.cm if sec.page_width else 0
        h = sec.page_height.cm if sec.page_height else 0
        ok_size = abs(w - 21.0) < 0.3 and abs(h - 29.7) < 0.3
        R.add("页面", f"第{i}节 纸张", "通过" if ok_size else "不通过",
              f"{w:.1f}×{h:.1f} cm", "应为 A4 21.0×29.7 cm")
        want = P["page"]["margins_cm"]
        tol = P["page"].get("tolerance_cm", 0.25)
        got = {"top": sec.top_margin.cm, "bottom": sec.bottom_margin.cm,
               "left": sec.left_margin.cm, "right": sec.right_margin.cm}
        bad = [k for k in got if abs(got[k] - want[k]) > tol]
        R.add("页面", f"第{i}节 页边距",
              "通过" if not bad else "不通过",
              "上{:.2f} 下{:.2f} 左{:.2f} 右{:.2f}".format(
                  got["top"], got["bottom"], got["left"], got["right"]),
              f"应为 上{want['top']} 下{want['bottom']} 左{want['left']} 右{want['right']} cm")
        if sec.header and any(p.text.strip() for p in sec.header.paragraphs):
            R.add("页面", f"第{i}节 页眉", "警告", "页眉有内容", "本 profile 要求不加页眉")

    # --- 页码 ---
    try:
        with zipfile.ZipFile(doc_path) as z:
            tails = [n for n in z.namelist() if re.match(r"word/footer\d*\.xml", n)]
            has_page = False
            for t in tails:
                if b"PAGE" in z.read(t):
                    has_page = True
                    break
        R.add("页面", "页脚页码域", "通过" if has_page else "不通过",
              "已找到 PAGE 域" if has_page else "未找到页码域", "插入→页码→页面底端→居中")
    except Exception as e:
        R.add("页面", "页脚页码域", "警告", str(e))

    # --- 正文抽样 ---
    body_pars = [p for p in doc.paragraphs
                 if len(p.text.strip()) >= 40 and not p.style.name.lower().startswith(("heading", "标题"))]
    if body_pars:
        sample = body_pars[: min(60, len(body_pars))]
        fonts, sizes, lss, inds = {}, {}, {}, {}
        for p in sample:
            f = east_asian_font(p)
            if f:
                fonts[f] = fonts.get(f, 0) + 1
            s = run_size_pt(p)
            if s:
                sizes[s] = sizes.get(s, 0) + 1
            rule, val = line_spacing(p)
            if rule:
                lss[(rule, val)] = lss.get((rule, val), 0) + 1
            ic = first_line_indent_chars(p, s)
            if ic is not None:
                inds[round(ic)] = inds.get(round(ic), 0) + 1

        want_body = P["styles"]["body"]
        top_font = max(fonts, key=fonts.get) if fonts else ""
        top_size = max(sizes, key=sizes.get) if sizes else None
        top_ls = max(lss, key=lss.get) if lss else None
        top_ind = max(inds, key=inds.get) if inds else None

        R.add("字体字号", "正文中文字体", "通过" if "宋" in top_font else "警告",
              f"最常见：{top_font or '未识别'}", f"应为 {want_body['font_cn']}")
        R.add("字体字号", "正文字号", "通过" if top_size and abs(top_size - want_body["size_pt"]) < 0.6 else "不通过",
              f"最常见：{top_size}pt", f"应为 {want_body['size_pt']}pt（小四）")
        if top_ls:
            ok = (top_ls[0] == "exact" and abs(top_ls[1] - 20) <= 1)
            R.add("字体字号", "正文行距", "通过" if ok else "警告",
                  f"最常见：{top_ls[0]} {top_ls[1]}",
                  f"应为固定值 20 磅（学院示例实测；学校规范文本为 22 磅，以学院为准）")
        R.add("字体字号", "首行缩进", "通过" if top_ind == 2 else "警告",
              f"最常见：{top_ind} 字符", "应为 2 字符")

    # --- 标题 ---
    heads = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if not t or len(t) > 60:
            continue
        if re.match(r"^第\s*\d+\s*章", t):
            heads.append(("章", t))
        elif re.match(r"^\d+\.\d+\.\d+\.\d+", t):
            heads.append(("四级", t))
        elif re.match(r"^\d+\.\d+\.\d+", t):
            heads.append(("三级", t))
        elif re.match(r"^\d+\.\d+", t):
            heads.append(("二级", t))
    if heads:
        lv4 = [t for k, t in heads if k == "四级"]
        R.add("标题", "四级编号", "不通过" if lv4 else "通过",
              f"发现 {len(lv4)} 处" + (f"，如「{lv4[0][:24]}」" if lv4 else ""),
              "学院明令禁止；三级以下改用（一）/1./（1）")
        punct = [t for k, t in heads if re.search(r"[。，、；：]$", t)]
        R.add("标题", "标题末尾标点", "警告" if punct else "通过",
              f"{len(punct)} 处" + (f"，如「{punct[0][:24]}」" if punct else ""), "各级标题不加标点")
        short = [t for k, t in heads if k != "章" and cjk_len(t) < 6]
        R.add("标题", "标题过短", "警告" if short else "通过",
              f"{len(short)} 处" + (f"，如「{short[0][:24]}」" if short else ""),
              "不能只写名词，应「限定语+对象+判断」")
        concl = [t for k, t in heads if re.search(r"结论|结语|总结", t)]
        if concl:
            ok = bool(re.match(r"^第\s*\d+\s*章", concl[-1]))
            R.add("标题", "结论章号", "通过" if ok else "不通过", concl[-1][:30],
                  "应为「第N章 结论」（学院口径：加章号）")
        nums = [int(re.match(r"^第\s*(\d+)\s*章", t).group(1)) for k, t in heads if k == "章"]
        if nums:
            gaps = [n for i, n in enumerate(sorted(nums), 1) if n != i]
            R.add("标题", "章号连续", "通过" if not gaps else "警告",
                  f"章号：{sorted(nums)}", "章号应从 1 连续")
        R.add("标题", "章数", "通过", f"{len(nums)} 章", "5–6 章为样本主流")

    # --- 摘要与关键词 ---
    full = "\n".join(p.text for p in doc.paragraphs)
    m = re.search(r"摘\s*要(.{100,8000}?)(关键词|关键字)", full, re.S)
    if m:
        n = cjk_len(m.group(1))
        lo, hi = P["content"]["abstract_chars_master"]
        R.add("摘要", "中文摘要字数", "通过" if lo <= n <= hi else "警告",
              f"{n} 字", f"硕士应为 {lo}–{hi} 字（学院示例另要求写满一页为宜）")
    mk = re.search(r"关键词[:：]?\s*([^\n]{4,150})", full)
    if mk:
        kw = mk.group(1)
        sep = "；" if "；" in kw else ("，" if "，" in kw else (" " if " " in kw else "无"))
        n_kw = len([x for x in re.split(r"[；;，,、\s]+", kw.strip("。. ")) if x])
        want_sep = P["content"]["keyword_separator_cn"]
        R.add("摘要", "关键词分隔符", "通过" if sep == want_sep else "警告",
              f"当前用「{sep}」", f"本 profile 采用「{want_sep}」（学院示例与样本一致）")
        lo, hi = P["content"]["keyword_count"]
        R.add("摘要", "关键词个数", "通过" if lo <= n_kw <= hi else "警告",
              f"{n_kw} 个", f"应为 {lo}–{hi} 个")

    # --- 参考文献 ---
    ref_idx = None
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip().replace(" ", "") in ("参考文献", "參考文獻"):
            ref_idx = i
            break
    if ref_idx is not None:
        seg = [p.text.strip() for p in doc.paragraphs[ref_idx + 1:] if p.text.strip()]
        br = [s for s in seg if re.match(r"^[\[【]\s*\d{1,3}\s*[\]】]", s)]
        want_br = P["reference_list"]["number_bracket"]
        types = set()
        for s in br:
            if s.startswith("【"):
                types.add("【】")
            elif s.startswith("["):
                types.add("[]")
        R.add("参考文献", "序号括号",
              "不通过" if (types and types != {want_br}) else ("警告" if not types else "通过"),
              f"检出：{'、'.join(sorted(types)) or '无'}",
              f"本 profile 用 {want_br}（体例文件明文「排序用【1】连续排列」；格式示例用的是 []，两者冲突时以体例文件为准）。全文不得混用")
        withpage = [s for s in br if re.search(r"第\s*\d+(-\d+)?\s*页", s)]
        R.add("参考文献", "误带页码", "不通过" if withpage else "通过",
              f"{len(withpage)} 条" + (f"，如「{withpage[0][:30]}」" if withpage else ""),
              "参考文献一律不得出现页码")
        groups = [s for s in seg if re.match(r"^[一二三四五六七八九十]、", s)]
        R.add("参考文献", "分类标题", "通过" if len(groups) >= 2 else "警告",
              f"{len(groups)} 类：{'／'.join(g[:8] for g in groups) or '无'}",
              "应为 中文著作／中文论文／中文学位论文／英文著作／英文论文")
        # 类内排序方向
        years = []
        for s in br:
            y = re.search(r"(19|20)\d{2}", s)
            if y:
                years.append(int(y.group(0)))
        if len(years) >= 4:
            desc = sum(1 for a, b in zip(years, years[1:]) if b <= a)
            asc = sum(1 for a, b in zip(years, years[1:]) if b >= a)
            direction = "降序" if desc > asc else "升序"
            want = "降序" if P["reference_list"]["sort_within_group"] == "year_desc" else "升序"
            R.add("参考文献", "类内时间排序", "通过" if direction == want else "警告",
                  f"疑似{direction}", f"本 profile 要求{want}")
        lo = P["reference_list"]["min_total"]
        R.add("参考文献", "条目数", "通过" if len(br) >= lo else "不通过",
              f"{len(br)} 条", f"硕士应 ≥ {lo} 条，外文 ≥ {P['reference_list']['min_foreign']} 条")
    else:
        R.add("参考文献", "章节是否存在", "不通过", "未找到「参考文献」标题", "必须有独立的参考文献部分")

    # --- 脚注 ---
    fns = read_footnotes(doc_path)
    if fns:
        circled = [f for f in fns if re.search(r"[①②③④⑤⑥⑦⑧⑨⑩]", f[:3])]
        R.add("脚注", "编号符号", "通过" if not circled else "不通过",
              f"共 {len(fns)} 条脚注；含圈码 {len(circled)} 条",
              "学院要求全文连续阿拉伯数字 1、2、3")
        qianyin = [f for f in fns if "前引" in f]
        R.add("脚注", "「前引」用法", "通过" if not qianyin else "不通过",
              f"{len(qianyin)} 处", "学院要求重复引用直接重写全称，不用「前引」")
        nopage = [f for f in fns if not re.search(r"第\s*\d+\s*页|p{1,2}\.\s*\d+|\d+\s*页", f)
                  and not f.startswith(("该", "包括", "即", "如"))]
        ratio = len(nopage) / len(fns)
        R.add("脚注", "缺页码", "警告" if ratio > 0.2 else "通过",
              f"{len(nopage)}/{len(fns)} 条未见页码",
              "著作/论文/译著/学位论文脚注必须有页码（纯解释性脚注除外）")
    else:
        R.add("脚注", "脚注是否存在", "警告", "未检出脚注",
              "法学院体例以脚注引注，若无脚注请确认是否漏引")

    # --- 字数 ---
    n_chars = cjk_len(full)
    lo = P["content"]["body_chars_master_min"]
    R.add("字数", "中文总字数", "通过" if n_chars >= lo else "不通过",
          f"{n_chars} 字", f"硕士正文应 ≥ {lo} 字")

    return R


def render(R: Report, prof_name: str, src: str):
    L = [f"# 学位论文格式体检报告", "",
         f"- 文件：`{src}`", f"- 采用 profile：{prof_name}", "",
         f"**结果：通过 {R.count('通过')} 项 ｜ 警告 {R.count('警告')} 项 ｜ 不通过 {R.count('不通过')} 项**", ""]
    order = ["页面", "字体字号", "标题", "摘要", "参考文献", "脚注", "字数"]
    icon = {"通过": "✅", "警告": "⚠️", "不通过": "❌"}
    for g in order:
        rows = [r for r in R.rows if r["group"] == g]
        if not rows:
            continue
        L.append(f"## {g}")
        L.append("")
        L.append("| 检查项 | 结果 | 实测 | 要求 / 处理 |")
        L.append("|---|---|---|---|")
        for r in rows:
            L.append(f"| {r['item']} | {icon[r['status']]} {r['status']} | {r['detail']} | {r['fix']} |")
        L.append("")
    fails = [r for r in R.rows if r["status"] == "不通过"]
    if fails:
        L.append("## 必须先修的项")
        L.append("")
        for r in fails:
            L.append(f"- **{r['group']}·{r['item']}**：{r['detail']} → {r['fix']}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="按 profile 体检 docx 学位论文")
    ap.add_argument("docx")
    ap.add_argument("--profile", default="uibe-law-2020")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", help="输出 Markdown 报告路径")
    args = ap.parse_args(argv)

    ppath = args.profile if os.path.exists(args.profile) else os.path.join(PROFILE_DIR, args.profile + ".json")
    if not os.path.exists(ppath):
        sys.exit(f"找不到 profile：{ppath}")
    prof = json.load(open(ppath, encoding="utf-8"))

    if not os.path.exists(args.docx):
        sys.exit(f"找不到文件：{args.docx}")

    R = check(args.docx, prof)
    if args.json:
        print(json.dumps({"profile": prof["id"], "rows": R.rows}, ensure_ascii=False, indent=1))
    else:
        text = render(R, prof["name"], args.docx)
        if args.out:
            open(args.out, "w", encoding="utf-8").write(text)
            print(f"已写入 {args.out}", file=sys.stderr)
            print(f"通过 {R.count('通过')}｜警告 {R.count('警告')}｜不通过 {R.count('不通过')}", file=sys.stderr)
        else:
            print(text)
    return 1 if R.count("不通过") else 0


if __name__ == "__main__":
    sys.exit(main())
