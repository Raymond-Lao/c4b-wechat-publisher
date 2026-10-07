---
name: wechat-publisher
description: Convert Markdown or Word documents into WeChat Official Account (微信公众号) compatible HTML that can be copy-pasted straight into the WeChat editor. Applies a selectable color theme, inline CSS, callout highlight boxes, auto table of contents, article metadata and a copyright footer, auto-fills the title and summary from the body when the front matter omits them, embeds local images as base64 with captions, strips forbidden HTML and HTML comments, and validates the result before publishing. Can also expand a bullet outline into a full draft, export the same source to Zhihu Markdown or plain text, and scaffold new drafts from article-type templates. Use when the user says convert to WeChat, 公众号排版, 公众号文章, 微信公众号格式, 转换成公众号, make a WeChat article, generate WeChat HTML, 一稿多投, 转知乎格式, 从大纲写初稿, 大纲转初稿, or provides a .md or .docx file and asks to format, beautify or publish it for 微信公众号.
agent_created: true
---

# WeChat Publisher — Markdown / Word → 公众号 HTML

## Overview

把 Markdown 或 Word 文档转成**可以直接粘贴进公众号编辑器**的 HTML。可以理解成一台"公众号打印机"：给它内容，它吐出经得起公众号严格编辑器规则的排版好的 HTML。

基线来自 EduSeed C4B starter kit。本版修掉了 8 个真实缺陷（5 个来自基线，3 个是自己改造时改出来的），新增 12 项能力，并跑过一轮 skill-creator 的 eval 流程（6 个用例 × with_skill/without_skill 两种配置 × 3 轮）。改动清单见 `references/CHANGELOG.md`，评估结果见 `evals/`。

覆盖写作到发布的两段：**大纲 → 初稿**（`outline_to_draft.py`）和**初稿 → 公众号 HTML**（`convert_to_wechat.py`）。

## 核心能力

| 能力 | 说明 |
|------|------|
| 多主题配色 | 5 套主题：default / blue / warm / minimal / elegant，可再自定义主色 |
| Callout 高亮框 | 4 种类型：note / tip / warn / practice |
| 自动目录 | 从 h2/h3 生成编号目录 |
| 文章元数据与页脚 | 标题、作者、日期、摘要（文件头 front matter），并自动追加版权行与生成标识 |
| **自动标题摘要** | 没写 front matter 时从正文提取：h1 当大标题（并从正文移除，避免重复）、首个合适段落当摘要（只作元数据，不重复渲染到头部）；含代码或样式声明的段落会被跳过 |
| 中文排版优化 | 中文与英文/数字之间自动补空格，代码块内不处理 |
| **本地图片处理** | 本地图片自动嵌成 base64（粘贴时不丢）、统一宽度上限、alt 文本渲染成图注；外链/缺失/SVG 三类风险分别告警 |
| **一稿多投** | 同一份源稿一次导出公众号 HTML + 知乎 Markdown + 纯文本 |
| **体裁模板** | 4 套现成骨架：技术教程 / 学习心得 / 技能介绍 / 复盘总结 |
| **从大纲生成初稿** | 给一份提纲（章节 + 要点），生成带 front matter、章节结构与写作提示的初稿，可直接交给转换脚本 |
| 批量转换 | 一次转换整个目录 |
| 输出自检 | 转换后自动扫描违规标签 / CSS / 图片，另有独立自检脚本 |
| **评估基准** | `evals/` 内含 6 个用例的可复现 benchmark，带自动判分与审阅页 |

## Quick Start

