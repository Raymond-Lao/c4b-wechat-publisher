# 教学说明 · wechat-publisher 技能

> 技能名：`wechat-publisher`｜作者：李瑞翔｜版本：1.1（基于 C4B starter kit 二次开发）

这份文档的目标只有一个：**让拿到这个包的人，十分钟内跑出第一篇排版好的公众号文章。**

---

## 一、这个技能是干什么的

给它一份 **Markdown 或 Word 文档**，它吐出一段**可以直接粘贴进公众号编辑器**的 HTML。

公众号编辑器有一堆奇怪的限制：只认 inline CSS、禁止 `h1`、禁止 `div`、禁止 `script`、SVG 图片会消失……手工处理这些规则极其痛苦。这个技能把这些规则全部自动化了，还顺手做了配色、高亮框、自动目录这些提升观感的事。

**一句话：它是公众号的"打印机驱动"。**

---

## 二、安装

### 1. 装依赖

需要 Python 3.8 以上。然后：

```bash
pip install markdown beautifulsoup4 python-docx lxml
```

> 不装也行。脚本第一次运行时会自己检测并安装缺失的包。

### 2. 放入技能目录

把 `wechat-publisher` 整个文件夹放到技能目录下：

| 平台 | 位置 |
|------|------|
| Windows | `C:\Users\<你的用户名>\.workbuddy\skills\wechat-publisher\` |
| macOS / Linux | `~/.workbuddy/skills/wechat-publisher/` |

解压 `liruixiang_C4B_wechat-publisher.zip` 后目录结构应该是：

```
wechat-publisher/
├── SKILL.md
├── scripts/
│   ├── convert_to_wechat.py      ← 主转换脚本
│   ├── check_wechat_html.py      ← 发布前自检
│   ├── outline_to_draft.py       ← 大纲 → 初稿（写作辅助）
│   └── export_formats.py         ← 一稿多投 + 体裁模板
├── templates/                    ← 4 套体裁骨架
│   ├── tech-tutorial.md
│   ├── learning-note.md
│   ├── skill-intro.md
│   └── retrospective.md
├── references/
│   ├── syntax.md                 ← 语法手册
│   ├── wechat_styles.md          ← 主题与样式
│   ├── wechat_restrictions.md    ← 公众号限制清单
│   └── CHANGELOG.md              ← 改动记录
├── examples/
│   ├── demo_all_features.md      ← 全功能演示
│   ├── sample_article.md         ← 示例文章
│   ├── sample_report.docx        ← 示例 Word
│   └── sample_output.html        ← 示例输出
├── evals/                        ← 评估用例与执行器
│   ├── evals.json
│   ├── run_evals.py
│   └── files/                    ← 用例输入样例
└── tests/
    └── run_tests.py              ← 自动化测试
```

### 3. 验证安装是否成功

```bash
cd wechat-publisher
python tests/run_tests.py
```

看到 `结果：20/20 通过` 就说明装好了。

---

## 三、怎么用（三步）

### 第 1 步：写文章，并在开头填四行信息

用 Markdown 写正文。文件最开头加一个信息块：

```markdown
---
title: 文章标题
author: 你的名字
date: 2026-10-06
summary: 一句话摘要，会显示在标题下面。
theme: blue
toc: true
---

## 第一个小标题

正文……
```

这几行是可选的。**不写也能转换** —— 转换时会自动从正文里补：

- 标题：取正文里的 `# 一级标题`，并且会把它从正文移走（避免同一行标题出现两次）；
- 摘要：取正文里第一个合适的段落（会自动跳过带代码的段落，免得摘要变成一行代码）。

想自己控制就写清楚。**写了就一定以你写的为准**，自动补全只在缺的时候兜底。

### 第 0 步（可选）：只有提纲，先让它长成初稿

如果你手上只有一份提纲（章节 + 要点），可以先让工具把它扩成初稿，再往下写：

```bash
python scripts/outline_to_draft.py 我的大纲.md 初稿.md --author "你的名字"
```

大纲长这样就行：

```markdown
# 文章标题

## 一、第一节
- 要点 A
- 要点 B

## 二、第二节
1. 编号的要点也认
```

生成的初稿里有完整的 front matter、章节结构、以及用注释写成的写作提示
（提示只是写的时候看得见，转换后会被自动去掉，不会出现在成品里）。

| 参数 | 作用 |
|------|------|
| `--sections` | 把每个要点提升为 `### 小节标题`（默认只保留为要点清单） |
| `--no-tips` | 不插写作提示 |
| `--force` | 允许覆盖已存在的输出文件（默认拒绝，防止手滑毁掉在写的稿子） |

生成的初稿可以直接交给主脚本：

