#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_formats.py — 一稿多投 + 体裁模板（wechat-publisher 的 Level 4 扩展）

同一份 Markdown，一次导出三种可直接投递的格式：

    公众号 HTML   —— 走 convert_to_wechat.py 的完整清洗与排版
    知乎 Markdown —— 保留 markdown 结构，callout 变引用块（知乎支持引用）
    纯文本        —— 剥掉全部标记，适合发群、发邮件、贴工单

用法：
    # 三格式一起出
    python scripts/export_formats.py article.md --outdir dist

    # 只出知乎版和纯文本
    python scripts/export_formats.py article.md --outdir dist --formats zhihu,plain

    # 公众号版想换主题 / 加目录
    python scripts/export_formats.py article.md --outdir dist --theme blue --toc

    # 用体裁模板开一篇新稿
    python scripts/export_formats.py --list-templates
    python scripts/export_formats.py --new tech-tutorial drafts/my-post.md

设计原则：三种格式**共用同一份源文件**。不要为了适配某个平台去改源稿 ——
源稿是唯一真相，格式只是出口。
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_DIR / "templates"

sys.path.insert(0, str(SCRIPT_DIR))
import convert_to_wechat as cw  # noqa: E402  （同目录，必须在 path 之后导入）


TEMPLATE_LABELS = {
    "tech-tutorial": "技术教程 —— 让我一步步教你做成某件事",
    "learning-note": "学习心得 —— 我做了一个 X，过程与踩坑",
    "skill-intro": "技能/产品介绍 —— 这是什么、怎么用、给谁用",
    "retrospective": "复盘总结 —— 目标 / 结果 / 差距 / 改进",
}

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
CALLOUT_OPEN = re.compile(r"^:::\s*(\w+)\s*(.*)$")
CALLOUT_CLOSE = ":::"


# ---------------------------------------------------------------- 结构解析


def split_front_matter(text):
    """拆出文件头元数据与正文，正文里不留 --- 分隔线。"""
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, text[m.end():]


def split_blocks(text):
    """
    把正文拆成有序块：
      ("text", 原文)                    普通段落
      ("callout", 类型, 标题, 正文)      ::: 高亮框

    为什么不在字符串上直接正则替换：callout 是**多行**结构，
    逐行状态机比正则可靠（正则遇到嵌套或空行会开始猜）。
    """
    blocks, buf, lines, i = [], [], text.split("\n"), 0
    while i < len(lines):
        m = CALLOUT_OPEN.match(lines[i].strip())
        if m and m.group(1).lower() in cw.CALLOUT_TYPES:
            if buf:
                blocks.append(("text", "\n".join(buf)))
                buf = []
            ctype, title, body = m.group(1).lower(), m.group(2).strip(), []
            i += 1
            while i < len(lines) and lines[i].strip() != CALLOUT_CLOSE:
                body.append(lines[i])
                i += 1
            blocks.append(("callout", ctype, title, "\n".join(body).strip()))
        else:
            buf.append(lines[i])
        i += 1
    if buf:
        blocks.append(("text", "\n".join(buf)))
    return blocks


def _callout_label(ctype, title):
    cfg = cw.CALLOUT_TYPES.get(ctype, {})
    return title or cfg.get("label", ctype)


# ---------------------------------------------------------------- 各格式渲染


def render_zhihu(meta, blocks):
    """
    知乎版：保留 markdown 结构，callout 降级成引用块。
    知乎编辑器原生支持 markdown 粘贴，也支持 > 引用，所以这是最省事的映射。
    """
    out = []
    if meta.get("title"):
        out.append("# " + meta["title"])
    if meta.get("author") or meta.get("date"):
        out.append("  ·  ".join(b for b in (meta.get("author"),
                                           meta.get("date")) if b))
    if meta.get("summary"):
        out.append("> " + meta["summary"])

    for block in blocks:
        if block[0] == "text":
            out.append(block[1].strip("\n"))
        else:
            _, ctype, title, body = block
            head = "**{}**".format(_callout_label(ctype, title))
            quoted = ["> " + head, ">"]
            for ln in body.split("\n"):
                quoted.append(("> " + ln).rstrip())
            out.append("\n".join(quoted))
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(out)).strip() + "\n"


def md_to_plain(s):
    """把一段 markdown 压成纯文字。"""
    s = re.sub(r"^\s*```.*$", "", s, flags=re.M)              # 代码围栏
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.M)              # 标题符号
    s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"[图片：\1]", s)  # 图片
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1（\2）", s)     # 链接
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)                    # 加粗
    s = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", s)  # 斜体
    s = re.sub(r"`([^`]*)`", r"\1", s)                        # 行内代码
    s = re.sub(r"^\s*[-*+]\s+", "· ", s, flags=re.M)          # 无序列表
    s = re.sub(r"^\s*>\s?", "", s, flags=re.M)                # 引用
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def render_plain(meta, blocks):
    """纯文本版：连符号都不留，只留能直接读的文字。"""
    out = []
    if meta.get("title"):
        out.append(meta["title"])
        out.append("=" * min(48, max(8, len(meta["title"]) * 2)))
    if meta.get("author") or meta.get("date"):
        out.append("  ·  ".join(b for b in (meta.get("author"),
                                           meta.get("date")) if b))
    if meta.get("summary"):
        out.append("摘要：" + meta["summary"])
    if out:
        out.append("")

    for block in blocks:
        if block[0] == "text":
            piece = md_to_plain(block[1])
            if piece:
                out.append(piece)
        else:
            _, ctype, title, body = block
            out.append("【{}】".format(_callout_label(ctype, title)))
            out.append(md_to_plain(body))
        out.append("")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