```bash
# 最简：输出同名 .html（文章.md → 文章.html）
python scripts/convert_to_wechat.py 文章.md

# 指定输出、主题、目录，并补元数据
python scripts/convert_to_wechat.py 文章.md 文章_wechat.html --theme blue --toc \
    --author "李瑞翔" --summary "一句话摘要"

# Word 文档
python scripts/convert_to_wechat.py 报告.docx 报告_wechat.html --theme elegant

# 图片：默认就会把本地图片嵌成 base64，并把 alt 当图注
# （--no-embed-images 只留原路径；--no-captions 关图注；--image-width 80% 限宽）
python scripts/convert_to_wechat.py 文章.md --image-width 80%

# 批量：转换目录下所有 .md/.docx/.html
# 注意输出不在原目录，而在 <输入目录>/wechat_output/ 子目录里
python scripts/convert_to_wechat.py --batch ./drafts --theme warm
# → ./drafts/wechat_output/a.html、./drafts/wechat_output/b.html

# 发布前自检
python scripts/check_wechat_html.py 文章_wechat.html

# 一稿多投：同时出公众号 HTML / 知乎 Markdown / 纯文本
python scripts/export_formats.py 文章.md --outdir dist --theme blue --toc

# 套体裁模板开新稿
python scripts/export_formats.py --list-templates
python scripts/export_formats.py --new tech-tutorial drafts/my-post.md

# 从大纲生成初稿（提纲 → 可往下写的初稿，带写作提示注释）
python scripts/outline_to_draft.py 我的大纲.md 初稿.md --author "李瑞翔"
python scripts/outline_to_draft.py 我的大纲.md --sections   # 要点提升为 ### 小节
python scripts/outline_to_draft.py 我的大纲.md --no-tips    # 不要写作提示

# 没写 front matter 也行：转换时自动从正文补标题与摘要
# （--no-auto-meta 可关闭；h1 会被用作大标题并从正文移除）
python scripts/convert_to_wechat.py 只有正文的稿子.md
```

之后：浏览器打开输出 HTML → `Ctrl+A` → `Ctrl+C` → 粘贴进公众号编辑器 → 手机上预览 → 发布。

## 工作流

### Step 0（可选）— 从大纲生成初稿

如果用户手上只有提纲（章节 + 要点），先用 `scripts/outline_to_draft.py` 生成初稿，
再进后面的排版流程。两个脚本是接得上的：初稿的输出可以直接喂给 `convert_to_wechat.py`。

```bash
python scripts/outline_to_draft.py 大纲.md 初稿.md --author "作者名"
```

生成的初稿里，写作提示用 HTML 注释写成（写的时候看得见），转换时会被自动剥离，
不会出现在成品里。区别记一下：`templates/` 是**空骨架**（结构固定，你填内容），
`outline_to_draft.py` 是**按用户的大纲生成**（章节来自提纲，要点已摆到位置上）。

### Step 1 — 确认输入与风格

确认源文件格式（`.md` / `.docx` / `.html`）。向用户确认三件事：
主题、是否需要目录、作者署名与摘要。

用户没有指定时，按内容气质选：技术教程用 `blue`，生活分享用 `warm`，
读书笔记用 `elegant`，纯文字长文用 `minimal`。

**如果源文件没写 front matter**：不用停下来让用户补。转换时会自动从正文提取——
`h1` 当文章大标题（并从正文移除，避免重复），首个不含代码的合适段落当摘要。
命令行和文件头里的值优先级更高，自动值只在缺失时兜底。

### Step 2 — 处理 Callout 标记

Callout 在 Markdown 里用三个冒号包裹：

```markdown
::: tip 小标题
这里是内容，**支持加粗**和 `行内代码`。
:::
```

四种类型：`note`（知识）、`tip`（提示）、`warn`（注意）、`practice`（动手做）。
完整语法见 `references/syntax.md`。

### Step 3 — 转换

运行 `scripts/convert_to_wechat.py`。脚本依次完成 7 步：
读取 → 清洗违规标签 → **处理图片（嵌入/告警）** → 套主题样式 → 中文排版优化 → 过滤 CSS → 输出。

### Step 4 — 自检

转换脚本自身会报一次自检结果。发布前再单独跑一次
`scripts/check_wechat_html.py <输出文件>` 拿完整报告（字数、图片数、违规项统计）。
有 `[错误]` 必须修，有 `[提醒]` 逐条确认。

图片相关的提醒不受 `--quiet` 抑制 —— "图片悄悄丢了"是排版里最难看出来的失败，
必须让用户看见。

### Step 5 — 交付与发布说明

告诉用户：输出文件路径、用了哪套主题、中文字数与图片数。并提醒两条发布要点：

1. 外链图片需要先上传到公众号素材库，否则会丢；
2. SVG 图片保存后会消失，务必用 PNG。

### Step 6（可选）— 多平台分发

如果用户还要发知乎或发群，用 `scripts/export_formats.py` 从**同一份源稿**出三种格式，
不要为了适配平台去改源稿。

### Step 7（可选）— 改完技能后复跑评估

改动本技能的脚本后，用 `evals/run_evals.py` 复跑一遍基准，确认没有回归：

