# 语法手册

本技能在标准 Markdown 之上增加了三组语法：文件头元数据、Callout 高亮框、命令行参数。

---

## 1. 文件头元数据（front matter）

写在 Markdown 文件最开头，用 `---` 包起来。这些值可以被命令行参数覆盖。

```markdown
---
title: 文章标题
author: 李瑞翔
date: 2026-10-06
summary: 一句话摘要，会显示在标题下方作为导语。
theme: blue
toc: true
cjk_spacing: true
footer: 本文为原创，转载请注明出处与作者。
---
```

| 字段 | 作用 | 默认 |
|------|------|------|
| `title` | 文章大标题，居中显示在正文最前面 | 空 |
| `author` | 作者署名 | 空 |
| `date` | 日期，与作者用 `·` 连接显示 | 空 |
| `summary` | 导语/摘要，带底色的强调块 | 空 |
| `theme` | 配色主题 | `default` |
| `toc` | 是否生成目录（`true` / `false`） | `false` |
| `cjk_spacing` | 是否开启中英文自动加空格 | `true` |
| `footer` | 自定义页脚文案 | 自动生成版权行 |

**注意**：文件头必须以 `---` 开头，且第一行不能有空行。正文中间的 `---` 仍然是分隔线，两者不冲突。

---

## 2. Callout 高亮框

用三个冒号包裹一个块：

```markdown
::: 类型 标题
内容，支持 **加粗**、`行内代码`、[链接](https://example.com)。

可以写多行，每行会保留换行。
:::
```

- `类型` 必填，只能是下面四种之一；写成别的会被当作普通段落。
- `标题` 可省略。省略时使用该类型的默认标签。

| 类型 | 默认标签 | 颜色 | 适用场景 |
|------|---------|------|---------|
| `note` | 📘 知识点 | 蓝 | 概念解释、背景补充 |
| `tip` | 💡 小提示 | 青 | 技巧、经验、省时间的做法 |
| `warn` | ⚠️ 注意 | 橙 | 踩坑提醒、限制、风险 |
| `practice` | 🔧 动手做 | 紫 | 操作步骤、练习任务 |

**使用建议**：一篇 3000 字的文章放 2–4 个最舒服。放太多反而失去强调效果。

**限制**：callout 不能嵌套 callout；不要在里面写 `<div>` 等禁止标签。

---

## 3. 命令行参数

```
python scripts/convert_to_wechat.py <输入> [输出] [选项]
```

| 参数 | 说明 |
|------|------|
| `<输入>` | `.md` / `.docx` / `.html` 文件路径 |
| `[输出]` | 输出 HTML 路径。省略时与输入同名，扩展名换为 `.html` |
| `--theme <名>` | 主题：`default` / `blue` / `warm` / `minimal` / `elegant` |
| `--accent <#RRGGBB>` | 覆盖主题主色，例如 `--accent "#c0392b"` |
| `--toc` / `--no-toc` | 强制开启 / 关闭目录 |
| `--no-cjk-spacing` | 关闭中英文自动加空格 |
| `--title` `--author` `--date` `--summary` `--footer` | 覆盖对应元数据 |
| `--image-width <值>` | 图片最大宽度，默认 `100%`，可写 `80%` / `420px` |
| `--no-embed-images` | 不把本地图片嵌成 base64，只保留原路径（一般不用） |
| `--no-captions` | 不把图片的 `alt` 文本渲染成图注 |
| `--no-auto-meta` | 不自动补标题与摘要（默认会从正文提取，见 3.3） |
| `--batch <目录>` | 批量转换目录下所有 `.md` / `.docx`，输出到 `<目录>/wechat_output/` |
| `--list-themes` | 列出全部主题 |
| `--quiet` | 只输出最终结果，不打印 7 步过程（图片告警不受此影响） |

优先级：**命令行参数 > 文件头元数据 > 默认值**。

### 3.1 图片的行为

| 输入里的图片 | 输出 |
|--------------|------|
| `![说明](本地图片.png)` | 读成 base64 内嵌；`说明` 渲染成图注 |
| `![说明](https://…/a.png)` | 保留外链，同时在终端告警"可能丢失" |
| `![说明](找不到.png)` | 保留原路径，告警提醒确认图片位置 |
| `![说明](矢量图.svg)` | **不嵌入**，告警让先转 PNG（公众号保存后会丢 SVG） |

**图片告警不会被 `--quiet` 静默掉** —— 这四种在页面上都只表现为"一张没出来的图"，
必须让作者知道是哪一种，因为处理动作完全不同。

### 3.2 一稿多投与体裁模板