```bash
python scripts/outline_to_draft.py 我的大纲.md 初稿.md --author "你的名字"
python scripts/convert_to_wechat.py 初稿.md 初稿.html --theme blue --toc
```

> 它和 `templates/` 里的体裁模板**不是一回事**：模板是空骨架（章节固定，你往里填），
> 这个脚本是按你的提纲生成结构。

### 第 2 步：运行一条命令

```bash
python scripts/convert_to_wechat.py 我的文章.md
```

屏幕上会打印七步进度和最终结果。输出文件是 `我的文章.html`。

**常用的四种改法：**

```bash
# 换配色主题
python scripts/convert_to_wechat.py 我的文章.md --theme warm

# 指定输出文件名
python scripts/convert_to_wechat.py 我的文章.md 输出.html

# Word 文档同样支持
python scripts/convert_to_wechat.py 报告.docx 报告.html --theme elegant

# 图片想窄一点（默认占满 100% 宽度）
python scripts/convert_to_wechat.py 我的文章.md --image-width 80%
```

查看所有主题：

```bash
python scripts/convert_to_wechat.py --list-themes
```

### 第 3 步：自检 → 预览 → 粘贴

```bash
python scripts/check_wechat_html.py 我的文章.html
```

看到 `[通过]` 就可以往下走。然后：

1. 用浏览器打开生成的 `.html` 文件
2. `Ctrl+A` 全选 → `Ctrl+C` 复制
3. 打开公众号后台（mp.weixin.qq.com）→ 新建图文
4. `Ctrl+V` 粘贴进编辑器
5. 手机上预览 → 调整 → 发布

::: tip 为什么要先自检
自检脚本会告诉你：有没有残留的违规标签、图片有没有宽度限制、有没有 SVG 图片（这种图片粘贴后一定会消失）、中文字数有没有超限。**它只是检查，不会改你的文件。**
:::

---

## 四、写高亮框（最实用的功能）

在 Markdown 里用三个冒号包一个块：

```markdown
::: tip 小标题
这里是内容，**支持加粗**、`行内代码`。
可以写多行。
:::
```

四种类型：

| 类型 | 显示效果 | 什么时候用 |
|------|---------|-----------|
| `note` | 📘 知识点（蓝色） | 解释概念、补充背景 |
| `tip` | 💡 小提示（青色） | 技巧、经验 |
| `warn` | ⚠️ 注意（橙色） | 踩坑提醒、风险 |
| `practice` | 🔧 动手做（紫色） | 操作步骤、练习任务 |

一篇 3000 字的文章放 **2 到 4 个**最合适。放太多反而没有重点。

---

## 五、批量转换

```bash
python scripts/convert_to_wechat.py --batch ./drafts --theme blue
```

目录下所有 `.md` 和 `.docx` 会一次转完，输出到 `./drafts/wechat_output/`。

---

## 六、图片怎么处理（最容易踩坑的一节）

公众号的图片和网页上的图片**不是一回事**。下面这张表建议先看一眼，能省掉你后面半小时的困惑：

| 你写的 | 会发生什么 | 技能怎么处理 |
|--------|-----------|-------------|
| `![说明](本地图片.png)` | 编辑器读不到你硬盘上的文件 | **自动读成 base64 嵌进 HTML**，粘贴时图片跟着进去 |
| `![说明](https://…/a.png)` | 保存时可能丢失 | 保留外链，同时**在终端告警**提醒你先上传到素材库 |
| `![说明](写错路径.png)` | 页面上是个空框 | 保留原路径并**明确告警**，不会默默放过 |
| `![说明](矢量图.svg)` | 保存后直接消失 | **不嵌入**，告警让你先转成 PNG |

另外两件自动做的事：

- **给每张图加宽度上限**（默认 `max-width: 100%`），长图不会撑破手机屏幕；
- **把 `![...]` 里的说明文字渲染成图注**，显示在图片下方的小字位置。

```bash
# 图片想窄一点
python scripts/convert_to_wechat.py 我的文章.md --image-width 80%

# 不想要图注 / 不想嵌入图片
python scripts/convert_to_wechat.py 我的文章.md --no-captions
```

::: warn 图片告警不会被 --quiet 关掉
`--quiet` 是用来给批量转换降噪的，但**图片相关的告警不受它影响**。
原因是上面那四种情况在页面上看起来都是"一张没出来的图"，而你要做的动作完全不同
（上传 / 补路径 / 转格式 / 修路径）—— 这时候省掉提示，等于把问题藏起来。
:::

---

## 七、一稿多投与体裁模板

同一篇稿子，公众号要 HTML，知乎要 Markdown，发群里要纯文本。
不用改三遍源稿：

