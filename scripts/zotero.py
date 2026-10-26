#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zotero 本地 API 只读客户端（Zotero 7+）。

前置条件
--------
1. Zotero 客户端正在运行；
2. 已勾选 编辑 → 设置 → 高级 → 「允许此计算机上的其他应用程序与 Zotero 通信」。

本地 API 是**只读**的：可以读条目、集合、标签、附件路径，但不能写入。

作为模块使用
------------
    from zotero import Zotero
    z = Zotero()
    for it in z.collection_items("ABC12345"):
        print(it["data"]["title"])

命令行
------
    python zotero.py stats
    python zotero.py collections
    python zotero.py items [--collection KEY] [--limit N]
    python zotero.py search "个人信息" [-n 20]
    python zotero.py children ITEM_KEY
    python zotero.py paths ITEM_KEY
    python zotero.py tags
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:23119/api"
API_VERSION = "3"


class ZoteroError(RuntimeError):
    pass


class Zotero:
    def __init__(self, base: str = DEFAULT_BASE, library: str = "users/0", timeout: int = 25):
        self.base = base.rstrip("/")
        self.library = library
        self.timeout = timeout

    # ---------- 底层 ----------
    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self.base}/{self.library}/{path.lstrip('/')}"

    def get(self, path: str):
        url = self._url(path)
        req = urllib.request.Request(url, headers={"Zotero-API-Version": API_VERSION})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = r.read()
                return json.loads(body.decode("utf-8")) if body else None
        except urllib.error.HTTPError as e:
            raise ZoteroError(f"HTTP {e.code} for {url} — 检查 Zotero 是否运行且已开启本地 API") from e
        except urllib.error.URLError as e:
            raise ZoteroError(f"无法连接 {url} — {e.reason}") from e

    def ping(self) -> bool:
        try:
            self.get("items?limit=1")
            return True
        except ZoteroError:
            return False

    def paginate(self, path: str, page: int = 100, cap: int = 5000):
        out, start = [], 0
        sep = "&" if "?" in path else "?"
        while start < cap:
            batch = self.get(f"{path}{sep}limit={page}&start={start}")
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page:
                break
            start += page
        return out

    # ---------- 资源 ----------
    def collections(self):
        return self.get("collections") or []

    def collection_items(self, key: str, top: bool = True):
        path = f"collections/{key}/items" + ("/top" if top else "")
        return self.paginate(path)

    def items(self, top: bool = True):
        return self.paginate("items/top" if top else "items")

    def item(self, key: str):
        return self.get(f"items/{key}")

    def children(self, key: str):
        return self.get(f"items/{key}/children") or []

    def search(self, q: str, limit: int = 25, top: bool = True):
        path = "items" + ("/top" if top else "") + "?q=" + urllib.parse.quote(q) + "&qmode=everything"
        return self.get(f"{path}&limit={limit}") or []

    def tags(self):
        return self.paginate("tags")

    def libraries(self):
        return self.get("libraries") or []

    # ---------- 附件 ----------
    @staticmethod
    def attachment_path(att: dict) -> str:
        """从附件条目解析出本地绝对路径（不存在则返回空串）。"""
        href = ((att.get("links") or {}).get("enclosure") or {}).get("href", "")
        if not href.startswith("file://"):
            return ""
        path = urllib.request.url2pathname(href[7:])
        # Windows 下形如 /C:/Users/... 需去掉前导斜杠
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        return path

    def attachments(self, key: str, content_type: str | None = None):
        """返回 [(路径, 是否存在, 附件元数据)]。"""
        out = []
        for c in self.children(key):
            d = c["data"]
            if d.get("itemType") != "attachment":
                continue
            if content_type and d.get("contentType") != content_type:
                continue
            p = self.attachment_path(c)
            out.append((p, bool(p) and os.path.exists(p), d))
        return out

    def pdfs(self, key: str):
        return [p for p, ok, _ in self.attachments(key, "application/pdf") if ok]


# ---------- 展示辅助 ----------
def year_of(d: dict) -> str:
    return (d.get("date") or "")[:4]