```
python scripts/export_formats.py <输入.md> [--outdir dist] [--formats wechat,zhihu,plain]
python scripts/export_formats.py --list-templates
python scripts/export_formats.py --new <模板名> <目标路径.md>
```

四个体裁模板：`tech-tutorial` / `learning-note` / `skill-intro` / `retrospective`。

> 源稿是唯一真相，格式只是出口 —— 不要为了适配某个平台去改源稿。

---

### 3.3 自动标题与摘要

**不写 front matter 也能出完整的头部**：转换时会从正文里提取。

| 元素 | 从哪来 | 说明 |
|------|-------|------|
| 标题 | 第一个 `h1` | 提取后会**从正文移除**——它已经当大标题了，正文再来一次就是重复 |
| 摘要 | 第一个合适段落 | 跳过两类段落：含 `<code>` 的、像样式声明的；**只作元数据，不重复渲染到文章头部** |

优先级：**命令行 > 文件头 > 自动提取**。自动值只在缺失时兜底，不会覆盖你写的东西。
不想要这个行为就加 `--no-auto-meta`。

> **自动提取的摘要为什么不渲染进头部**：它是**从正文里抄出来的一段**，本来就在文章里，
> 再渲染一遍，读者会在开头看到同一句话连说两次（这个问题正是跑 eval 时暴露出来的）。
> 想在文章开头显示导语，请在 front matter 里自己写 `summary:` —— 那是你的选择，会照常渲染。

> 摘要为什么跳过含代码的段落：一篇讲 CSS 的文章，第一段常常是
> 「正文里引用了 `padding-left: 24px;` 这样一个例子。」——
> 拿它当摘要，读者在文章列表页看到的就是一行样式代码。

另外，源文件里的 **HTML 注释一律会被剥离**。初稿里的写作提示就是用注释写的，
写的时候看得见，成品里不该出现。

### 3.4 从大纲生成初稿

`scripts/outline_to_draft.py` 负责"想法 → 初稿"这一段：

```bash
# 基本用法：提纲 → 初稿
python scripts/outline_to_draft.py 大纲.md 初稿.md --author "李瑞翔"

# 把每个要点提升为 ### 小节标题
python scripts/outline_to_draft.py 大纲.md --sections

# 不要写作提示
python scripts/outline_to_draft.py 大纲.md --no-tips
```

| 参数 | 说明 |
|------|------|
| `--author` / `--date` / `--summary` / `--title` / `--theme` | 写进初稿的 front matter |
| `--sections` | 要点 → `###` 小节标题（默认只保留为要点清单） |
| `--no-tips` | 不插入写作提示注释 |
| `--force` | 允许覆盖已存在的输出文件（默认拒绝，防止手滑毁掉在写的稿子） |

大纲的写法没有硬要求，能识别这些就够：

```markdown
# 文章标题          ← 变成 front matter 的 title

## 一、第一节        ← 变成 h2 章节
- 要点 A            ← 摆在章节里
- 要点 B

## 二、第二节
1. 编号要点也会被识别
```

生成的初稿可以直接交给转换脚本，两个工具是接得上的：

```bash
python scripts/outline_to_draft.py 大纲.md 初稿.md --author "李瑞翔"
python scripts/convert_to_wechat.py 初稿.md 初稿.html --theme blue --toc
```

> 和 `templates/` 的区别（这两个东西容易混）：
> `templates/` 是**空骨架**——章节标题固定，你往里填内容；
> 本脚本是**按你的大纲生成**——章节来自你的提纲，要点已经被摆到位置上。

## 4. 自检工具

```
python scripts/check_wechat_html.py <输出.html> [--strict]
```

`--strict` 会把"[提醒]"也视为失败，适合在自动化流程里当门禁用。

退出码：`0` 通过，`1` 有错误。

---

## 完整示例

```markdown
---
title: 我用 AI 做了一个公众号排版技能
author: 李瑞翔
date: 2026-10-06
summary: 从拿来主义到二次开发，一个非技术背景的人也能造工具。
theme: blue
toc: true
---

## 为什么我要做这个

公众号编辑器只认 inline CSS，从 Markdown 粘贴过去经常格式全乱。

::: note 什么是 inline CSS
就是直接把样式写在标签上，像 `p style="color:red"` 这样。
:::

::: warn 踩坑提醒
公众号会把 `h1` 强制降级，也会把 `div` 换成 `p`。
:::

## 我是怎么做的

1. 拿到一个现成的 starter kit
2. 跑通它，读代码，找缺陷
3. 用 skill-creator 二次开发

---

正文结束。
```

转换命令：

```bash
python scripts/convert_to_wechat.py article.md article_wechat.html
python scripts/check_wechat_html.py article_wechat.html
```