```bash
python scripts/export_formats.py 我的文章.md --outdir dist
# → dist/我的文章.wechat.html
# → dist/我的文章.zhihu.md
# → dist/我的文章.plain.txt
```

只想要其中一两种：

```bash
python scripts/export_formats.py 我的文章.md --outdir dist --formats zhihu,plain
```

**体裁模板**：不用每次对着空白页想结构，先套个骨架再填内容。

```bash
python scripts/export_formats.py --list-templates
python scripts/export_formats.py --new tech-tutorial drafts/我的新稿.md
```

| 模板名 | 适合写什么 |
|--------|-----------|
| `tech-tutorial` | 技术教程：一步步教别人做成某件事 |
| `learning-note` | 学习心得：我做了一个 X，过程与踩坑 |
| `skill-intro` | 技能/产品介绍：这是什么、怎么用、给谁用 |
| `retrospective` | 复盘总结：目标 / 结果 / 差距 / 改进 |

> 目标文件已存在时，`--new` 会**拒绝覆盖**并报错退出 —— 起稿是高频动作，
> 静默覆盖别人的稿子是事故。

---

## 八、五套配色主题

| 主题 | 适合什么内容 |
|------|------------|
| `default` | 中性灰，最安全，什么都能用 |
| `blue` | 技术教程、知识科普 |
| `warm` | 生活分享、情感随笔 |
| `minimal` | 极简风格，纯文字长文 |
| `elegant` | 读书笔记、书评 |

想微调主色但不想改代码：

```bash
python scripts/convert_to_wechat.py 文章.md --theme minimal --accent "#c0392b"
```

想自己加一套主题：改 `scripts/convert_to_wechat.py` 里的 `THEMES` 字典，
把新主题加进 `THEME_ORDER`。写法见 `references/wechat_styles.md`。

---

## 九、改完技能之后，怎么确认没改坏

有两层验证，建议都跑：

**第一层：单元测试（快，十几秒）**

```bash
python tests/run_tests.py
```

20 个用例，覆盖全部修复与新增能力。看到 `20/20 通过` 就没事。

**第二层：评估基准（慢一点，约 30 秒，36 次运行）**

```bash
python evals/run_evals.py --skill . \
    --baseline ../c4b-wechat-publisher-starter/scripts/convert_to_wechat.py \
    --workspace ../wechat-publisher-workspace --runs 3
```

它会拿本技能和 **starter kit 原版脚本**跑同一批 6 个用例，
逐条判分，然后输出：

- `benchmark.json` / `benchmark.md` —— 通过率对比与自动分析
- `eval_report.html` —— 可以逐条点开看每个用例输出的审阅页

> `--baseline` 要指向 starter kit 原版的 `convert_to_wechat.py`。
> 这一项不能省 —— 没有基线就没有"改造加了多少值"的答案。

---

## 十、常见问题

**Q：粘贴到公众号后格式还是乱了？**
先跑一遍 `check_wechat_html.py`。如果有 `[错误]`，先解决错误；如果显示通过但格式还是乱，检查你的浏览器是不是开了"阅读模式"或插件——复制时要复制**渲染后的页面**。

**Q：图片丢了？**
分四种情况，看终端告警：外链图需要先上传到素材库；本地路径的图**会自动嵌成 base64**，如果你看到"未嵌入"的告警，说明路径写错了或图片被移走了；SVG 图保存后一定消失，先转成 PNG。

**Q：为什么终端会冒出"[图片] …"的提示，我用 `--quiet` 也没关掉？**
这是故意的。这四种图片问题在页面上看起来都一样（一个空框），但你要做的动作完全不同，所以不静默。详见第六节。

**Q：代码块挤成一行？**
本技能已经修复了这个问题（会自动加 `white-space: pre-wrap`）。如果你的版本还会挤，说明用的不是这个版本。

**Q：能转换 `.doc`（老版 Word）吗？**
不能。请先用 Word 另存为 `.docx`。

**Q：一次转换多少字比较好？**
公众号单篇上限约 20000 中文字，建议 2000–4000 字。

---

## 十一、参考文档在哪

| 想看什么 | 看哪个文件 |
|---------|-----------|
| 完整语法（front matter、callout、命令行参数） | `references/syntax.md` |
| 主题、样式值、怎么加新主题 | `references/wechat_styles.md` |
| 公众号到底禁什么、怎么规避 | `references/wechat_restrictions.md` |
| 相比 starter kit 改了什么、为什么 | `references/CHANGELOG.md` |

---

## 十二、卸载

删掉 `wechat-publisher` 文件夹即可。它不会在系统里注册任何东西，也不会写注册表。
