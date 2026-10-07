# 公众号 HTML 限制完整清单

来源：starter kit 的 `references/wechat_restrictions.md`，经过实测校正与补充（校正项标 ⚠️）。

---

## 允许的 HTML 标签

```
p, h2, h3, ul, ol, li, span, img, a, table, tr, th, td, br
```

本技能额外保留 `hr`、`thead`、`tbody`、`strong`、`em` 作为**中间态**：
它们在清洗阶段会被转换成上表中的安全标签，不会出现在最终输出里。

---

## 禁止的 HTML 标签

| 标签 | 原因 | 处理方式 |
|------|------|---------|
| `h1` | 公众号把 h1 留给文章标题 | 降级为 `h2` |
| `div` | 渲染不可靠 | 改为 `p` |
| `script` | 安全策略，必定剥离 | 整段删除 |
| `style` | CSS 必须 inline | 整段删除（样式需写进 `style=""`） |
| `iframe` | 禁止外嵌 | 整段删除 |
| `video` / `audio` | 必须用公众号自带的视频/音频组件 | 删除，改为提示用户手动插入 |
| `svg` | 保存时必定消失 | 删除 |
| `form` / `input` / `button` | 禁止交互 | 删除 |
| `canvas` | 依赖 JS | 删除 |

---

## 禁止的 HTML 属性

| 属性 | 原因 | 处理方式 |
|------|------|---------|
| `class` | 公众号不支持 CSS 类 | 删除 |
| `id` | 不支持元素 ID | 删除 |
| `onclick` / `onload` 等 | 禁止 JS 事件 | 删除 |
| `data-*` | 无意义且可能触发清洗 | 删除 |
| `style` 以外的一切 | 只保留 `style` / `src` / `alt` / `href` / `colspan` / `rowspan` | 删除 |

---

## CSS 规则

### 必须 inline

```html
<!-- ✅ 正确 -->
<p style="font-size: 16px; color: #333;">正文</p>

<!-- ❌ 错误：公众号会整段剥离 -->
<style>p { font-size: 16px; }</style>
<p>正文</p>

<!-- ❌ 错误：公众号不认 class -->
<p class="body-text">正文</p>
```

### 允许的 CSS 属性

```
color, background-color, font-size, font-weight, font-style,
line-height, text-align, margin, padding, border, border-left,
border-collapse, text-decoration, display, vertical-align,
max-width, width, height, font-family, letter-spacing, text-indent, overflow,
border-radius ⚠️, white-space ⚠️, word-break ⚠️, overflow-wrap ⚠️
```

⚠️ 标记者为基线的限制文档未列出、但公众号编辑器**实测支持**的属性。
前四项是基线里缺的 `border-radius`，后三项是代码块换行所必需的。
如果你的发布环境出现异常，把 `scripts/convert_to_wechat.py` 里的 `ALLOWED_CSS`
中这四项删掉即可回到保守模式。

### 禁止的 CSS

- `position` `float` `flex` `grid` `z-index` `transform` —— 布局属性
- `animation` `transition` —— 动效
- `@media` —— 没有响应式断点
- `@font-face` —— 不能自定义字体

---

## 图片规则

| 方式 | 可用？ | 说明 |
|------|--------|------|
| `<img src="https://...">` | ⚠️ | URL 可访问才行；公众号可能重新托管，也可能直接丢图 |
| `<img src="data:image/png;base64,...">` | ✅ | 粘贴后公众号会自动上传到自己的 CDN |
| `<img src="data:image/jpeg;base64,...">` | ✅ | 同上，照片推荐这种 |
| `<img src="data:image/svg+xml;base64,...">` | ❌ | 保存后消失 |
| 内联 `<svg>...</svg>` | ❌ | 直接被剥离 |

**最佳实践**：图标、示意图用 PNG base64 内嵌；真实照片先上传公众号素材库再取 CDN 链接。

从 Word 文档提取的内嵌图片，本技能会自动转成 PNG/JPG base64 直接内嵌。

---

## 篇幅限制

| 限制项 | 数值 |
|--------|------|
| 单篇正文上限 | 约 20000 中文字 |
| 图片数量上限 | 100 张 |
| 单图大小上限 | 10 MB |
| 支持的图片格式 | PNG / JPG / GIF |
| GIF 大小上限 | 2 MB |

`scripts/check_wechat_html.py` 会自动统计中文字数并超限告警。

---

## 常见翻车原因

1. **保存后格式全乱** —— 用了禁止标签或非 inline CSS
2. **图片消失** —— SVG data URI，或外链图片失效
3. **行距/间距和预览不一样** —— 公众号合并 margin 的规则和浏览器不同，多用 `padding`
4. **代码块变成一行** —— 必须用 `p` + `white-space: pre-wrap`，不能用 `pre` / `code` 裸标签
5. **表格右边被截断** —— 公众号没有横向滚动；超过 5 列的表格请拆成多张
6. **中文和英文挤在一起** —— 开启中英文自动加空格（本技能默认开启）
7. **标题层级消失** —— h1 被降级是正常行为，公众号只有 h2/h3 两级

---

## 发布前检查清单

- [ ] 跑一遍 `check_wechat_html.py`，没有 `[错误]`
- [ ] 所有外链图片已上传到公众号素材库，或已改成 base64
- [ ] 中文字数未超 20000
- [ ] 手机预览：标题不换行难看、表格不溢出、图片清晰
- [ ] 摘要在 120 字以内（公众号摘要框有字数限制）
- [ ] 封面图已单独上传（封面不走正文排版）