```bash
python evals/run_evals.py --skill . \
    --baseline <starter-kit>/scripts/convert_to_wechat.py \
    --workspace ../wechat-publisher-workspace --runs 3
```

它会输出 grading.json、benchmark.json，并调用 skill-creator 的 eval-viewer 生成审阅页。

## 输入格式

| 格式 | 处理方式 |
|------|---------|
| Markdown (.md) | 用 `markdown` 库转换，支持表格、围栏代码、脚注、callout、front matter |
| Word (.docx) | 用 `python-docx` 提取，保留标题层级、加粗斜体、列表、表格；内嵌图片转 PNG/JPG base64 |
| HTML (.html) | 直接读取后清洗 |

## 依赖

```bash
pip install markdown beautifulsoup4 python-docx lxml --break-system-packages
```

首次运行会自动检测并安装缺失依赖。

## 公众号硬性限制

转换脚本会自动执行下列规则，无需人工检查，但排查问题时要对照：

- 只允许标签：`p, h2, h3, ul, ol, li, span, img, a, table, tr, th, td, br`
- 禁止：`script / style / iframe / div / h1 / svg / video / audio`（`h1` 降级为 `h2`，`div` 改为 `p`）
- 禁止：`class` / `id` / JS 事件属性
- CSS **必须 inline**，且不能含 `position / float / flex / grid / animation / transition`
- 图片：PNG/JPG 可用 base64；SVG 会消失
- 单篇约 20000 中文字、100 张图上限

完整清单见 `references/wechat_restrictions.md`。

## 边界情况

| 情况 | 处理 |
|------|------|
| 源文件为空 | 报错中止，不生成空 HTML |
| 未知主题名 | 提示可选值并回退 default |
| 无 h2/h3 或只有一个 | 不生成目录（至少 2 个标题才有意义） |
| 非 UTF-8 编码 | 按 UTF-8 读取，非法字节替换而不是崩溃 |
| 代码块含中文 | 中文排版优化跳过代码块，避免破坏代码 |
| 表格过宽 | 设置 `width: 100%`；过宽表格建议人工拆成两张 |
| Word 内嵌图片 | 转 base64 内嵌，公众号粘贴时会上传到自己的 CDN |
| 本地图片文件 | 转 base64 内嵌；找不到文件时**保留原路径并明确告警**，不静默丢弃 |
| 外部链接图片 | 保留原样并提醒先上传到素材库 |
| 本地 SVG 图片 | 不嵌入，直接告警（公众号保存后会消失，让用户先转 PNG） |
| 图片 alt 文本 | 有 alt 就在图下方渲染成居中图注；没有则不加 |
| 源文件没有 front matter | 自动从正文提取标题（取 `h1`）与摘要；含代码或样式声明的段落不当摘要 |
| 源文件里有 HTML 注释 | 一律剥离——初稿里的写作提示就是用注释写的，成品里不该出现 |
| 大纲只有要点、没有分章 | 全部收进一章，不丢内容 |
| 初稿的目标文件已存在 | 拒绝覆盖（`--force` 才覆盖），避免手滑毁掉正在写的稿子 |

## 参考文件

- `scripts/convert_to_wechat.py` — 主转换脚本（md/docx/html → 公众号 HTML）
- `scripts/check_wechat_html.py` — 发布前独立自检（7 大类检查项）
- `scripts/outline_to_draft.py` — 大纲 → 初稿（写作辅助，Level 4）
- `scripts/export_formats.py` — 一稿多投 + 体裁模板
- `evals/evals.json` — 6 个评估用例（prompt / 预期 / 输入）
- `evals/run_evals.py` — 评估执行与判分（with_skill vs without_skill）
- `evals/files/` — 评估用例的输入样例
- `templates/` — 4 套体裁骨架（技术教程 / 学习心得 / 技能介绍 / 复盘总结）
- `tests/run_tests.py` — 20 个自动化测试用例（修复回归 + 新能力）
- `references/syntax.md` — 完整语法手册（front matter / callout / 命令行参数）
- `references/wechat_styles.md` — 5 套主题的全部样式值与自定义方法
- `references/wechat_restrictions.md` — 公众号 HTML 限制完整清单
- `references/CHANGELOG.md` — 相对 starter kit 基线的全部改动与原因
- `examples/demo_all_features.md` — 覆盖全部语法的演示文件
- `examples/sample_article.md` — 一篇完整的示例文章
