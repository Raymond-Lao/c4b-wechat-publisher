#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WeChat Publisher — Markdown / Word → 公众号 HTML（增强版）

基线：EduSeed C4B starter kit 的 convert_to_wechat.py（拿来主义）
本版在基线上做了两件事：
  A. 修掉基线里的 5 个真实缺陷（见 references/CHANGELOG.md）
  B. 新增 6 项能力：主题系统 / callout 高亮框 / 自动目录 / 元数据与页脚 /
     中文排版优化 / 批量转换

用法：
    python convert_to_wechat.py article.md
    python convert_to_wechat.py article.md out.html --theme blue --toc
    python convert_to_wechat.py report.docx out.html --author 李瑞翔
    python convert_to_wechat.py --batch ./drafts --theme warm

输出后：浏览器打开 → Ctrl+A → Ctrl+C → 粘贴进公众号编辑器。
"""

import argparse
import base64
import html as html_mod
import io
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

# ---------------------------------------------------------------- 依赖自检

def ensure_dependencies():
    missing = []
    for mod, pkg in (("markdown", "markdown"), ("bs4", "beautifulsoup4"),
                     ("docx", "python-docx")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print("[deps] 正在安装缺失依赖: " + ", ".join(missing))
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               *missing, "--break-system-packages", "-q"])
        print("[deps] 完成\n")


ensure_dependencies()

import markdown as md_lib
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

# ---------------------------------------------------------------- 常量

# 公众号允许的标签
ALLOWED_TAGS = {
    "p", "h2", "h3", "ul", "ol", "li", "span", "img", "a",
    "table", "tr", "th", "td", "br", "hr", "thead", "tbody", "strong", "em",
}

# 公众号禁止、需要删除或降级的标签
DROP_TAGS = {"script", "style", "iframe", "video", "audio", "svg", "form", "input"}

# 公众号会存活的位图格式 → MIME。SVG 不在其中：公众号保存时会把 SVG 丢掉，
# 所以本地 SVG 图片不嵌入，只报警告，让作者自己转 PNG。
IMG_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}

# 允许保留的 CSS 属性
ALLOWED_CSS = {
    "color", "background-color", "font-size", "font-weight", "font-style",
    "line-height", "text-align", "margin", "padding", "border",
    "border-left", "border-top", "border-bottom", "border-collapse",
    "text-decoration", "display", "vertical-align", "max-width", "width",
    "height", "font-family", "letter-spacing", "text-indent", "overflow",
    # 以下 4 项基线参考文档未列，但公众号编辑器实测支持，属于本技能的扩展
    "border-radius", "white-space", "word-break", "overflow-wrap",
}

# 主题定义：改一处即可换整篇风格
THEMES = {
    "default": {
        "label": "默认 · 中性灰",
        "accent": "#3f3f46",
        "accent_soft": "#f6f7f9",
        "text": "#333333",
        "text_soft": "#6b7280",
        "rule": "#e5e7eb",
        "h2_bar": False,
        "divider": "· · ·",
        "radius": "8px",
    },
    "blue": {
        "label": "蓝色 · 科技学术",
        "accent": "#1a73e8",
        "accent_soft": "#eef4ff",
        "text": "#22303f",
        "text_soft": "#5b6b7c",
        "rule": "#d7e3f4",
        "h2_bar": True,
        "divider": "— — —",
        "radius": "8px",
    },
    "warm": {
        "label": "暖色 · 生活分享",
        "accent": "#e65100",
        "accent_soft": "#fff6e8",
        "text": "#3d2f24",
        "text_soft": "#7a6553",
        "rule": "#f0dcc4",
        "h2_bar": True,
        "divider": "· · ·",
        "radius": "10px",
    },
    "minimal": {
        "label": "极简 · 纯文字",
        "accent": "#333333",
        "accent_soft": "#fafafa",
        "text": "#333333",
        "text_soft": "#888888",
        "rule": "#ebebeb",
        "h2_bar": False,
        "divider": "———",
        "radius": "0px",
    },
    "elegant": {
        "label": "雅致 · 深青衬线",
        "accent": "#0f6e56",
        "accent_soft": "#eaf7f2",
        "text": "#26332f",
        "text_soft": "#5f726b",
        "rule": "#cfe6dd",
        "h2_bar": True,
        "divider": "◇ ◇ ◇",
        "radius": "8px",
    },
}

THEME_ORDER = ["default", "blue", "warm", "minimal", "elegant"]

# callout 四种类型：公众号文章最实用的排版元素
CALLOUT_TYPES = {
    "note":     {"icon": "📘", "label": "知识点", "accent": "#1a73e8", "bg": "#eef4ff"},
    "tip":      {"icon": "💡", "label": "小提示", "accent": "#0f6e56", "bg": "#eaf7f2"},
    "warn":     {"icon": "⚠️", "label": "注意", "accent": "#b45309", "bg": "#fff7e6"},
    "practice": {"icon": "🔧", "label": "动手做", "accent": "#6d28d9", "bg": "#f5f1ff"},
}

MONO = ("ui-monospace, SFMono-Regular, Menlo, Consolas, "
        "'Courier New', monospace")

# ---------------------------------------------------------------- 样式生成


def build_styles(theme_key, accent_override=None):
    """按主题生成全部 inline CSS。"""
    t = dict(THEMES[theme_key])
    if accent_override:
        t["accent"] = accent_override

    h2_extra = (f" padding-left: 10px; border-left: 4px solid {t['accent']};"
                if t["h2_bar"] else "")

    return {
        "h2": (f"font-size: 22px; font-weight: bold; line-height: 1.5; "
               f"color: {t['accent']}; margin: 32px 0 14px 0;{h2_extra}"),
        "h3": (f"font-size: 17px; font-weight: bold; line-height: 1.6; "
               f"color: {t['text']}; margin: 22px 0 10px 0;"),
        "p": (f"font-size: 16px; line-height: 1.75; color: {t['text']}; "
              f"margin: 14px 0; letter-spacing: 0.3px;"),
        "li": (f"font-size: 16px; line-height: 1.75; color: {t['text']}; "
               f"margin: 6px 0; letter-spacing: 0.3px;"),
        "ul": "margin: 12px 0; padding-left: 24px;",
        "ol": "margin: 12px 0; padding-left: 24px;",
        "code_inline": (f"background-color: #f5f5f5; color: #d73a49; "
                        f"font-size: 14px; padding: 2px 5px; "
                        f"border-radius: 3px; font-family: {MONO};"),
        "code_block": (f"background-color: {t['accent_soft']}; "
                       f"color: #24292e; font-size: 13px; line-height: 1.7; "
                       f"padding: 14px 16px; margin: 16px 0; "
                       f"border-radius: {t['radius']}; font-family: {MONO}; "
                       f"white-space: pre-wrap; word-break: break-all;"),
        "blockquote": (f"background-color: {t['accent_soft']}; "
                       f"color: {t['text_soft']}; font-size: 15px; "
                       f"line-height: 1.8; padding: 12px 16px; margin: 18px 0; "
                       f"border-left: 4px solid {t['accent']}; "
                       f"border-radius: 0 {t['radius']} {t['radius']} 0;"),
        "table": ("border-collapse: collapse; margin: 16px 0; "
                  "font-size: 14px; width: 100%;"),
        "th": (f"background-color: {t['accent_soft']}; color: {t['text']}; "
               f"font-weight: bold; padding: 9px 10px; text-align: left; "
               f"border: 1px solid {t['rule']};"),
        "td": (f"padding: 9px 10px; border: 1px solid {t['rule']}; "
               f"color: {t['text']}; line-height: 1.6;"),
        "a": f"color: {t['accent']}; text-decoration: underline;",
        "img": (f"max-width: 100%; height: auto; display: block; "
                f"margin: 18px auto; border-radius: {t['radius']};"),
        "img_caption": (f"font-size: 13px; line-height: 1.6; "
                        f"color: {t['text_soft']}; text-align: center; "
                        f"margin: -8px 0 20px 0;"),
        "hr": (f"text-align: center; color: {t['rule']}; "
               f"letter-spacing: 6px; font-size: 13px; margin: 30px 0;"),
        "meta_title": (f"font-size: 24px; font-weight: bold; line-height: 1.45; "
                       f"color: {t['accent']}; text-align: center; "
                       f"margin: 0 0 10px 0;"),
        "meta_byline": (f"font-size: 13px; color: {t['text_soft']}; "
                        f"text-align: center; margin: 0 0 6px 0; "
                        f"letter-spacing: 0.5px;"),
        "summary": (f"background-color: {t['accent_soft']}; "
                    f"color: {t['text_soft']}; font-size: 15px; "
                    f"line-height: 1.8; padding: 14px 16px; margin: 20px 0; "
                    f"border-radius: {t['radius']}; "
                    f"border-left: 4px solid {t['accent']};"),
        "toc": (f"background-color: {t['accent_soft']}; padding: 16px 18px; "
                f"margin: 20px 0; border-radius: {t['radius']};"),
        "toc_title": (f"font-size: 15px; font-weight: bold; "
                      f"color: {t['accent']}; margin: 0 0 8px 0; "
                      f"letter-spacing: 1px;"),
        "toc_item": (f"font-size: 15px; line-height: 1.9; "
                     f"color: {t['text']}; margin: 0;"),
        "toc_num": (f"color: {t['accent']}; font-weight: bold; "
                    f"font-family: {MONO}; font-size: 13px;"),
        "footer": (f"font-size: 12px; line-height: 1.9; "
                   f"color: {t['text_soft']}; text-align: center; "
                   f"margin: 40px 0 0 0; padding-top: 18px; "
                   f"border-top: 1px solid {t['rule']};"),
    }


# ---------------------------------------------------------------- 输入读取


FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def parse_front_matter(text):
    """解析文件头的简单 key: value 元数据块。"""
    meta = {}
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return meta, text
    for line in m.group(1).splitlines():
        if ":" in line and not line.strip().startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta, text[m.end():]


CALLOUT_OPEN = re.compile(r"^:::\s*(\w+)\s*(.*)$")
PLACEHOLDER = "@@C4B_CALLOUT_{}@@"


def extract_callouts(text):
    """
    把 ::: type 标题 ... ::: 块抽出来，正文里留下占位符。
    这样 callout 内部的 **加粗** 等 markdown 仍能被正常渲染。
    """
    lines = text.split("\n")
    out, callouts, i = [], [], 0
    while i < len(lines):
        m = CALLOUT_OPEN.match(lines[i].strip())
        if m and m.group(1).lower() in CALLOUT_TYPES:
            ctype = m.group(1).lower()
            title = m.group(2).strip()
            body = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                body.append(lines[i])
                i += 1
            idx = len(callouts)
            callouts.append({"type": ctype, "title": title,
                             "body": "\n".join(body).strip()})
            out.append("")
            out.append(PLACEHOLDER.format(idx))
            out.append("")
        else:
            out.append(lines[i])
        i += 1
    return "\n".join(out), callouts


def read_markdown(filepath):
    """Markdown → (HTML, callouts, meta)"""
    raw = Path(filepath).read_text(encoding="utf-8", errors="replace")
    meta, body = parse_front_matter(raw)
    body, callouts = extract_callouts(body)
    html = md_lib.markdown(body, extensions=[
        "extra", "fenced_code", "nl2br", "sane_lists", "tables",
    ])
    return html, callouts, meta


def _iter_docx_blocks(doc):
    """按文档顺序产出段落与表格。"""
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, doc)
        elif child.tag.endswith("}tbl"):
            yield Table(child, doc)


def _docx_image_data_uri(para, doc):
    """把段落里的内嵌图片转成 base64 data URI（公众号接受 PNG/JPG base64）。"""
    uris = []
    blips = para._p.findall(
        ".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
    for blip in blips:
        rid = blip.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/"
            "relationships}embed")
        if not rid:
            continue
        try:
            part = doc.part.related_parts[rid]
            ct = part.content_type or "image/png"
            if "jpeg" in ct or "jpg" in ct:
                ct = "image/jpeg"
            elif "gif" in ct:
                ct = "image/gif"
            else:
                ct = "image/png"
            b64 = base64.b64encode(part.blob).decode("ascii")
            uris.append("data:{};base64,{}".format(ct, b64))
        except Exception:
            continue
    return uris


def read_docx(filepath):
    """Word .docx → HTML（含表格、列表、内嵌图片）"""
    doc = Document(filepath)
    parts = []
    list_mode = None

    def close_list():
        nonlocal list_mode
        if list_mode:
            parts.append("</{}>".format(list_mode))
            list_mode = None

    for block in _iter_docx_blocks(doc):
        if isinstance(block, Table):
            close_list()
            rows = []
            for r_i, row in enumerate(block.rows):
                cells = []
                for cell in row.cells:
                    txt = html_mod.escape(cell.text.strip())
                    tag = "th" if r_i == 0 else "td"
                    cells.append("<{0}>{1}</{0}>".format(tag, txt))
                rows.append("<tr>{}</tr>".format("".join(cells)))
            parts.append("<table>{}</table>".format("".join(rows)))
            continue

        para = block
        text = para.text.strip()
        imgs = _docx_image_data_uri(para, doc)
        style_name = (para.style.name or "") if para.style else ""

        if not text and not imgs:
            continue

        if style_name.startswith("Heading"):
            close_list()
            lvl = style_name.replace("Heading ", "").strip()
            tag = "h2" if lvl in ("1", "2") else "h3"
            parts.append("<{0}>{1}</{0}>".format(tag, html_mod.escape(text)))
            continue

        is_bullet = "List Bullet" in style_name
        is_number = "List Number" in style_name
        if is_bullet or is_number:
            want = "ul" if is_bullet else "ol"
            if list_mode != want:
                close_list()
                parts.append("<{}>".format(want))
                list_mode = want
            parts.append("<li>{}</li>".format(html_mod.escape(text)))
            continue

        close_list()

        if style_name in ("Quote", "Intense Quote") or style_name.startswith("Quote"):
            parts.append("<blockquote>{}</blockquote>".format(
                html_mod.escape(text)))
        else:
            buf = ["<p>"]
            for run in para.runs:
                t = html_mod.escape(run.text) if run.text else ""
                if not t:
                    continue
                if run.bold and run.italic:
                    buf.append('<span style="font-weight:bold;'
                               'font-style:italic;">{}</span>'.format(t))
                elif run.bold:
                    buf.append('<span style="font-weight:bold;">{}</span>'.format(t))
                elif run.italic:
                    buf.append('<span style="font-style:italic;">{}</span>'.format(t))
                else:
                    buf.append(t)
            buf.append("</p>")
            parts.append("".join(buf))

        for uri in imgs:
            parts.append('<img src="{}" alt="">'.format(uri))

    close_list()
    return "\n".join(parts), [], {}


# ---------------------------------------------------------------- 清洗与套样式


def _split_style(style):
    """把 style 字符串拆成 (属性, 值) 列表。"""
    out = []
    for decl in style.split(";"):
        if ":" not in decl:
            continue
        k, v = decl.split(":", 1)
        k = k.strip().lower()
        v = v.strip()
        if k and v:
            out.append((k, v))
    return out


def filter_css(style):
    """只保留白名单里的 CSS 属性（修掉基线里 ALLOWED_CSS 是死代码的问题）。"""
    kept = ["{}: {}".format(k, v) for k, v in _split_style(style)
            if k in ALLOWED_CSS]
    return "; ".join(kept) + (";" if kept else "")


BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "div", "li", "pre",
              "section", "article", "main", "figure", "figcaption",
              "dl", "dt", "dd"}


def _flatten_to_inline(html_str):
    """
    把一段 HTML 片段压平成一串可塞进单个 <p> 的行内 HTML。

    公众号里嵌套 <p> 不可靠，所以**块级段落之间**改用 <br> 连接。

    【修复 1：列表内容被静默丢弃】
    callout 最终渲染成**单个 <p>**，而 HTML 规则不允许 <p> 里嵌 <ol>/<ul>：
    解析器会把列表甩到 <p> 外面，调用方又只取那个 <p>，整个列表连同文字就被
    丢掉了——脚本不报错、退出码 0，只是内容凭空少了一块。
    所以列表必须在这里就压平成 "1. 文字<br>• 文字" 这种行内形式。

    【修复 2：只在块级元素之间换行】
    换行必须发生在**块级元素之间**，不能发生在行内元素之间 ——
    否则「这是**重点**内容」会被拆成三行。
    """
    frag = BeautifulSoup(html_str or "", "html.parser")
    return "<br>".join(_flatten_blocks(frag))


def _flatten_blocks(node):
    """把子节点按「块级 vs 行内」分组，返回块列表（每块内部是行内 HTML）。"""
    blocks, buf = [], ""

    def flush():
        nonlocal buf
        if buf.strip():
            blocks.append(buf.strip())
        buf = ""

    for child in node.children:
        if not isinstance(child, Tag):
            buf += str(child)
            continue

        name = child.name
        if name == "br":
            buf += "<br>"
        elif name in ("ul", "ol"):
            flush()
            for i, li in enumerate(child.find_all("li", recursive=False), 1):
                mark = "• " if name == "ul" else "{}. ".format(i)
                inner = _flatten_to_inline(li.decode_contents())
                if inner:
                    blocks.append(html_mod.escape(mark) + inner)
        elif name == "blockquote":
            flush()
            inner = _flatten_to_inline(child.decode_contents())
            if inner:
                blocks.append(html_mod.escape("> ") + inner)
        elif name == "table":
            flush()
            for tr in child.find_all("tr"):
                cells = [c.get_text(" ", strip=True)
                         for c in tr.find_all(["td", "th"])]
                if cells:
                    blocks.append(html_mod.escape(" | ".join(cells)))
        elif name == "hr":
            flush()
            blocks.append(html_mod.escape("· · ·"))
        elif name in BLOCK_TAGS:
            flush()
            inner = _flatten_to_inline(child.decode_contents())
            if inner:
                blocks.append(inner)
        else:
            # 行内标签（strong / em / code / span / a / img…）：留在当前块内
            buf += str(child)

    flush()
    return blocks


def _inline_md(text):
    """
    把一行文本按 markdown 内联语法解析，剥掉外层 <p> 后返回。

    【修复：callout 标题的 markdown 内联格式不生效】
    标题此前只做了 escape，所以 `::: tip 标题带**加粗**` 会把星号原样
    显示在文章里（正文里的加粗正常，因为正文走了 markdown 解析，唯独
    标题这一行漏了）。星号裸露在公众号排版里是很显眼的瑕疵。
    """
    if not text:
        return ""
    frag = BeautifulSoup(md_lib.markdown(text, extensions=["extra"]), "lxml")
    p = frag.find("p")
    if p is None:
        return html_mod.escape(text)
    return p.decode_contents().strip()


def _render_callout(callout):
    """callout 数据 → 公众号安全的 <p> 块。"""
    cfg = CALLOUT_TYPES[callout["type"]]
    label = callout["title"] or cfg["label"]
    body_md = md_lib.markdown(callout["body"],
                              extensions=["extra", "nl2br", "sane_lists"])
    inner_html = _flatten_to_inline(body_md)
    head = '<span style="font-weight:bold;color:{};">{} {}</span>'.format(
        cfg["accent"], cfg["icon"], _inline_md(label))
    style = ("background-color: {}; border-left: 4px solid {}; "
             "border-radius: 0 8px 8px 0; padding: 13px 16px; "
             "margin: 18px 0; font-size: 15px; line-height: 1.8; "
             "color: #333333;").format(cfg["bg"], cfg["accent"])
    return '<p style="{}">{}<br>{}</p>'.format(style, head, inner_html)


def sanitize(html, callouts, styles, divider="· · ·"):
    """按公众号规则清洗 HTML。"""
    soup = BeautifulSoup(html, "lxml")

    # 0. callout 占位符 → 真正的 callout 块
    #    【修复】早期只取 fragment.find("p")，一旦 callout 渲染出多个顶层块
    #    （例如列表被解析器甩出 <p>），多余的部分会被静默丢弃。现在把全部
    #    顶层块都替换进去，绝不丢内容。
    for idx, callout in enumerate(callouts):
        marker = PLACEHOLDER.format(idx)
        for node in soup.find_all(string=re.compile(re.escape(marker))):
            holder = node.parent
            fragment = BeautifulSoup(_render_callout(callout), "lxml")
            root = fragment.find("body") or fragment
            blocks = [c.extract() for c in list(root.children)
                      if str(c).strip()]
            if not blocks:
                break
            if holder is not None and holder.name == "p":
                holder.replace_with(*blocks)
            elif holder is not None:
                node.replace_with(*blocks)
            break

    # 1. 删除 HTML 注释。
    #    写作提示是用 <!-- --> 写的（outline_to_draft 生成的初稿里全是），
    #    写的时候看得见就够了；公众号编辑器对注释的处理不明确，留着只是增加不确定性。
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # 2. 删除禁止标签
    for tag_name in DROP_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()

    # 3. h1 → h2（公众号 h1 被标题占用）
    for h1 in soup.find_all("h1"):
        h1.name = "h2"

    # 4. div → p
    for div in soup.find_all("div"):
        div.name = "p"

    # 5. hr → 分隔符段落【修复基线：hr 会被 unwrap 导致分节线消失】
    for hr in soup.find_all("hr"):
        p = soup.new_tag("p")
        p["style"] = styles["hr"]
        p.string = divider
        hr.replace_with(p)

    # 6. 代码块 → 带样式的 <p>，保留换行【修复基线：丢掉嵌套、换行丢失】
    for pre in soup.find_all("pre"):
        code = pre.find("code")
        src = code if code is not None else pre
        lines = src.decode_contents().split("\n")
        p = soup.new_tag("p")
        p["style"] = styles["code_block"]
        for i, line in enumerate(lines):
            if i:
                p.append(soup.new_tag("br"))
            p.append(NavigableString(html_mod.unescape(line)))
        pre.replace_with(p)

    # 7. 行内 code → span
    for code in soup.find_all("code"):
        span = soup.new_tag("span")
        span["style"] = styles["code_inline"]
        span.string = code.get_text()
        code.replace_with(span)

    # 8. 引用块 → 带样式的 <p>，保留内部换行与加粗
    #    【修复基线：get_text() 把多行压成一行且丢掉加粗】
    for bq in soup.find_all("blockquote"):
        new_p = soup.new_tag("p")
        new_p["style"] = styles["blockquote"]
        inline = _flatten_to_inline(bq.decode_contents())
        frag = BeautifulSoup(inline, "html.parser")
        for child in list(frag.children):
            new_p.append(child.extract() if isinstance(child, Tag) else str(child))
        bq.replace_with(new_p)

    # 9. strong / em → span（公众号不认 <strong> 的样式继承）
    for tag in soup.find_all(["strong", "b"]):
        span = soup.new_tag("span")
        span["style"] = "font-weight: bold;"
        for child in list(tag.children):
            span.append(child)
        tag.replace_with(span)

    for tag in soup.find_all(["em", "i"]):
        span = soup.new_tag("span")
        span["style"] = "font-style: italic;"
        for child in list(tag.children):
            span.append(child)
        tag.replace_with(span)

    # 10. 图片补 max-width【修复基线：长图在手机上撑破屏幕】
    for img in soup.find_all("img"):
        img["style"] = styles["img"]
        if not img.get("alt"):
            img["alt"] = ""

    return soup


def resolve_images(soup, base_dir, styles, opts):
    """
    图片处理 —— starter kit 里标着 ⚠️ 基础的那块短板。

    公众号的图片规则和普通网页完全不同：
      - **外链图片会在保存时丢失**，必须先把图上传到公众号素材库；
      - **SVG 保存后会消失**，只有 PNG/JPG/GIF/WebP 这类位图能存活；
      - **本地路径粘贴时编辑器读不到**，因为文件在你自己硬盘上。

    所以这里把 markdown 里的本地图片读成 base64 data URI 直接嵌进 HTML ——
    粘贴时编辑器会把 data URI 当作"剪贴板里的图片"收下，图片就跟着正文进去了。
    （Word 输入里的图片本来就是 data URI，会被识别并跳过。）

    本函数**不静默处理**：找不到的图、SVG、外链都会收集成警告一次性报出来，
    因为"图片悄悄丢了"是公众号排版里最难靠肉眼发现的失败。
    """
    stats = {"embedded": 0, "already": 0, "external": 0, "missing": 0,
             "svg": 0, "captions": 0}
    warns = []
    base = Path(base_dir) if base_dir else Path.cwd()
    width = opts.get("image_width") or "100%"
    do_embed = opts.get("embed_images", True)
    do_captions = opts.get("captions", True)

    img_style = styles["img"]
    if width != "100%":
        img_style = img_style.replace("max-width: 100%",
                                      "max-width: {}".format(width))

    for idx, img in enumerate(list(soup.find_all("img")), 1):
        src = (img.get("src") or "").strip()

        if not src:
            stats["missing"] += 1
            warns.append("第 {} 张图没有 src，已跳过".format(idx))

        elif src.startswith("data:"):
            if src.lower().startswith("data:image/svg"):
                stats["svg"] += 1
                warns.append("第 {} 张图是 SVG base64 —— 公众号保存后会消失，"
                             "请换成 PNG".format(idx))
            else:
                stats["already"] += 1

        elif src.lower().startswith(("http://", "https://")):
            # 外链图片：能不能存活取决于公众号是否已把它转存到素材库
            stats["external"] += 1
            warns.append("第 {} 张图是外链（{}…）—— 公众号保存时可能丢失，"
                         "建议先把图上传到素材库".format(idx, src[:42]))

        elif src.lower().endswith(".svg"):
            stats["svg"] += 1
            warns.append("第 {} 张图是本地 SVG（{}）—— 公众号保存后会消失，"
                         "请先转成 PNG".format(idx, src))

        elif do_embed:
            local = unquote(src)
            cand = Path(local)
            if not cand.is_absolute():
                cand = base / local
            if cand.is_file() and cand.suffix.lower() in IMG_MIME:
                data = base64.b64encode(cand.read_bytes()).decode("ascii")
                img["src"] = "data:{};base64,{}".format(
                    IMG_MIME[cand.suffix.lower()], data)
                stats["embedded"] += 1
            elif cand.is_file():
                stats["svg"] += 1
                warns.append("第 {} 张图的格式 {} 公众号不保证支持（{}）".format(
                    idx, cand.suffix or "?", src))
            else:
                stats["missing"] += 1
                warns.append("第 {} 张图找不到本地文件：{}（保留原路径，"
                             "请确认图片位置）".format(idx, src))
        else:
            stats["missing"] += 1
            warns.append("第 {} 张图未嵌入（--no-embed-images）：{}".format(idx, src))

        img["style"] = img_style
        if not img.get("alt"):
            img["alt"] = ""

        # 图片说明：markdown 的 alt 文本本来就该显出来，
        # 放在图片下方居中小字，是公众号里最常用的图注排版。
        alt = (img.get("alt") or "").strip()
        if do_captions and alt:
            cap = soup.new_tag("p")
            cap["style"] = styles["img_caption"]
            cap.string = alt
            host = img.find_parent("p") or img
            host.insert_after(cap)
            stats["captions"] += 1

    return stats, warns


def apply_styles(soup, styles):
    """套用主题 inline CSS（保留已显式设置的样式）。"""
    style_map = {
        "h2": styles["h2"], "h3": styles["h3"], "p": styles["p"],
        "li": styles["li"], "ul": styles["ul"], "ol": styles["ol"],
        "table": styles["table"], "th": styles["th"], "td": styles["td"],
        "a": styles["a"], "img": styles["img"],
    }
    for tag_name, style in style_map.items():
        for el in soup.find_all(tag_name):
            if el.get("style"):
                continue
            el["style"] = style
    return soup


CJK = r"[\u4e00-\u9fff\u3400-\u4dbf]"
CJK_LEFT = re.compile("({})([A-Za-z0-9])".format(CJK))
CJK_RIGHT = re.compile("([A-Za-z0-9%])({})".format(CJK))


def apply_cjk_spacing(soup):
    """
    中文排版优化：在中文与半角英文/数字之间补一个空格。
    跳过代码（等宽字体）内的文本，避免破坏代码。
    """
    for node in list(soup.find_all(string=True)):
        parent = node.parent
        if parent is None or parent.name in ("script", "style"):
            continue
        skip = "monospace" in (parent.get("style") or "")
        if not skip:
            for anc in parent.parents:
                if isinstance(anc, Tag) and "monospace" in (anc.get("style") or ""):
                    skip = True
                    break
        if skip:
            continue
        text = str(node)
        new = CJK_LEFT.sub(r"\1 \2", text)
        new = CJK_RIGHT.sub(r"\1 \2", new)
        if new != text:
            node.replace_with(NavigableString(new))
    return soup


def clean_attributes(soup):
    """删掉 class/id/data-*，并 unwrap 非白名单标签。"""
    for tag in soup.find_all(True):
        for attr in list(tag.attrs.keys()):
            if attr not in ("style", "src", "alt", "href", "colspan", "rowspan"):
                del tag.attrs[attr]
        if tag.name not in ALLOWED_TAGS and tag.name not in (
                "html", "head", "body", "[document]"):
            tag.unwrap()
    # unwrap 之后可能出现空壳 p
    for p in soup.find_all("p"):
        if not p.get_text(strip=True) and not p.find("img"):
            p.decompose()
    return soup


# ---------------------------------------------------------------- 元数据自动补全


SUMMARY_MAX = 90
SUMMARY_MIN = 20
CALLOUT_PH_RE = re.compile(r"@@C4B_CALLOUT_\d+@@")
# `padding-left: 24px;` 这类样式声明。既不该出现在摘要里，
# 也是自检脚本判断"正文泄漏 CSS"用的同一套模式——保持一致。
CSS_LIKE_RE = re.compile(r"[a-z-]{3,}\s*:\s*[^;<>{}]{1,40};", re.I)


def derive_meta(raw_html, meta, opts):
    """
    从正文里自动补标题与摘要 —— 挑战 Level 4 要求「自动加标题摘要」。

    只在用户没写的时候补，**绝不覆盖已有值**（优先级：命令行 > 文件头 > 自动提取）。
    """
    if not opts.get("auto_meta", True):
        return raw_html, meta
    if meta.get("title") and meta.get("summary"):
        return raw_html, meta

    soup = BeautifulSoup(raw_html, "lxml")
    trimmed = False

    if not meta.get("title"):
        h1 = soup.find("h1")
        if h1 is not None:
            text = h1.get_text(" ", strip=True)
            if text:
                meta["title"] = text
                # 这一行已经用作头部大标题，正文里再出现一次就是重复
                h1.decompose()
                trimmed = True

    if not meta.get("summary"):
        meta["summary"] = _pick_summary(soup)
        # 自动提取的摘要，是从正文里**抄**出来的一段 —— 它本来就在正文里。
        # 再往头部渲染一遍，同一句话就会在文章里出现两次，读者看着像复读。
        # 所以自动来的只当元数据用；头部渲染留给「用户自己写了 summary」的场景。
        # （这条是跑 eval 才发现的：摘要块抢在了引用块前面，把引用块的断言带偏了）
        if meta["summary"]:
            meta["_summary_auto"] = True

    return (str(soup) if trimmed else raw_html), meta


def _pick_summary(soup):
    """
    挑一段适合当摘要的话。

    不是"第一个够长的段落"就完事——有两类段落必须跳过：
      · 含 <code> 的：读者点开看到的会是一段代码
      · 像 CSS 声明的：一篇讲样式的文章，摘要会变成 `padding-left: 24px;`，
        而且会被自检判成"正文泄漏 CSS"（这个坑是测试帮我抓到的）
    """
    for tag in soup.find_all(["p", "li"]):
        if tag.find("code") is not None:
            continue
        text = CALLOUT_PH_RE.sub("", tag.get_text(" ", strip=True)).strip()
        if len(text) < SUMMARY_MIN:
            continue
        if CSS_LIKE_RE.search(text):
            continue
        return (text[:SUMMARY_MAX] + "…") if len(text) > SUMMARY_MAX else text
    return ""


# ---------------------------------------------------------------- 结构增强


def build_header(meta):
    """文章头部：大标题 + 署名行。"""
    parts = []
    if meta.get("title"):
        parts.append('<p style="{}">{}</p>'.format(
            meta["_styles"]["meta_title"], html_mod.escape(meta["title"])))
    bits = [b for b in (meta.get("author"), meta.get("date")) if b]
    if bits:
        parts.append('<p style="{}">{}</p>'.format(
            meta["_styles"]["meta_byline"],
            html_mod.escape("  ·  ".join(bits))))
    # 只渲染「用户自己写的」摘要。自动提取的那份已经在正文里了，重复渲染=复读。
    if meta.get("summary") and not meta.get("_summary_auto"):
        parts.append('<p style="{}">{}</p>'.format(
            meta["_styles"]["summary"], html_mod.escape(meta["summary"])))
    return parts


def build_toc(soup, styles):
    """
    从 h2/h3 自动生成目录。
    公众号不支持锚点跳转，且嵌套 <p> 不可靠，所以渲染成
    单个带底色的 <p>，内部用 <br> 串联条目。
    """
    heads = [h for h in soup.find_all(["h2", "h3"]) if h.get_text(strip=True)]
    if len(heads) < 2:
        return []

    lines, h2_i = [], 0
    for h in heads:
        txt = html_mod.escape(h.get_text(strip=True))
        if h.name == "h2":
            h2_i += 1
            num, indent = "{:02d}".format(h2_i), ""
        else:
            # 【修复】一级目录是 "01" 这种编号，二级用 "—" 且需要视觉缩进。
            # 注意：整段目录是「单个 <p> + <br>」结构，没有独立的 <p> 可以挂
            # style，所以缩进只能用不换行空格实现。绝不能把 CSS 声明当文本拼进来
            # ——那会在页面上直接显示出 "padding-left: 24px;" 这样的样式代码。
            num, indent = "—", "&nbsp;&nbsp;&nbsp;&nbsp;"
        lines.append('{}<span style="{}">{}</span>&nbsp;&nbsp;{}'.format(
            indent, styles["toc_num"], num, txt))

    return ['<p style="{}">目 录</p>'.format(styles["toc_title"]),
            '<p style="{}">{}</p>'.format(styles["toc"], "<br>".join(lines))]


def build_footer(meta, styles):
    lines = []
    if meta.get("footer"):
        lines.append(html_mod.escape(meta["footer"]))
    else:
        author = meta.get("author") or "作者"
        lines.append("© {}　保留所有权利".format(html_mod.escape(author)))
    lines.append("本文由 wechat-publisher 技能自动排版生成")
    return ['<p style="{}">{}</p>'.format(styles["footer"], "<br>".join(lines))]


# ---------------------------------------------------------------- 主流程


def convert(input_path, output_path, opts):
    path = Path(input_path)
    if not path.exists():
        print("[!] 找不到文件: {}".format(input_path))
        return False

    ext = path.suffix.lower()
    if ext == ".md":
        raw_html, callouts, meta = read_markdown(input_path)
    elif ext == ".docx":
        raw_html, callouts, meta = read_docx(input_path)
    elif ext in (".html", ".htm"):
        raw_html, callouts, meta = path.read_text(
            encoding="utf-8", errors="replace"), [], {}
    else:
        print("[!] 不支持的格式: {}（支持 .md / .docx / .html）".format(ext))
        return False

    # 元数据优先级：命令行 > 文件头 > 默认
    theme_key = opts["theme"] or meta.get("theme") or "default"
    if theme_key not in THEMES:
        print("[!] 未知主题 {}，已回退 default。可选: {}".format(
            theme_key, ", ".join(THEME_ORDER)))
        theme_key = "default"
    styles = build_styles(theme_key, opts.get("accent"))
    divider = THEMES[theme_key]["divider"]

    for key in ("title", "author", "date", "summary", "footer"):
        if opts.get(key):
            meta[key] = opts[key]
        elif meta.get(key) is None:
            meta[key] = ""

    # 自动补全标题与摘要（挑战 Level 4 要求「自动加标题摘要」）。
    # 只在用户没写的时候补，写了就一定以用户的为准。
    _had_title, _had_summary = bool(meta["title"]), bool(meta["summary"])
    raw_html, meta = derive_meta(raw_html, meta, opts)
    auto_filled = []
    if not _had_title and meta["title"]:
        auto_filled.append("标题")
    if not _had_summary and meta["summary"]:
        auto_filled.append("摘要")

    toc_on = opts["toc"] if opts["toc"] is not None else \
        (str(meta.get("toc", "")).lower() in ("true", "1", "yes"))
    cjk_on = opts["cjk"] if opts["cjk"] is not None else \
        (str(meta.get("cjk_spacing", "true")).lower() not in ("false", "0", "no"))

    if not opts["quiet"]:
        print("[1/7] 读取 {} ({})".format(path.name, ext))

    if not raw_html.strip():
        print("[!] 源文件没有可转换的内容，已中止（不生成空 HTML）")
        return False

    meta["_styles"] = styles
    if not opts["quiet"]:
        print("[2/7] 清洗违规标签（script/style/iframe/h1/div）")
    soup = sanitize(raw_html, callouts, styles, divider)

    img_stats, img_warns = resolve_images(soup, path.parent, styles, opts)
    if not opts["quiet"]:
        print("[3/7] 处理图片（嵌入 {} / 已有 {} / 外链 {} / 缺失 {} / SVG {}）".format(
            img_stats["embedded"], img_stats["already"], img_stats["external"],
            img_stats["missing"], img_stats["svg"]))

    if not opts["quiet"]:
        print("[4/7] 套用主题样式：{}".format(THEMES[theme_key]["label"]))
    soup = apply_styles(soup, styles)

    if cjk_on:
        if not opts["quiet"]:
            print("[5/7] 中文排版优化（中英文间距）")
        soup = apply_cjk_spacing(soup)
    else:
        if not opts["quiet"]:
            print("[5/7] 跳过中文排版优化")

    if not opts["quiet"]:
        print("[6/7] 整理属性（去 class/id，过滤非白名单 CSS）")
    soup = clean_attributes(soup)

    for tag in soup.find_all(True):
        if tag.get("style"):
            filtered = filter_css(tag["style"])
            if filtered:
                tag["style"] = filtered
            else:
                del tag["style"]

    body = soup.find("body")
    content = "\n".join(str(c) for c in body.children if str(c).strip()) \
        if body else str(soup)

    head_parts = build_header(meta)
    toc_parts = build_toc(BeautifulSoup(content, "lxml"), styles) if toc_on else []
    foot_parts = build_footer(meta, styles)

    final = "\n".join(head_parts + toc_parts + [content] + foot_parts)

    out_html = (
        '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<title>{}</title>\n</head>\n'
        '<body style="max-width: 640px; margin: 0 auto; padding: 24px 18px; '
        'font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', '
        '\'PingFang SC\', \'Hiragino Sans GB\', \'Microsoft YaHei\', sans-serif; '
        'background-color: #ffffff; color: {};">\n{}\n</body>\n</html>'
    ).format(html_mod.escape(meta.get("title") or "公众号文章预览"),
             THEMES[theme_key]["text"], final)

    Path(output_path).write_text(out_html, encoding="utf-8")

    if not opts["quiet"]:
        print("[7/7] 写出 {}".format(output_path))

    size_kb = os.path.getsize(output_path) / 1024
    issues = self_check(out_html)
    print("\n[OK] {} 已生成（{:.1f} KB，主题：{}）".format(
        output_path, size_kb, THEMES[theme_key]["label"]))
    if callouts:
        print("     已渲染 {} 个 callout 高亮框".format(len(callouts)))
    if auto_filled:
        print("     已自动补全：{}（从正文提取，原文没有写）".format(
            " / ".join(auto_filled)))
    if toc_parts:
        print("     已生成自动目录")
    if img_stats["embedded"] or img_stats["already"] or img_stats["captions"]:
        print("     图片：嵌入 {} 张（base64）/ 原有 {} 张 / 图注 {} 条".format(
            img_stats["embedded"], img_stats["already"], img_stats["captions"]))
    for w in img_warns:
        print("     [图片] " + w)
    if issues:
        print("     [警告] 自检发现 {} 个问题：".format(len(issues)))
        for it in issues:
            print("       - " + it)
    else:
        print("     自检通过：无违规标签 / 无 class / 无 JS")
    return True


def self_check(html):
    """转换后立刻自检（details 见 scripts/check_wechat_html.py）。"""
    problems = []
    for tag in ("script", "iframe", "style", "<div", "<h1", "class=", "onclick"):
        if tag in ("<div", "<h1", "class="):
            if tag.lower() in html.lower():
                problems.append("残留违规内容: {}".format(tag))
        elif "<{}".format(tag) in html.lower():
            problems.append("残留违规标签: <{}>".format(tag))
    if re.search(r"<svg", html, re.I):
        problems.append("残留 <svg>（公众号保存后会消失）")
    if re.search(r'<img[^>]+src="data:image/svg', html, re.I):
        problems.append("存在 SVG base64 图片（保存后会丢失，请换 PNG）")
    for m in re.finditer(r'<img[^>]*\ssrc="([^"]*)"', html, re.I):
        src = m.group(1).strip()
        if not src.startswith("data:") and not src.lower().startswith("http"):
            problems.append(
                "图片未嵌入（src={}），粘贴到公众号后会变成空框".format(src[:48]))
    if re.search(r'<img[^>]*>(?!.*max-width)', html) and "max-width" not in html:
        problems.append("图片缺少 max-width")
    return problems


def main():
    ap = argparse.ArgumentParser(
        description="Markdown / Word → 公众号 HTML（增强版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="主题可选：" + " / ".join(
            "{}={}".format(k, THEMES[k]["label"]) for k in THEME_ORDER))
    ap.add_argument("input", nargs="?", help="输入文件（.md/.docx/.html）")
    ap.add_argument("output", nargs="?", help="输出 HTML（默认同名 .html）")
    ap.add_argument("--theme", choices=THEME_ORDER, help="配色主题")
    ap.add_argument("--accent", help="覆盖主题主色，如 #1a73e8")
    ap.add_argument("--toc", dest="toc", action="store_true", default=None,
                    help="生成自动目录")
    ap.add_argument("--no-toc", dest="toc", action="store_false",
                    help="不生成目录")
    ap.add_argument("--no-cjk-spacing", dest="cjk", action="store_false",
                    default=None, help="关闭中英文自动加空格")
    ap.add_argument("--title"), ap.add_argument("--author")
    ap.add_argument("--date"), ap.add_argument("--summary")
    ap.add_argument("--footer")
    ap.add_argument("--batch", help="批量转换目录下所有 .md/.docx")
    ap.add_argument("--no-embed-images", dest="embed_images",
                    action="store_false", default=True,
                    help="不把本地图片嵌成 base64，只保留原路径")
    ap.add_argument("--no-captions", dest="captions",
                    action="store_false", default=True,
                    help="不把图片的 alt 文本渲染成图注")
    ap.add_argument("--image-width", default="100%",
                    help="图片最大宽度，默认 100%%，如 80%% / 420px")
    ap.add_argument("--no-auto-meta", dest="auto_meta", action="store_false",
                    default=True,
                    help="不做标题/摘要的自动补全（默认会从正文提取）")
    ap.add_argument("--list-themes", action="store_true", help="列出所有主题")
    ap.add_argument("--quiet", action="store_true", help="减少输出")

    args = ap.parse_args()

    if args.list_themes:
        for k in THEME_ORDER:
            print("  {:10s} {}".format(k, THEMES[k]["label"]))
        return 0

    opts = {"theme": args.theme, "accent": args.accent, "toc": args.toc,
            "cjk": args.cjk, "title": args.title, "author": args.author,
            "date": args.date, "summary": args.summary, "footer": args.footer,
            "embed_images": args.embed_images, "captions": args.captions,
            "image_width": args.image_width, "auto_meta": args.auto_meta,
            "quiet": args.quiet}

    if args.batch:
        folder = Path(args.batch)
        if not folder.is_dir():
            print("[!] 不是目录: {}".format(args.batch))
            return 1
        files = sorted([p for p in folder.iterdir()
                        if p.suffix.lower() in (".md", ".docx")])
        if not files:
            print("[!] 目录里没有 .md / .docx 文件")
            return 1
        outdir = folder / "wechat_output"
        outdir.mkdir(exist_ok=True)
        ok = 0
        for f in files:
            print("\n=== {} ===".format(f.name))
            if convert(str(f), str(outdir / (f.stem + ".html")), opts):
                ok += 1
        print("\n批量完成：{}/{} 成功 → {}".format(ok, len(files), outdir))
        return 0 if ok == len(files) else 1

    if not args.input:
        ap.print_help()
        return 1

    out = args.output or str(Path(args.input).with_suffix(".html"))
    return 0 if convert(args.input, out, opts) else 1


if __name__ == "__main__":
    sys.exit(main())