def authors_of(d: dict, n: int = 99) -> list[str]:
    out = []
    for c in (d.get("creators") or [])[:n]:
        name = c.get("lastName") or c.get("name") or ""
        first = c.get("firstName") or ""
        if first and c.get("creatorType") in (None, "author", "editor"):
            # 中文条目 firstName 常为空；西文条目拼接
            name = f"{name} {first}".strip() if re.search(r"[A-Za-z]", first) else (name + first)
        out.append(name)
    return [x for x in out if x]


def brief(i: dict) -> str:
    d = i["data"]
    au = "、".join(authors_of(d, 3))
    more = " 等" if len(d.get("creators") or []) > 3 else ""
    venue = d.get("publicationTitle") or d.get("university") or d.get("publisher") or ""
    return (f"[{d['itemType']:<15}] {(d.get('title') or '(无题名)')[:66]} | "
            f"{au}{more} | {year_of(d)} | {venue[:24]} | {d['key']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Zotero 本地 API 只读客户端")
    ap.add_argument("--base", default=DEFAULT_BASE, help="本地 API 根地址")
    ap.add_argument("--library", default="users/0", help="库路径，默认 users/0")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats", help="库概况")
    sub.add_parser("collections", help="列出全部集合")
    p_items = sub.add_parser("items", help="列出条目")
    p_items.add_argument("--collection", help="只列某集合内条目")
    p_items.add_argument("--limit", type=int, default=50)
    p_search = sub.add_parser("search", help="全文检索")
    p_search.add_argument("q")
    p_search.add_argument("-n", "--limit", type=int, default=25)
    p_child = sub.add_parser("children", help="列出某条目的子附件")
    p_child.add_argument("key")
    p_paths = sub.add_parser("paths", help="输出某条目的 PDF 绝对路径")
    p_paths.add_argument("key")
    sub.add_parser("tags", help="列出标签")

    args = ap.parse_args(argv)
    z = Zotero(args.base, args.library)

    if not z.ping():
        print("❌ 连不上 Zotero 本地 API。请确认：\n"
              "   1) Zotero 客户端已启动\n"
              "   2) 编辑→设置→高级→勾选「允许此计算机上的其他应用程序与 Zotero 通信」",
              file=sys.stderr)
        return 2

    if args.cmd == "stats":
        top = z.items(top=True)
        cols = z.collections()
        tags = z.tags()
        from collections import Counter
        print(f"顶层条目 {len(top)} ｜ 集合 {len(cols)} ｜ 标签 {len(tags)}")
        print("\n条目类型：")
        for k, v in Counter(i["data"]["itemType"] for i in top).most_common():
            print(f"  {k:<20} {v}")
        nopdf = [i for i in top if not z.pdfs(i["data"]["key"])]
        print(f"\n无本地 PDF 文件的顶层条目：{len(nopdf)}（含仅有网页链接的条目）")

    elif args.cmd == "collections":
        for c in z.collections():
            d = c["data"]
            print(f"{d['key']}  {(d.get('parentCollection') or '-'):<10} "
                  f"{(c.get('meta') or {}).get('numItems', 0):>4}  {d['name']}")

    elif args.cmd == "items":
        items = z.collection_items(args.collection) if args.collection else z.items()
        for i in items[: args.limit]:
            print(brief(i))

    elif args.cmd == "search":
        for i in z.search(args.q, args.limit):
            print(brief(i))

    elif args.cmd == "children":
        for path, ok, d in z.attachments(args.key):
            print(f"{d['itemType']:<12} {str(d.get('contentType')):<28} "
                  f"{'OK ' if ok else 'MISS'} {path or d.get('url', '')}")

    elif args.cmd == "paths":
        for p in z.pdfs(args.key):
            print(p)

    elif args.cmd == "tags":
        tags = z.tags()
        print(f"共 {len(tags)} 个标签")
        for t in tags[:200]:
            print(f"  {t['tag']:<40} {t.get('meta', {}).get('numItems', '')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
