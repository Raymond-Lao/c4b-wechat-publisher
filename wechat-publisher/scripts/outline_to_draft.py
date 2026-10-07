#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
outline → draft：把一个提纲扩写成"可以往下写"的初稿。

挑战 C4B 的 Level 4 列出「写作辅助集成：技能不仅转换格式，还能帮你从大纲生成初稿」。
本脚本负责"想法 → 初稿"这一段，输出的 .md 可直接交给 convert_to_wechat.py 排版。

与 templates/ 的区别（这两个东西容易混）：
  templates/  是**空骨架**——章节标题是固定的，你往里填内容；
  本脚本      是**按你的大纲生成**——章节来自你的提纲，要点被摆到该在的位置上。

用法：
  python scripts/outline_to_draft.py 大纲.md 初稿.md --author 李瑞翔
  python scripts/outline_to_draft.py 大纲.md --sections      # 要点提升为小节标题
  python scripts/outline_to_draft.py 大纲.md --no-tips       # 不要写作提示
"""

import argparse
import re
import sys
from datetime import date as _date
from pathlib import Path

H1_RE = re.compile(r"^#\s+(.+)$")
H2_RE = re.compile(r"^##\s+(.+)$")
H3_RE = re.compile(r"^###\s+(.+)$")
BULLET_RE = re.compile(r"^[-*+]\s+(.+)$")
NUMBER_RE = re.compile(r"^\d+[.)]\s+(.+)$")
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

CLOSING_WORDS = ("结语", "总结", "最后", "收尾", "尾声")

# "一、xxx" / "第 2 章 xxx" / "3. xxx" 这类前缀，拼提示时要去掉，否则
# 提示会变成"本节要回答的问题：一、我遇到的问题"——把序号也念了一遍。
NUM_PREFIX_RE = re.compile(
    r"^\s*(?:第\s*[一二三四五六七八九十百\d]+\s*[章节部分讲]|[一二三四五六七八九十]+\s*[、.．)]|\d+\s*[、.．)])\s*")


def clean_title(t):
    """去掉标题里的序号前缀，用于拼写作提示。"""
    stripped = NUM_PREFIX_RE.sub("", t).strip()
    return stripped or t


# ---------------------------------------------------------------- 解析

def split_front_matter(text):
    """拆出可选的 key: value 头部，返回 (meta, 正文)。"""
    meta = {}
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return meta, text
    for line in m.group(1).splitlines():
        if ":" in line and not line.strip().startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta, text[m.end():]


def parse_outline(text):
    """
    逐行状态机解析大纲。

    这里刻意不用正则做"切块"——大纲里嵌套层级多、格式松，
    正则切块一旦切错是**静默出错**（少一段或多一段，没人会注意）。
    逐行读的代价是代码长一点，好处是每一行的归属都是显式判断的。
    """
    meta, body = split_front_matter(text)

    title = None
    sections = []          # [{"title": str, "points": [str], "notes": [str]}]
    loose = []             # 第一个 h2 之前出现的要点/文字
    cur = None

    for raw in body.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue

        m = H1_RE.match(s)
        if m:
            if title is None:
                title = m.group(1).strip()
            else:
                # 第二个 h1 当章节处理，避免标题被吞掉
                cur = {"title": m.group(1).strip(), "points": [], "notes": []}
                sections.append(cur)
            continue

        m = H2_RE.match(s)
        if m:
            cur = {"title": m.group(1).strip(), "points": [], "notes": []}
            sections.append(cur)
            continue

        m = H3_RE.match(s)
        if m:
            item = m.group(1).strip()
            (cur["points"] if cur else loose).append(item)
            continue

        m = BULLET_RE.match(s) or NUMBER_RE.match(s)
        if m:
            (cur["points"] if cur else loose).append(m.group(1).strip())
            continue

        # 普通文字行：当作说明，进 notes（会变成提示，不会当成正文）
        (cur["notes"] if cur else loose).append(s)

    return meta, title, sections, loose


# ---------------------------------------------------------------- 生成

def _hint(text):
    """写作提示统一用 HTML 注释：写的时候看得见，转换后不会渲染出来。"""
    return "<!-- {} -->".format(text)


def build_draft(meta, title, sections, loose, opts):
    lines = []
    title = title or opts.get("title") or "未命名文章"

    # ---- front matter（已有的值优先，不覆盖）
    fm = {
        "title": meta.get("title") or title,
        "author": meta.get("author") or opts.get("author") or "你的名字",
        "date": meta.get("date") or opts.get("date") or _date.today().isoformat(),
        "theme": meta.get("theme") or opts.get("theme") or "blue",
        "toc": meta.get("toc") or "true",
        "summary": meta.get("summary") or opts.get("summary")
                   or "（在这里写一句话摘要：读者读完能得到什么）",
    }
    lines.append("---")
    for k in ("title", "author", "date", "theme", "toc", "summary"):
        lines.append("{}: {}".format(k, fm[k]))
    lines.append("---")
    lines.append("")

    # ---- 标题
    lines.append("# {}".format(fm["title"]))
    lines.append("")

    # ---- 引言
    if opts["tips"]:
        lines.append(_hint(
            "引言怎么写：读者现在卡在哪 → 这篇能给他什么 → 凭什么信你。"
            "2-3 句就够，不要写背景铺垫。"))
    lines.append("（在这里写引言。写完删掉这行。）")
    lines.append("")

    # ---- 正文各章
    if not sections and loose:
        # 大纲只给了要点没分章：全部收进一章，避免内容被丢掉
        sections = [{"title": "正文", "points": list(loose), "notes": []}]

    for i, sec in enumerate(sections, 1):
        lines.append("## {}".format(sec["title"]))
        is_closing = any(w in sec["title"] for w in CLOSING_WORDS)

        if opts["tips"]:
            if is_closing:
                lines.append(_hint(
                    "结语怎么写：给一个可迁移的用法或下一步动作。"
                    "别写「谢谢观看」这种没有信息量的结尾。"))
            else:
                lines.append(_hint(
                    "本节要回答的问题：{}".format(clean_title(sec["title"]))))
        lines.append("")

        if sec["points"]:
            if opts["sections"]:
                for p in sec["points"]:
                    lines.append("### {}".format(p))
                    if opts["tips"]:
                        lines.append(_hint(
                            "展开这一节：先说结论，再给一个具体例子或数字。"))
                    lines.append("")
                    lines.append("（展开这里。）")
                    lines.append("")
            else:
                for p in sec["points"]:
                    lines.append("- {}".format(p))
                lines.append("")
                if opts["tips"]:
                    lines.append(_hint(
                        "把上面的要点展开成 2-3 段。"
                        "每个要点至少配一个具体例子、数字或代码。"))
                lines.append("（在这里展开。）")
                lines.append("")
        else:
            lines.append("（在这里写{}。）".format("结语" if is_closing else "正文"))
            lines.append("")

        for n in sec["notes"]:
            if opts["tips"]:
                lines.append(_hint("大纲备注：{}".format(n)))
                lines.append("")

    # ---- 结语（大纲里已经写了就不再补）
    has_closing = any(any(w in s["title"] for w in CLOSING_WORDS) for s in sections)
    if not has_closing:
        lines.append("## 结语")
        if opts["tips"]:
            lines.append(_hint(
                "收尾给一个可迁移的用法或下一步动作。"
                "别写「谢谢观看」这种没有信息量的结尾。"))
        lines.append("")
        lines.append("（在这里写结语。）")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------- 主流程

def make_draft(outline_path, draft_path, opts):
    src = Path(outline_path)
    if not src.is_file():
        print("[!] 找不到大纲文件: {}".format(outline_path))
        return False

    text = src.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print("[!] 大纲是空的，没有内容可以展开。")
        return False

    meta, title, sections, loose = parse_outline(text)
    if not sections and not loose and not title:
        print("[!] 没解析出任何标题或要点，请检查大纲格式"
              "（至少要有 # 标题 或 - 要点）。")
        return False

    out = Path(draft_path) if draft_path else src.with_name(src.stem + "_draft.md")
    if out.exists() and not opts.get("force"):
        print("[!] {} 已存在，未覆盖。要覆盖请加 --force。".format(out))
        return False

    content = build_draft(meta, title, sections, loose, opts)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")

    n_points = sum(len(s["points"]) for s in sections) + len(loose)
    print("[OK] 初稿已生成: {}".format(out))
    print("     章节 {} 个 / 要点 {} 条 / {} 字".format(
        len(sections), n_points, len(content)))
    print("     下一步: python scripts/convert_to_wechat.py {} --theme {}".format(
        out.name, opts.get("theme") or "blue"))
    return True


def main():
    ap = argparse.ArgumentParser(
        description="把大纲扩写成初稿（可直接交给 convert_to_wechat.py 排版）")
    ap.add_argument("outline", help="大纲文件（.md）")
    ap.add_argument("draft", nargs="?", help="输出初稿（默认 <大纲名>_draft.md）")
    ap.add_argument("--author", help="作者名，写进 front matter")
    ap.add_argument("--date", help="日期，默认今天")
    ap.add_argument("--summary", help="一句话摘要")
    ap.add_argument("--title", help="覆盖标题（默认取大纲里的 # 一级标题）")
    ap.add_argument("--theme", help="写进 front matter 的默认主题")
    ap.add_argument("--sections", action="store_true",
                    help="把每个要点提升为 ### 小节标题（默认只保留要点清单）")
    ap.add_argument("--no-tips", dest="tips", action="store_false", default=True,
                    help="不插入写作提示注释")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    args = ap.parse_args()

    ok = make_draft(args.outline, args.draft, {
        "author": args.author, "date": args.date, "summary": args.summary,
        "title": args.title, "theme": args.theme,
        "sections": args.sections, "tips": args.tips, "force": args.force,
    })
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
