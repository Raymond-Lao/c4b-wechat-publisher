# 样式与主题参考

所有样式值都以 **inline CSS** 形式写在标签上。想换风格，改主题定义即可，不必逐个改样式。

---

## 五套主题

| 主题 | 定位 | 主色 | h2 左侧竖线 | 分隔符 |
|------|------|------|------------|--------|
| `default` | 中性灰，最安全 | `#3f3f46` | 无 | `· · ·` |
| `blue` | 蓝，科技/学术/教程 | `#1a73e8` | 有 | `— — —` |
| `warm` | 暖橙，生活/分享 | `#e65100` | 有 | `· · ·` |
| `minimal` | 极简，纯文字长文 | `#333333` | 无 | `———` |
| `elegant` | 深青，读书笔记/随笔 | `#0f6e56` | 有 | `◇ ◇ ◇` |

```bash
python scripts/convert_to_wechat.py article.md --list-themes   # 查看全部
python scripts/convert_to_wechat.py article.md --theme warm    # 指定主题
```

---

## 各元素样式（以 blue 主题为例）

### H2 — 章节标题（公众号最高级标题）
```
font-size: 22px; font-weight: bold; line-height: 1.5;
color: #1a73e8; margin: 32px 0 14px 0;
padding-left: 10px; border-left: 4px solid #1a73e8;
```
`border-left` 那部分是 `h2_bar: True` 主题才有的左侧竖线。

### H3 — 小标题
```
font-size: 17px; font-weight: bold; line-height: 1.6;
color: #22303f; margin: 22px 0 10px 0;
```

### 正文段落
```
font-size: 16px; line-height: 1.75; color: #22303f;
margin: 14px 0; letter-spacing: 0.3px;
```
`letter-spacing: 0.3px` 是中文排版的关键——中文没有词间空格，加一点点字距能明显提升可读性。

### 列表项
```
font-size: 16px; line-height: 1.75; color: #22303f;
margin: 6px 0; letter-spacing: 0.3px;
```
列表容器 `ul` / `ol`：`margin: 12px 0; padding-left: 24px;`

### 行内代码
```
background-color: #f5f5f5; color: #d73a49; font-size: 14px;
padding: 2px 5px; border-radius: 3px; font-family: <等宽字体栈>;
```

### 代码块
```
background-color: #eef4ff; color: #24292e; font-size: 13px;
line-height: 1.7; padding: 14px 16px; margin: 16px 0;
border-radius: 8px; font-family: <等宽字体栈>;
white-space: pre-wrap; word-break: break-all;
```
`white-space: pre-wrap` 保证长代码行能换行，不会推出屏幕外。

### 引用块
```
background-color: #eef4ff; color: #5b6b7c; font-size: 15px;
line-height: 1.8; padding: 12px 16px; margin: 18px 0;
border-left: 4px solid #1a73e8; border-radius: 0 8px 8px 0;
```

### 表格
```
table      margin: 16px 0; font-size: 14px; width: 100%; border-collapse: collapse;
th         background-color: #eef4ff; padding: 9px 10px; text-align: left;
           border: 1px solid #d7e3f4; font-weight: bold;
td         padding: 9px 10px; border: 1px solid #d7e3f4; line-height: 1.6;
```

### 图片
```
max-width: 100%; height: auto; display: block;
margin: 18px auto; border-radius: 8px;
```

### 分隔线（Markdown 的 `---`）
```
text-align: center; color: #d7e3f4; letter-spacing: 6px;
font-size: 13px; margin: 30px 0;
```

### 文章标题 / 署名 / 摘要 / 目录 / 页脚

| 元素 | 关键样式 |
|------|---------|
| 大标题 | `font-size: 24px; font-weight: bold; text-align: center; color: 主色` |
| 署名行 | `font-size: 13px; text-align: center; color: 次级文字色` |
| 摘要 | `background-color: 浅主色; font-size: 15px; line-height: 1.8; border-left: 4px solid 主色` |
| 目录标题 | `font-size: 15px; font-weight: bold; color: 主色; letter-spacing: 1px` |
| 目录容器 | `background-color: 浅主色; padding: 16px 18px; border-radius: 8px` |
| 目录编号 | `color: 主色; font-weight: bold; font-family: 等宽; font-size: 13px` |
| 页脚 | `font-size: 12px; text-align: center; color: 次级文字色; border-top: 1px solid 分隔色` |

---

## Callout 高亮框

| 类型 | 图标 | 主色 | 底色 |
|------|------|------|------|
| `note` | 📘 | `#1a73e8` | `#eef4ff` |
| `tip` | 💡 | `#0f6e56` | `#eaf7f2` |
| `warn` | ⚠️ | `#b45309` | `#fff7e6` |
| `practice` | 🔧 | `#6d28d9` | `#f5f1ff` |

结构：底色 + 4px 左侧竖线 + 右侧圆角，内部用 `<br>` 分行。
标题用 `font-weight: bold` + 该类型的强调色。

---

## 移动端排版原则

- **正文最小 16px**，再小在手机上读不动。
- **行高 1.75** 是中文长文的最舒服值。
- **不要用纯黑 `#000`**，`#333` 或更柔和的深灰更护眼。
- **图片必须 `max-width: 100%`**，否则长图会撑破屏幕。
- **手机可视宽度约 375px**，超过 5 列的表格基本不能看，建议拆开。

---

## 怎么自己加一套主题

在 `scripts/convert_to_wechat.py` 的 `THEMES` 字典里加一项即可：

```python
"rose": {
    "label": "玫瑰 · 情感随笔",
    "accent": "#c2185b",        # 主色：标题、目录编号、引用竖线
    "accent_soft": "#fdf0f5",   # 浅主色：底色块、代码块背景
    "text": "#2f2a2c",          # 正文色
    "text_soft": "#7a6a70",     # 次级文字色：署名、页脚
    "rule": "#f0d5e0",          # 边框、分隔线颜色
    "h2_bar": True,             # h2 是否带左侧竖线
    "divider": "❋ ❋ ❋",        # 分隔符样式
    "radius": "10px",           # 圆角
},
```

然后把 `"rose"` 加进 `THEME_ORDER` 列表，运行 `--list-themes` 验证。

不想改代码也能微调主色：

```bash
python scripts/convert_to_wechat.py article.md --theme minimal --accent "#c0392b"
```

---

## CSS 白名单

只有下列属性会被写进最终 HTML，其他一律过滤掉：

```
color, background-color, font-size, font-weight, font-style, line-height,
text-align, margin, padding, border, border-left, border-top, border-bottom,
border-collapse, text-decoration, display, vertical-align, max-width, width,
height, font-family, letter-spacing, text-indent, overflow,
border-radius, white-space, word-break, overflow-wrap
```

最后四项是相对基线文档的扩展——公众号编辑器实测支持，且对代码块和卡片的观感提升明显。
