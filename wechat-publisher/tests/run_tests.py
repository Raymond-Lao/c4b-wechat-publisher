#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wechat-publisher 自动化测试（eval）

用法：
    python tests/run_tests.py

覆盖 18 个用例：6 个基线缺陷修复 + 3 个自身缺陷回归
+ 9 个新增能力（含批量转换、极端输入矩阵、图片处理、一稿多投）。
每个用例构造真实输入 → 跑转换 → 断言输出，全部通过返回 0。
"""

import base64
import html as html_lib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
CONVERT = ROOT / "scripts" / "convert_to_wechat.py"
CHECKER = ROOT / "scripts" / "check_wechat_html.py"
EXPORT = ROOT / "scripts" / "export_formats.py"
OUTLINE = ROOT / "scripts" / "outline_to_draft.py"
PY = sys.executable

# 1×1 透明 PNG，用来测"本地图片能否被嵌进 HTML"（不依赖 PIL）
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8"
    "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

results = []


def visible_text(html):
    """剥掉标签和属性，只留读者真正看到的文字。"""
    return html_lib.unescape(re.sub(r"<[^>]*>", "", html))


def run_convert(src_text, name="case.md", args=None):
    """把内容写成临时文件，跑转换，返回输出 HTML。"""
    tmp = Path(tempfile.mkdtemp(prefix="c4b_"))
    src = tmp / name
    src.write_text(src_text, encoding="utf-8")
    out = tmp / "out.html"
    cmd = [PY, str(CONVERT), str(src), str(out), "--quiet"] + (args or [])
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    result = {"ok": proc.returncode == 0, "stdout": proc.stdout,
              "stderr": proc.stderr, "html": "", "dir": tmp}
    if out.exists():
        result["html"] = out.read_text(encoding="utf-8")
    return result


def case(title, fn):
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, "抛出异常: {}: {}".format(type(exc).__name__, exc)
    results.append((title, ok, detail))
    print("  {} {}\n      {}".format("[PASS]" if ok else "[FAIL]", title, detail))


# ---------------------------------------------------------------- 修复类用例

def t1_h1_div_script_removed():
    # 这里带一段 front matter：否则正文里的 "# 一级标题" 会被「自动标题」
    # 提升成文章大标题并从正文移除，这条用例就测不到 h1 降级了。
    # （无 front matter 时的行为单独由 新增11 覆盖。）
    r = run_convert(
        "---\ntitle: 已有标题\n---\n\n"
        "# 一级标题\n\n正文\n\n<div>div内容</div>\n\n"
        "<script>alert(1)</script>\n\n<style>p{color:red}</style>\n")
    if not r["ok"]:
        return False, "转换失败: " + r["stderr"][:200]
    h = r["html"]
    bad = [t for t in ("<script", "<style>", "<div", "<h1")
           if t in h.lower()]
    if bad:
        return False, "残留违规标签: {}".format(bad)
    if "<h2" not in h:
        return False, "h1 未被降级为 h2"
    return True, "script/style/div/h1 已清理，h1 正确降级为 h2"


def t2_hr_preserved():
    r = run_convert("段落一\n\n---\n\n段落二\n")
    if "<hr" in r["html"] and "· · ·" not in r["html"]:
        return False, "分隔符未转换"
    if "· · ·" in r["html"] or "— — —" in r["html"]:
        return True, "分隔线被保留为可见分隔符（基线此处会整条消失）"
    return False, "分隔线丢失（复现了基线缺陷 1）"


def t3_blockquote_keeps_br():
    r = run_convert("> 第一行\n> 第二行带 **加粗**\n")
    h = r["html"]
    m = re.search(r'<p style="[^"]*border-left[^"]*">(.*?)</p>', h, re.S)
    if not m:
        return False, "没有找到引用块输出"
    block = m.group(1)
    if "<br" not in block:
        return False, "引用块内没有换行符（复现了基线缺陷 2）"
    if "font-weight: bold" not in block:
        return False, "引用块内的加粗丢失"
    return True, "引用块保留换行，且内部加粗完好"


def t4_img_max_width():
    r = run_convert("![图](https://example.com/a.png)\n")
    imgs = re.findall(r"<img[^>]*>", r["html"])
    if not imgs:
        return False, "没有输出 img 标签"
    if "max-width" not in imgs[0]:
        return False, "img 缺少 max-width（复现了基线缺陷 3）"
    return True, "图片已注入 max-width:100%（防撑破手机屏幕）"


def t5_css_whitelist():
    r = run_convert('<p style="position:fixed;color:red;float:left;">测试</p>\n')
    h = r["html"]
    if "position" in h or "float" in h:
        return False, "非白名单 CSS 未被过滤（ALLOWED_CSS 仍是死代码）"
    if "color: red" not in h and "color:red" not in h:
        return False, "白名单内的 color 被误删"
    return True, "position/float 已过滤，color 保留 —— ALLOWED_CSS 真正生效"


def t6_code_block_newlines():
    r = run_convert("```\nline1\nline2\nline3\n```\n")
    m = re.search(r'<p style="[^"]*monospace[^"]*">(.*?)</p>', r["html"], re.S)
    if not m:
        return False, "未找到代码块"
    block = m.group(1)
    if block.count("<br") < 2:
        return False, "代码块换行丢失（复现了基线缺陷 5）"
    if "white-space: pre-wrap" not in m.group(0):
        return False, "代码块缺少 white-space: pre-wrap"
    return True, "代码块用 br 保留换行，并带 pre-wrap"


def t13_toc_no_css_leak():
    """
    回归用例：目录拼接时不得把 CSS 声明当文字输出。

    背景：目录是「单个 <p> + <br>」结构，没有独立 <p> 可以挂 style，
    早期实现用 pad 变量拼缩进，结果 "padding-left: 24px; " 直接显示在了
    文章正文里。这类问题脚本不报错、长文里肉眼也难发现，必须靠测试兜住。
    """
    src = ("## 第一节\n\n内容一\n\n### 小节甲\n\n内容二\n\n"
           "## 第二节\n\n内容三\n\n### 小节乙\n\n内容四\n")
    r = run_convert(src, args=["--toc"])
    h = r["html"]
    if "目 录" not in h:
        return False, "未生成目录"

    text = visible_text(h)
    m = re.search(r"[a-z-]{3,}\s*:\s*[^;<>{}]{1,40};", text, re.I)
    if m:
        return False, "目录把 CSS 声明当可见文字输出了：{!r}".format(m.group(0).strip())
    if "padding-left" in text:
        return False, "可见文字里出现了裸的 padding-left"

    toc_text = text.split("目 录", 1)[1]
    if "—" not in toc_text:
        return False, "二级目录条目（—— 前缀）缺失"
    if "01" not in toc_text or "02" not in toc_text:
        return False, "一级目录编号缺失"

    # 反向检查：行内代码里正常引用的 CSS 示例，不能被自检误判成"泄漏"，
    # 否则一篇讲 CSS 的文章永远过不了自检。
    r2 = run_convert("正文里引用了 `padding-left: 24px;` 这样一个例子。\n")
    chk = subprocess.run([PY, str(CHECKER), str(Path(r2["dir"]) / "out.html")],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if chk.returncode != 0:
        return False, "行内代码里的 CSS 示例被误判为泄漏：{}".format(
            chk.stdout.strip()[-160:])
    return True, "目录无 CSS 泄漏，二级条目用不换行空格缩进；行内代码未被误判"


def t14_callout_list_not_lost():
    """
    回归用例：callout 正文里的列表不能被静默丢弃。

    背景：callout 最终渲染成**单个 <p>**，而 HTML 规则不允许 <p> 里嵌
    <ol>/<ul>。早期实现里解析器把列表甩到 <p> 外面，调用方又只取了那个
    <p>，于是整个列表连同文字凭空消失，而脚本不报错、自检还显示"通过"。
    这是整个项目里最难发现的一类问题：**输出错了，但不报错。**
    """
    src = ("## 标题\n\n正文。\n\n"
           "::: practice 你也想试的话\n"
           "1. 第一问？\n2. 第二问？\n3. 第三问？\n"
           ":::\n\n"
           "::: note 要点\n"
           "- 第四问？\n- 第五问？\n"
           ":::\n\n"
           "结尾。\n")
    r = run_convert(src)
    if not r["ok"]:
        return False, "转换失败: " + r["stderr"][:200]
    h = r["html"]

    missing = [x for x in ("第一问？", "第二问？", "第三问？", "第四问？", "第五问？")
               if x not in h]
    if missing:
        return False, "callout 里的列表内容被丢弃: {}".format(missing)
    if "<ol" in h or "<ul" in h:
        return False, "callout 里残留块级列表标签（会被解析器甩出 <p> 后丢失）"
    if "1. " not in h:
        return False, "有序列表未压平成 '1. 文字' 形式"
    if "• " not in h:
        return False, "无序列表未压平成 '• 文字' 形式"
    return True, "有序/无序列表都完整保留，并压平为行内文本"


def t15_callout_title_inline_md():
    """
    回归用例：callout 标题里的 markdown 内联格式必须解析，星号不能裸露。

    背景：正文走了 markdown 解析，唯独**标题这一行**只做了 escape，
    于是 `::: tip 标题带**加粗**` 会把 `**` 原样印在文章里。
    星号裸露在公众号排版中非常显眼，是"肉眼可见但不报错"的瑕疵。

    断言方式：把标签全部剥掉、只看可见文字里有没有裸星号 ——
    直接对原始 HTML 做正则会被 style 属性干扰。
    """
    src = "::: tip 标题带**加粗**和*斜体*\n正文内容。\n:::\n"
    r = run_convert(src)
    if not r["ok"]:
        return False, "转换失败: " + r["stderr"][:200]
    h = r["html"]

    if "**" in h:
        return False, "callout 标题里的 markdown 星号裸露在输出中"
    # 剥掉所有标签后，可见文字里不应出现成对的强调符号
    visible = BeautifulSoup(h, "lxml").get_text()
    if "*" in visible:
        return False, "可见文字里残留星号：{}".format(
            visible[visible.find("*") - 20:visible.find("*") + 20])
    # 标题里的加粗应真的生效（strong → span 之后）
    i = h.find("标题带")
    if i < 0:
        return False, "标题文字丢失"
    seg = h[i:i + 300]
    if "font-weight: bold" not in seg:
        return False, "标题里的加粗未转换成带样式的 span"
    return True, "callout 标题的内联 markdown 正确解析，无星号裸露"


def t16_extreme_input_matrix():
    """
    极端输入矩阵（10 组）—— 技能的成色在边界上，不在正常流程。

    这 10 组是定稿自测时人工构造的（完整结果见 `liruixiang_C4B_自测自评.md` 2.1 节），
    现在固化成可重跑的门禁。**自测发现的问题如果不固化，就只是一次性验证** ——
    下次改代码时，这 10 组场景就没人替你重跑了。

    断言分三类：
      1. 该中止的必须中止（空输入不能产出空 HTML —— 产出了就是"假成功"）
      2. 该通过的不能崩
      3. 该通过的不能丢内容：输入里的关键字符串必须出现在**可见文字**里

    第 3 条为什么强调"可见文字"：直接对原始 HTML 做正则会命中 style 属性，
    而且 `<` 会被转义成 `&lt;`。剥掉标签再比对才可靠。
    """
    long_src = ("---\ntitle: 超长\n---\n\n"
                + "\n\n".join("## 第 {} 节\n\n这是第 {} 节的正文。".format(i, i)
                             for i in range(1, 121)))

    # (场景, 源文本, 期望, 可见文字里必须出现, HTML 里绝不能出现)
    cases = [
        ("空文件", "", "fail", [], []),
        ("只有 front matter", "---\ntitle: 无正文\nauthor: A\n---\n", "fail", [], []),
        ("只有标题", "# 只有标题\n", "ok", ["只有标题"], []),
        ("无 front matter 的正文", "## 小节\n\n一段正文。\n", "ok", ["小节", "一段正文"], []),
        ("混入违规标签与事件属性",
         '<div onclick="evil()">危险 div 内容</div>\n\n<script>alert(1)</script>\n',
         "ok", ["危险 div 内容"], ["onclick", "<script", "<div"]),
        ("emoji 与特殊符号",
         "## 特殊字符\n\nemoji：🎉🚀 100%效率 ¥199 → 箭头\n",
         "ok", ["🎉", "🚀", "100%", "¥199", "→"], []),
        ("callout 内嵌有序列表",
         "::: practice 标题\n1. 第一问？\n2. 第二问？\n:::\n",
         "ok", ["第一问？", "第二问？"], ["<ol"]),
        ("未闭合的 callout",
         "::: warn 忘了收尾\n这段内容没有结束标记。\n",
         "ok", ["没有结束标记"], []),
        ("代码块里的 HTML 与尖括号",
         '```python\nhtml = "<p class=\\"x\\">t</p>"\nif a < b and c > d: pass\n```\n',
         "ok", ['"<p class=', "c > d"], []),
        ("超长文章（120 节）", long_src, "ok", ["第 1 节", "第 120 节"], []),
    ]

    failed = []
    for name, src, expect, must_have, must_not in cases:
        r = run_convert(src)
        if expect == "fail":
            if r["ok"]:
                failed.append("{}：应当中止却成功了（会产出空 HTML）".format(name))
            continue
        if not r["ok"]:
            failed.append("{}：转换失败 {}".format(name, r["stderr"][:70]))
            continue
        text = BeautifulSoup(r["html"], "lxml").get_text()
        missing = [k for k in must_have if k not in text]
        if missing:
            failed.append("{}：内容丢失 {}".format(name, missing))
        leaked = [k for k in must_not if k in r["html"]]
        if leaked:
            failed.append("{}：不该出现的东西出现了 {}".format(name, leaked))

    if failed:
        return False, "；".join(failed)
    return True, "10 组极端输入全部符合预期（2 组正确中止、8 组内容完整且无违规残留）"


# ---------------------------------------------------------------- 新增能力用例
def t7_theme_system():
    outs = {}
    for theme in ("default", "blue", "warm", "minimal", "elegant"):
        r = run_convert("## 标题\n\n正文\n", args=["--theme", theme])
        if not r["ok"]:
            return False, "主题 {} 转换失败".format(theme)
        outs[theme] = r["html"]

    colors = {}
    for theme, h in outs.items():
        m = re.search(r"<h2 style=\"([^\"]*)\"", h)
        if not m:
            return False, "主题 {} 的输出里找不到 h2".format(theme)
        c = re.search(r"color:\s*(#[0-9a-f]{6})", m.group(1), re.I)
        if not c:
            return False, "主题 {} 的 h2 没有颜色".format(theme)
        colors[theme] = c.group(1).lower()

    if len(set(colors.values())) < 3:
        return False, "5 套主题的 h2 主色只有 {} 种: {}".format(
            len(set(colors.values())), colors)
    if colors["default"] == colors["blue"]:
        return False, "default 与 blue 主题主色相同，主题未真正生效"
    return True, "5 套主题各自生效，h2 主色分别为 " + " / ".join(
        "{}={}".format(k, v) for k, v in colors.items())


def t8_callout():
    src = ("::: note 知识点\n这是**重点**内容。\n:::\n\n"
           "::: warn 注意\n小心踩坑。\n:::\n")
    r = run_convert(src)
    h = r["html"]
    if "📘 知识点" not in h or "⚠️ 注意" not in h:
        return False, "callout 标题未渲染"
    if h.count("border-left: 4px solid") < 2:
        return False, "callout 缺少左侧竖线样式"
    if 'font-weight: bold;">重点' not in h and "font-weight: bold;\">重点" not in h:
        return False, "callout 内的 markdown 加粗未生效"
    return True, "note/warn 两种 callout 渲染正确，内部 markdown 生效"


def t9_toc():
    src = "## 第一节\n\n内容\n\n## 第二节\n\n内容\n\n### 小节\n\n内容\n"
    r = run_convert(src, args=["--toc"])
    h = r["html"]
    if "目 录" not in h:
        return False, "未生成目录标题"
    if ">01<" not in h or ">02<" not in h:
        return False, "目录缺少编号"
    if "第一节" not in h.split("目 录")[1][:600]:
        return False, "目录里没有列出章节"
    # 标题不足 2 个时不生成目录
    r2 = run_convert("## 只有一个标题\n\n内容\n", args=["--toc"])
    if "目 录" in r2["html"]:
        return False, "标题不足 2 个时仍生成了目录"
    return True, "目录生成正确，且标题不足时自动跳过"


def t10_metadata_footer():
    src = "---\ntitle: 我的标题\nauthor: 李瑞翔\ndate: 2026-10-06\n" \
          "summary: 这是一段摘要。\nfooter: 版权所有。\n---\n\n正文\n"
    r = run_convert(src)
    h = r["html"]
    for token in ("我的标题", "李瑞翔", "2026-10-06", "这是一段摘要。", "版权所有。"):
        if token not in h:
            return False, "缺少元数据: {}".format(token)
    if "<title>我的标题</title>" not in h:
        return False, "页面 title 未同步"
    return True, "标题/作者/日期/摘要/页脚全部渲染，front matter 解析正常"


def t11_cjk_spacing():
    r = run_convert("我用 AI 写了一个 C4B 技能，2026 年发布。\n")
    h = r["html"]
    if "我用 AI 写了一个 C4B 技能" not in h:
        return False, "中英文之间未加空格（原文本身已带空格，测试无效）"
    r2 = run_convert("我用AI写了一个技能\n")
    if "我用 AI 写了一个技能" not in r2["html"]:
        return False, "中英文之间未自动补空格"
    # 代码块内不应被加空格
    r3 = run_convert("```\nfor i in range(3):\n```\n")
    if "range(3)" not in r3["html"]:
        return False, "代码块被中文排版规则破坏"
    return True, "中文与英文/数字间自动补空格，代码块内不受影响"


def t12_batch_and_edge_cases():
    tmp = Path(tempfile.mkdtemp(prefix="c4b_batch_"))
    try:
        (tmp / "a.md").write_text("## A\n\n内容\n", encoding="utf-8")
        (tmp / "b.md").write_text("## B\n\n内容\n", encoding="utf-8")
        proc = subprocess.run(
            [PY, str(CONVERT), "--batch", str(tmp), "--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        outdir = tmp / "wechat_output"
        made = sorted(p.name for p in outdir.glob("*.html")) if outdir.exists() else []
        if len(made) != 2:
            return False, "批量转换失败，只产出 {}".format(made)

        # 空文件
        empty = run_convert("   \n\n")
        if empty["ok"]:
            return False, "空文件应当报错中止，实际却成功"

        # 未知主题回退
        bad = run_convert("## 标题\n\n正文\n", args=["--theme", "nope"])
        if bad["ok"]:
            return False, "未知主题应当被拒绝（argparse choices），实际通过了"

        # 自检脚本对干净输出返回 0
        clean = run_convert("## 标题\n\n正文\n")
        chk = subprocess.run([PY, str(CHECKER), str(Path(clean["dir"]) / "out.html")],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if chk.returncode != 0:
            return False, "自检脚本对干净输出返回了非 0：{}".format(chk.stdout[-200:])
        return True, "批量转换 2/2 成功；空文件正确报错；未知主题被拒绝；自检通过"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t17_image_handling():
    """新增能力：本地图片嵌入 + 图注 + 外链/缺失/SVG 显式告警。"""
    tmp = Path(tempfile.mkdtemp(prefix="c4b_img_"))
    try:
        (tmp / "pic.png").write_bytes(TINY_PNG)
        (tmp / "vec.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>',
            encoding="utf-8")
        (tmp / "a.md").write_text(
            "## 图片一节\n\n"
            "![本地图注文字](pic.png)\n\n"
            "![外链图](https://example.com/a.png)\n\n"
            "![缺失图](missing.png)\n\n"
            "![矢量图](vec.svg)\n", encoding="utf-8")
        out = tmp / "out.html"
        proc = subprocess.run(
            [PY, str(CONVERT), str(tmp / "a.md"), str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0 or not out.exists():
            return False, "转换失败: " + (proc.stderr or proc.stdout)[:200]

        h = out.read_text(encoding="utf-8")
        imgs = re.findall(r"<img[^>]*>", h)
        if len(imgs) != 4:
            return False, "图片数量异常：{}".format(len(imgs))
        if "data:image/png;base64" not in imgs[0]:
            return False, "本地 PNG 没被嵌成 base64，粘贴后会是空框"
        if "本地图注文字" not in visible_text(h):
            return False, "图片 alt 没有渲染成图注"

        # 三类风险都要有显式告警 —— 绝不允许静默
        for key, label in (("外链", "外链图"), ("找不到本地文件", "缺失图"),
                           ("SVG", "SVG 图")):
            if key not in proc.stdout:
                return False, "{}没有告警，属于静默处理".format(label)

        # 自检脚本要把"没嵌入的图"标出来
        chk = subprocess.run([PY, str(CHECKER), str(out)],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if "没嵌入" not in chk.stdout:
            return False, "自检没有标出未嵌入的图片"

        # 开关必须真的能关掉
        out2 = tmp / "out2.html"
        subprocess.run(
            [PY, str(CONVERT), str(tmp / "a.md"), str(out2),
             "--no-embed-images", "--no-captions", "--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        h2 = out2.read_text(encoding="utf-8")
        if "data:image/png;base64" in h2:
            return False, "--no-embed-images 没生效"
        if "本地图注文字" in visible_text(h2):
            return False, "--no-captions 没生效"
        return True, ("本地图片嵌入 base64、alt 渲染成图注；外链/缺失/SVG "
                      "三类风险均显式告警；--no-embed-images / --no-captions 生效")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t18_multi_format_and_templates():
    """新增能力：一稿多投（公众号/知乎/纯文本）+ 体裁模板。"""
    tmp = Path(tempfile.mkdtemp(prefix="c4b_fmt_"))
    try:
        src = tmp / "art.md"
        src.write_text(
            "---\ntitle: 三格式测试\nauthor: 李瑞翔\ndate: 2026-10-06\n"
            "summary: 一句话摘要\n---\n\n"
            "## 小标题\n\n正文里有 **加粗** 和 `行内代码`。\n\n"
            "::: tip 提示标题\n框里的第一行\n\n框里的第二行\n:::\n\n"
            "- 列表项一\n- 列表项二\n", encoding="utf-8")

        proc = subprocess.run(
            [PY, str(EXPORT), str(src), "--outdir", str(tmp / "dist"), "--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            return False, "导出失败: " + (proc.stderr or proc.stdout)[:200]

        dist = tmp / "dist"
        wechat = dist / "art.wechat.html"
        zhihu = dist / "art.zhihu.md"
        plain = dist / "art.plain.txt"
        for p in (wechat, zhihu, plain):
            if not p.is_file():
                return False, "缺少输出: {}".format(p.name)

        hw = wechat.read_text(encoding="utf-8")
        if "<h1" in hw.lower() or "<div" in hw.lower():
            return False, "公众号版残留违规标签"
        if "三格式测试" not in hw:
            return False, "公众号版丢了标题"

        z = zhihu.read_text(encoding="utf-8")
        if "> **提示标题**" not in z:
            return False, "知乎版没有把 callout 转成引用块"
        if ":::" in z:
            return False, "知乎版残留 callout 定界符 :::"
        if "**加粗**" not in z:
            return False, "知乎版丢了 markdown 加粗"

        t = plain.read_text(encoding="utf-8")
        for bad in ("**", ":::", "##", "`"):
            if bad in t:
                return False, "纯文本版残留标记: {}".format(bad)
        if "【提示标题】" not in t:
            return False, "纯文本版没有把 callout 渲染成【标题】"
        if "加粗" not in t:
            return False, "纯文本版丢了正文"

        # --formats 只出指定格式
        subprocess.run([PY, str(EXPORT), str(src), "--outdir", str(tmp / "d2"),
                        "--formats", "plain", "--quiet"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
        made = sorted(p.name for p in (tmp / "d2").glob("*"))
        if made != ["art.plain.txt"]:
            return False, "--formats 过滤失效，实际产出 {}".format(made)

        # 体裁模板
        lt = subprocess.run([PY, str(EXPORT), "--list-templates"],
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        if lt.returncode != 0 or lt.stdout.count("——") < 4:
            return False, "模板列表不完整: {}".format(lt.stdout[-160:])

        dst = tmp / "my.md"
        n1 = subprocess.run([PY, str(EXPORT), "--new", "retrospective", str(dst)],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
        if n1.returncode != 0 or not dst.is_file():
            return False, "按模板新建失败: {}".format(n1.stdout[-160:])
        if "复盘" not in dst.read_text(encoding="utf-8"):
            return False, "新建出的文件内容不像复盘模板"
        n2 = subprocess.run([PY, str(EXPORT), "--new", "retrospective", str(dst)],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
        if n2.returncode == 0:
            return False, "目标已存在时应当拒绝覆盖，实际却成功"
        return True, ("三格式导出正确（callout 分别转引用块/【标题】）；"
                      "--formats 过滤生效；4 个体裁模板可用且不覆盖已有文件")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t19_outline_to_draft():
    """新增能力：从大纲生成初稿（挑战 Level 4「写作辅助集成」）。"""
    tmp = Path(tempfile.mkdtemp(prefix="c4b_outline_"))
    try:
        ol = tmp / "outline.md"
        ol.write_text(
            "# 用大纲生成初稿\n\n"
            "## 一、为什么\n- 手动列提纲太慢\n- 结构容易漏\n\n"
            "## 二、怎么做\n- 先跑通\n- 再补能力\n\n"
            "## 结语\n", encoding="utf-8")

        dr = tmp / "draft.md"
        p1 = subprocess.run([PY, str(OUTLINE), str(ol), str(dr), "--author", "李瑞翔"],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
        if p1.returncode != 0 or not dr.is_file():
            return False, "生成失败: {}".format((p1.stderr or p1.stdout)[-200:])
        d = dr.read_text(encoding="utf-8")

        for need in ("---", "title: 用大纲生成初稿", "author: 李瑞翔"):
            if need not in d:
                return False, "初稿缺少 {}".format(need)
        for need in ("## 一、为什么", "## 二、怎么做", "手动列提纲太慢", "先跑通"):
            if need not in d:
                return False, "初稿丢了 {}".format(need)
        if "<!--" not in d:
            return False, "没有插入写作提示注释"
        if d.count("## 结语") != 1:
            return False, "结语章节重复或缺失"
        # 提示里不该把序号也念一遍（"本节要回答的问题：一、为什么"）
        if "本节要回答的问题：一、" in d:
            return False, "写作提示没去掉标题的序号前缀"

        # --sections：要点提升为小节标题
        dr2 = tmp / "draft2.md"
        subprocess.run([PY, str(OUTLINE), str(ol), str(dr2), "--sections"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
        d2 = dr2.read_text(encoding="utf-8")
        if "### 手动列提纲太慢" not in d2:
            return False, "--sections 没把要点提升为小节"
        if "### 手动列提纲太慢" in d:
            return False, "默认模式不该生成小节标题"

        # --no-tips：不插提示
        dr3 = tmp / "draft3.md"
        subprocess.run([PY, str(OUTLINE), str(ol), str(dr3), "--no-tips"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
        if "<!--" in dr3.read_text(encoding="utf-8"):
            return False, "--no-tips 仍然插入了提示注释"

        # 不覆盖已有文件
        again = subprocess.run([PY, str(OUTLINE), str(ol), str(dr)],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
        if again.returncode == 0:
            return False, "目标已存在时应当拒绝覆盖"

        # 空大纲要报错，而不是产出一个空文件
        empty = tmp / "empty.md"
        empty.write_text("", encoding="utf-8")
        bad = subprocess.run([PY, str(OUTLINE), str(empty), str(tmp / "e.md")],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace")
        if bad.returncode == 0:
            return False, "空大纲应当报错"

        # 初稿必须能被转换器直接吃下去（两个脚本要接得上）
        conv = subprocess.run(
            [PY, str(CONVERT), str(dr), str(tmp / "draft.html"), "--quiet"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if conv.returncode != 0:
            return False, "初稿无法直接转换: {}".format(conv.stdout[-200:])
        dh = (tmp / "draft.html").read_text(encoding="utf-8")
        if "<!--" in dh:
            return False, "转换后写作提示注释没被剥离"
        if "用大纲生成初稿" not in dh:
            return False, "转换后丢了标题"

        return True, ("大纲 → 初稿（front matter/章节/要点/提示齐全）；"
                      "--sections 提升小节；--no-tips 生效；不覆盖已有文件；"
                      "空大纲报错；初稿可直接转换且注释被剥离")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def t20_auto_title_summary():
    """新增能力：自动补标题与摘要（挑战 Level 4「自动加标题摘要」）。"""
    tmp = Path(tempfile.mkdtemp(prefix="c4b_autometa_"))
    try:
        # 1) 没写 front matter：标题取自 h1，摘要取自首个合适段落
        a = tmp / "a.md"
        a.write_text(
            "# 自动补全测试\n\n"
            "这是正文的第一段，长度足够长，应该被选为摘要使用。\n\n"
            "<!-- 写作提示不该出现在成品里 -->\n\n"
            "## 小标题\n\n其他内容。\n", encoding="utf-8")
        r1 = subprocess.run([PY, str(CONVERT), str(a), str(tmp / "a.html")],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace")
        if r1.returncode != 0:
            return False, "转换失败: {}".format(r1.stdout[-200:])
        h1 = (tmp / "a.html").read_text(encoding="utf-8")

        # 标题应只出现 2 次：<title> 与头部大标题；正文那份应已被移除
        if h1.count("自动补全测试") != 2:
            return False, ("标题出现 {} 次（期望 2：<title> + 头部大标题，"
                           "正文那份应被移除）".format(h1.count("自动补全测试")))
        # 自动提取的摘要本来就在正文里，不能再往头部渲染一遍，否则同一句话复读。
        # 正文里出现 1 次 = 正常；2 次 = 头部又渲染了一份。
        if h1.count("这是正文的第一段") != 1:
            return False, ("正文段落被重复渲染（出现 {} 次，应为 1 次）"
                           .format(h1.count("这是正文的第一段")))
        if "已自动补全" not in r1.stdout:
            return False, "没有提示「已自动补全」（自动摘要对用户不可见=白补）"
        if "<!--" in h1:
            return False, "HTML 注释没被剥离"

        # 2) 写了 front matter：一个都不许被覆盖
        b = tmp / "b.md"
        b.write_text(
            "---\ntitle: 我写的标题\nsummary: 我写的摘要\n---\n\n"
            "# 正文里的大标题\n\n正文第一段内容也足够长了足够长了。\n",
            encoding="utf-8")
        subprocess.run([PY, str(CONVERT), str(b), str(tmp / "b.html"), "--quiet"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
        h2 = (tmp / "b.html").read_text(encoding="utf-8")
        if "我写的标题" not in h2 or "我写的摘要" not in h2:
            return False, "用户写的标题/摘要被自动值覆盖了"

        # 3) 含代码的段落不得当摘要 —— 否则讲 CSS 的文章摘要会变成一行样式，
        #    而且会被自检判成"正文泄漏 CSS"
        c = tmp / "c.md"
        c.write_text(
            "正文里引用了 `padding-left: 24px;` 这样一个例子。\n\n"
            "后面这段才是像样的摘要文字，长度也够长了。\n", encoding="utf-8")
        subprocess.run([PY, str(CONVERT), str(c), str(tmp / "c.html"), "--quiet"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
        h3 = (tmp / "c.html").read_text(encoding="utf-8")
        # 正文里那份行内代码本来就含 CSS 文本，所以正常应只出现 1 次；
        # 出现 2 次说明它同时被当成了摘要
        if h3.count("padding-left") != 1:
            return False, ("含代码的段落被当成摘要了（padding-left 出现 {} 次，"
                           "应为 1 次）".format(h3.count("padding-left")))
        if h3.count("后面这段才是像样的摘要文字") != 1:
            return False, "没有回退到下一个合适的摘要段落（或出现了复读）"
        chk = subprocess.run([PY, str(CHECKER), str(tmp / "c.html")],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace")
        if chk.returncode != 0:
            return False, "自检把这篇正常文章判成 CSS 泄漏: {}".format(
                chk.stdout.strip()[-160:])

        # 4) --no-auto-meta：不补标题（<title> 回落到默认值）
        subprocess.run([PY, str(CONVERT), str(a), str(tmp / "a2.html"),
                        "--no-auto-meta", "--quiet"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
        h4 = (tmp / "a2.html").read_text(encoding="utf-8")
        if "<title>公众号文章预览</title>" not in h4:
            return False, "--no-auto-meta 时不该自动补标题"
        if "<!--" in h4:
            return False, "--no-auto-meta 时注释仍应被剥离"

        return True, ("无 front matter 时自动补标题（正文那份被移除）与摘要；"
                      "已有值不被覆盖；含代码段落不当摘要且自检通过；"
                      "HTML 注释一律剥离；--no-auto-meta 可关闭")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


CASES = [
    ("修复1 · 违规标签清理与 h1 降级", t1_h1_div_script_removed),
    ("修复2 · 分隔线保留", t2_hr_preserved),
    ("修复3 · 引用块保留换行与加粗", t3_blockquote_keeps_br),
    ("修复4 · 图片注入 max-width", t4_img_max_width),
    ("修复5 · CSS 白名单真正生效", t5_css_whitelist),
    ("修复6 · 代码块换行保留", t6_code_block_newlines),
    ("修复7 · 目录不得泄漏 CSS 声明（回归）", t13_toc_no_css_leak),
    ("修复8 · callout 内的列表内容不得丢失（回归）", t14_callout_list_not_lost),
    ("修复9 · callout 标题的内联格式不得裸露星号（回归）", t15_callout_title_inline_md),
    ("新增1 · 5 套主题配色", t7_theme_system),
    ("新增2 · Callout 高亮框", t8_callout),
    ("新增3 · 自动目录", t9_toc),
    ("新增4 · 元数据与页脚", t10_metadata_footer),
    ("新增5 · 中文排版优化", t11_cjk_spacing),
    ("新增6 · 批量转换与边界情况", t12_batch_and_edge_cases),
    ("新增7 · 极端输入矩阵（10 组）", t16_extreme_input_matrix),
    ("新增8 · 本地图片嵌入与图注", t17_image_handling),
    ("新增9 · 一稿多投与体裁模板", t18_multi_format_and_templates),
    ("新增10 · 从大纲生成初稿（Level 4）", t19_outline_to_draft),
    ("新增11 · 自动标题摘要与注释剥离（Level 4）", t20_auto_title_summary),
]


def main():
    print("=" * 62)
    print("wechat-publisher 自动化测试")
    print("=" * 62)
    for title, fn in CASES:
        case(title, fn)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print("-" * 62)
    print("结果：{}/{} 通过".format(passed, total))
    if passed < total:
        print("失败用例：")
        for title, ok, detail in results:
            if not ok:
                print("  x {} -> {}".format(title, detail))
    print("=" * 62)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
