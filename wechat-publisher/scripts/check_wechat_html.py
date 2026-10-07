#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公众号 HTML 自检工具 — 粘贴进编辑器之前先跑一遍。

用法：
    python check_wechat_html.py output.html
    python check_wechat_html.py output.html --strict

检查项对应 references/wechat_restrictions.md：
  1. 违规标签（script / style / iframe / div / h1 / svg / video / audio）
  2. 违规属性（class / id / on* 事件）
  3. 非 inline 样式（缺 style 属性的元素）
  4. 违规 CSS 属性（position / float / flex / grid / animation / transition）
  5. 图片（max-width、SVG base64、外链）
  6. 篇幅统计（字数、图片数、表格数、callout 数）
  7. 正文是否泄漏 CSS 声明（样式代码被当文字显示出来）

退出码：0 = 通过，1 = 有错误
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

WRONG_TAGS = ["script", "style", "iframe", "div", "h1", "svg", "video",
              "audio", "form", "input", "button", "canvas"]
BAD_ATTRS = ["class", "id"]
BAD_CSS = ["position", "float", "flex", "grid", "animation", "transition",
           "@media", "@font-face", "z-index", "transform"]
LIMITS = {"max_chars": 20000, "max_images": 100, "max_image_mb": 10}


def check(path, strict=False):
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    errors, warns, notes = [], [], []

    # 1. 违规标签
    for t in WRONG_TAGS:
        hits = soup.find_all(t)
        if hits:
            errors.append("违规标签 <{}> × {}（公众号会剥离或渲染异常）".format(
                t, len(hits)))

    # 2. 违规属性
    for a in BAD_ATTRS:
        hits = soup.find_all(attrs={a: True})
        if hits:
            errors.append("违规属性 {} × {}（公众号不支持 CSS 类/ID）".format(
                a, len(hits)))
    js = soup.find_all(attrs={"onclick": True}) + soup.find_all(attrs={"onload": True})
    if js:
        errors.append("存在 JS 事件属性 × {}（一定被剥离）".format(len(js)))
    if "javascript:" in raw.lower():
        errors.append("存在 javascript: 协议链接")

    # 3. 非 inline 样式：进入公众号的内容里不应出现裸标签
    styled_bad = []
    for name in ("p", "h2", "h3", "li", "td", "th", "img", "ul", "ol"):
        for el in soup.find_all(name):
            if el.get("style") is None and not (name == "img"):
                styled_bad.append(name)
    if styled_bad:
        count = Counter(styled_bad)
        warns.append("这些标签缺少 inline style（粘贴后可能样式丢失）: " + ", ".join(
            "{}×{}".format(k, v) for k, v in count.items()))

    # 4. 违规 CSS 属性
    bad_css_hits = Counter()
    for el in soup.find_all(style=True):
        s = el["style"].lower()
        for prop in BAD_CSS:
            if prop + ":" in s:
                bad_css_hits[prop] += 1
    if bad_css_hits:
        errors.append("包含公众号不支持的 CSS: " + ", ".join(
            "{}×{}".format(k, v) for k, v in bad_css_hits.items()))

    # 5. 图片
    imgs = soup.find_all("img")
    for i, img in enumerate(imgs, 1):
        src = img.get("src", "")
        style = (img.get("style") or "").replace(" ", "")
        if "max-width" not in style:
            warns.append("第 {} 张图缺 max-width，长图会撑破手机屏幕".format(i))
        if src.startswith("data:image/svg"):
            errors.append("第 {} 张图是 SVG base64 —— 公众号保存后会消失，请换 PNG".format(i))
        elif src.startswith("http"):
            warns.append("第 {} 张图是外链，可能需要先上传到公众号素材库".format(i))
        elif not src.startswith("data:"):
            warns.append("第 {} 张图没嵌入（src={}），粘贴到公众号后会是空白，"
                         "请用 --embed-images 重新转换".format(i, src[:40]))
    if len(imgs) > LIMITS["max_images"]:
        errors.append("图片数 {} 超过公众号上限 {}".format(len(imgs), LIMITS["max_images"]))

    # 6. 统计
    body = soup.find("body") or soup
    text = body.get_text()
    chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    notes.append("中文字数：{}".format(chars))
    notes.append("段落 {} / 小标题 {} / 表格 {} / 图片 {} / 列表 {}".format(
        len(soup.find_all("p")), len(soup.find_all(["h2", "h3"])),
        len(soup.find_all("table")), len(imgs),
        len(soup.find_all(["ul", "ol"]))))
    if chars > LIMITS["max_chars"]:
        warns.append("中文字数 {} 超过公众号单篇上限约 {}".format(
            chars, LIMITS["max_chars"]))

    # 7. 正文里泄漏的 CSS 声明
    #    典型症状：拼字符串生成目录/脚注时，把 "padding-left: 24px; " 这类
    #    样式代码直接拼进了文本节点，页面上会明文显示出来。这种问题肉眼很难
    #    扫到（尤其长文），但一眼就会被读者看到，所以单独做一道检测。
    #    注意：代码块和行内代码（等宽字体）里的内容跳过 —— 否则一篇「讲 CSS」
    #    的文章，正文里正常引用的 CSS 示例会被误判成泄漏，永远过不了自检。
    css_decl = re.compile(
        r"\b(?:padding|margin|color|background|font|line-height|letter-spacing"
        r"|text-align|text-indent|border|width|height|display|white-space"
        r"|box-sizing|flex|grid|position|float|overflow|vertical-align)"
        r"[a-z-]*\s*:\s*[^;<>{}]{1,40};", re.I)
    leaked = []
    for node in soup.find_all(string=True):
        parent = node.parent
        if parent is None or parent.name in ("script", "style", "title"):
            continue
        # 父节点自己也要判（行内代码就是包在 <span style="...monospace..."> 里）
        if "monospace" in (parent.get("style") or ""):
            continue
        if any("monospace" in (a.get("style") or "") for a in parent.parents):
            continue
        if css_decl.search(str(node)):
            leaked.append(str(node).strip()[:70])
    if leaked:
        errors.append(
            "正文里泄漏了 CSS 声明 × {} —— 样式代码会被当文字显示出来: {}".format(
                len(leaked), " | ".join(leaked[:3])))

    # 输出
    print("=" * 56)
    print("公众号 HTML 自检：{}".format(Path(path).name))
    print("=" * 56)
    for n in notes:
        print("  · " + n)
    print("-" * 56)
    if errors:
        print("[错误] {} 项（必须修）".format(len(errors)))
        for e in errors:
            print("   x " + e)
    if warns:
        print("[提醒] {} 项（建议确认）".format(len(warns)))
        for w in warns:
            print("   ! " + w)
    if not errors and not warns:
        print("[通过] 未发现问题，可以粘贴进公众号编辑器。")
    elif not errors:
        print("[基本通过] 无致命错误。")
    print("=" * 56)

    if strict and warns:
        return 1
    return 1 if errors else 0


def main():
    ap = argparse.ArgumentParser(description="公众号 HTML 自检工具")
    ap.add_argument("html", help="要检查的 HTML 文件")
    ap.add_argument("--strict", action="store_true",
                    help="把提醒也当作失败")
    args = ap.parse_args()
    if not Path(args.html).exists():
        print("[!] 找不到文件: {}".format(args.html))
        return 1
    return check(args.html, args.strict)


if __name__ == "__main__":
    sys.exit(main())