# ---------------------------------------------------------------- 导出主流程


def export(input_path, outdir, formats, opts):
    src = Path(input_path)
    if not src.is_file():
        print("[!] 找不到文件: {}".format(input_path))
        return 1

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stem = src.stem
    text = src.read_text(encoding="utf-8", errors="replace")
    meta, body = split_front_matter(text)
    blocks = split_blocks(body)

    made = []
    if "wechat" in formats:
        out = outdir / "{}.wechat.html".format(stem)
        if cw.convert(str(src), str(out), opts):
            made.append(("wechat", out, out.stat().st_size))
    if "zhihu" in formats:
        out = outdir / "{}.zhihu.md".format(stem)
        out.write_text(render_zhihu(meta, blocks), encoding="utf-8")
        made.append(("zhihu", out, out.stat().st_size))
    if "plain" in formats:
        out = outdir / "{}.plain.txt".format(stem)
        out.write_text(render_plain(meta, blocks), encoding="utf-8")
        made.append(("plain", out, out.stat().st_size))

    print("-" * 56)
    print("一稿多投完成：{}".format(src.name))
    for kind, path, size in made:
        print("  [{:6s}] {}（{:.1f} KB）".format(kind, path, size / 1024))
    print("  源稿只有一份，三个出口共用 —— 不要为了平台去改源稿。")
    print("-" * 56)
    return 0 if made else 1


def list_templates():
    print("-" * 56)
    print("可用体裁模板（{}）".format(TEMPLATE_DIR))
    for name, desc in TEMPLATE_LABELS.items():
        exists = (TEMPLATE_DIR / (name + ".md")).is_file()
        print("  {}{:16s} {}".format("" if exists else "[缺失] ", name, desc))
    print("-" * 56)
    print("用法：python scripts/export_formats.py --new <模板名> <目标路径>")
    return 0


def new_article(template, dest):
    src = TEMPLATE_DIR / (template + ".md")
    if not src.is_file():
        print("[!] 没有这个模板: {}（可用：{}）".format(
            template, ", ".join(TEMPLATE_LABELS)))
        return 1
    dest = Path(dest)
    if dest.exists():
        print("[!] 目标已存在，不覆盖: {}".format(dest))
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(src), str(dest))
    print("已按「{}」模板生成：{}".format(
        TEMPLATE_LABELS.get(template, template), dest))
    print("下一步：填内容 → python scripts/export_formats.py {} --outdir dist".format(dest))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="一稿多投：Markdown → 公众号 HTML / 知乎 Markdown / 纯文本",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", help="输入 Markdown")
    ap.add_argument("--outdir", default="dist", help="输出目录（默认 dist）")
    ap.add_argument("--formats", default="wechat,zhihu,plain",
                    help="要出的格式，逗号分隔（默认三种全出）")
    ap.add_argument("--theme", choices=cw.THEME_ORDER, help="公众号版配色主题")
    ap.add_argument("--accent", help="覆盖主题主色")
    ap.add_argument("--toc", dest="toc", action="store_true", default=None,
                    help="公众号版生成目录")
    ap.add_argument("--no-cjk-spacing", dest="cjk", action="store_false",
                    default=None, help="关闭中英文自动加空格")
    ap.add_argument("--image-width", default="100%", help="公众号版图片最大宽度")
    ap.add_argument("--quiet", action="store_true", help="减少公众号版的转换输出")
    ap.add_argument("--list-templates", action="store_true", help="列出体裁模板")
    ap.add_argument("--new", metavar="模板名", help="按模板新建一篇文章")

    args = ap.parse_args()

    if args.list_templates:
        return list_templates()

    if args.new:
        if not args.input:
            print("[!] 用 --new 时要把目标路径写在后面，例如："
                  "--new tech-tutorial drafts/my-post.md")
            return 1
        return new_article(args.new, args.input)

    if not args.input:
        ap.print_help()
        return 1

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    unknown = [f for f in formats if f not in ("wechat", "zhihu", "plain")]
    if unknown:
        print("[!] 不认识的格式: {}（可选 wechat / zhihu / plain）".format(
            ", ".join(unknown)))
        return 1

    opts = {"theme": args.theme, "accent": args.accent, "toc": args.toc,
            "cjk": args.cjk, "title": None, "author": None, "date": None,
            "summary": None, "footer": None, "embed_images": True,
            "captions": True, "image_width": args.image_width,
            "quiet": args.quiet}
    return export(args.input, args.outdir, formats, opts)


if __name__ == "__main__":
    sys.exit(main())
