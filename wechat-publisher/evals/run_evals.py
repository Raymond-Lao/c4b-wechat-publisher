#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_evals.py — wechat-publisher 的 eval 执行与判分（skill-creator eval 流程）

按 skill-creator 的规范跑一轮完整 eval：

    evals/evals.json          用例定义（prompt / 预期 / 输入文件）
    → 每个用例跑两种配置
        with_skill     本技能包
        without_skill  EduSeed starter kit 的原版脚本（基线）
    → 每种配置跑 3 遍（用来观察方差）
    → 程序化判分，逐条给出 passed + evidence
    → 生成 grading.json / benchmark.json
    → 调 skill-creator 的 eval-viewer 生成审阅页

用法：
    python evals/run_evals.py --skill . \
        --baseline /path/to/c4b-wechat-publisher-starter/scripts/convert_to_wechat.py \
        --workspace ../wechat-publisher-workspace \
        --skill-creator /path/to/skill-creator

为什么用脚本判分而不是"看一眼"：判分标准必须可复现。
同一份输出，今天判成通过、明天判成不通过，这套 benchmark 就没有意义了。
"""

import argparse
import html as html_lib
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PY = sys.executable

VIEWER_REL = Path("eval-viewer") / "generate_review.py"
AGG_REL = Path("scripts") / "aggregate_benchmark.py"

# 用例 → 实际执行的命令参数。
# 这里必须和 evals.json 里的 prompt 对得上：prompt 说"用蓝色主题加目录"，
# 命令里就得真的带 --theme blue --toc，否则测的就不是同一件事。
CLI_ARGS = {
    0: [],
    1: ["--theme", "blue", "--toc"],
    2: [],
    3: [],
    4: [],
    5: [],
}

CSS_DECL = re.compile(r"[a-z-]+\s*:\s*[^;<>{}]{1,40};", re.I)


# ---------------------------------------------------------------- 判分工具


def visible(html):
    """剥掉标签与属性，只留读者真正看到的文字。"""
    return html_lib.unescape(re.sub(r"<[^>]*>", "", html))


def block_of(html, marker):
    """取第一个 style 里含 marker 的块级元素内容。"""
    m = re.search(r'<p style="[^"]*{}[^"]*">(.*?)</p>'.format(marker),
                  html, re.S)
    return m.group(1) if m else ""


def n_blocks(html, marker):
    return len(re.findall(r'<p style="[^"]*{}[^"]*"'.format(marker), html))


def bad_tags(html):
    low = html.lower()
    return [t for t in ("<h1", "<div", "<script", "<style", "<iframe")
            if t in low]


# ---------------------------------------------------------------- 逐条断言
#
# 每个 check 返回 (passed, evidence)。evidence 必须写"凭什么这么判"，
# 只写 True/False 的判分记录，事后没人能复核。


def c_out_nonempty(ctx):
    ok = ctx["ok"] and len(ctx["html"]) > 800
    return ok, "输出 {} 字节，退出码 {}".format(len(ctx["html"]), ctx["rc"])


def c_no_bad_tags(ctx):
    bad = bad_tags(ctx["html"])
    return not bad, ("违规标签: {}".format(bad) if bad
                     else "h1/div/script/style/iframe 均未出现")


def c_no_class(ctx):
    ok = "class=" not in ctx["html"]
    return ok, ("发现 class= 属性" if not ok else "无 class= 属性")


def c_no_css_leak(ctx):
    leaks = CSS_DECL.findall(visible(ctx["html"]))
    return not leaks, ("可见文字里出现 CSS 声明: {}".format(leaks[:3]) if leaks
                       else "可见文字中没有 CSS 声明泄漏")


def c_h2_accent(ctx):
    m = re.search(r'<h2[^>]*style="[^"]*color:\s*([#\w]+)', ctx["html"])
    if not m:
        return False, "没有找到带 color 的 h2"
    color = m.group(1).lower()
    return color == "#1a73e8", "h2 主色 = {}".format(color)


def c_meta_shown(ctx):
    vis = visible(ctx["html"])
    missing = [x for x in ("李瑞翔", "演示同一份稿子在不同配置下的输出差异")
               if x not in vis]
    return not missing, ("缺少 {}".format(missing) if missing
                         else "作者署名与摘要都出现在开头")


def c_toc_lists_all(ctx):
    vis = visible(ctx["html"])
    if "目 录" not in vis and "目录" not in vis:
        return False, "没有生成目录块"
    heads = ["一、主题决定了文章的第一印象", "二、长文必须有目录", "三、元数据的三个字段"]
    counts = {h: vis.count(h) for h in heads}
    missing = [h for h, c in counts.items() if c < 2]
    return not missing, ("目录没列出: {}".format(missing) if missing
                         else "3 个 h2 都出现在目录中（各出现 ≥2 次）")


def c_toc_no_css(ctx):
    vis = visible(ctx["html"])
    hit = [k for k in ("padding-left", "font-size:", "max-width")
           if k in vis]
    return not hit, ("目录里泄漏了样式文本: {}".format(hit) if hit
                     else "目录里没有样式文本泄漏")


def c_four_callouts(ctx):
    n = n_blocks(ctx["html"], "border-left: 4px solid")
    titles = ["什么是高亮框", "带行内加粗的标题", "注意嵌套", "动手试试"]
    vis = visible(ctx["html"])
    missing = [t for t in titles if t not in vis]
    return n >= 4 and not missing, "带底色高亮块 {} 个，缺失标题 {}".format(
        n, missing or "无")


def c_callout_list_kept(ctx):
    vis = visible(ctx["html"])
    items = ["先写下你原本的目标", "再记录实际发生的结果", "最后对比两者的差距"]
    missing = [i for i in items if i not in vis]
    marks = all(m in vis for m in ("1.", "2.", "3."))
    if missing:
        return False, "列表项丢失: {}".format(missing)
    return marks, ("列表项齐全，编号标记 {}".format("在" if marks else "缺失"))


def c_callout_title_md(ctx):
    vis = visible(ctx["html"])
    return "**" not in vis and "行内加粗" in vis, (
        "正文里有裸露星号" if "**" in vis else "标题加粗正常解析，无裸露星号")


def c_callout_bodies(ctx):
    vis = visible(ctx["html"])
    bodies = ["高亮框就是带底色和左侧竖线的强调块",
              "标题里的 markdown 加粗也应该正常渲染",
              "高亮框里不要放 HTML 标签",
              "做完之后，你会发现问题通常不在执行力上"]
    missing = [b for b in bodies if b not in vis]
    return not missing, ("缺少正文: {}".format(missing) if missing
                         else "4 个高亮框的正文全部保留")


def c_hr_kept(ctx):
    vis = visible(ctx["html"])
    ok = "· · ·" in vis or "— — —" in vis
    return ok, ("分隔线可见" if ok
                else "分隔线消失（hr 被吞掉，基线缺陷 1 复现）")


def c_quote_multiline(ctx):
    blk = block_of(ctx["html"], "border-left")
    if not blk:
        return False, "没有找到引用块"
    brs = blk.count("<br")
    return brs >= 2, "引用块内换行符 {} 个（需要 ≥2）".format(brs)


def c_quote_bold(ctx):
    blk = block_of(ctx["html"], "border-left")
    ok = "font-weight: bold" in blk
    return ok, ("引用块内加粗保留" if ok else "引用块内的加粗丢失")


def c_code_newlines(ctx):
    blk = block_of(ctx["html"], "white-space: pre-wrap")
    if not blk:
        return False, "没有找到代码块"
    brs = blk.count("<br")
    return brs >= 4, "代码块内换行符 {} 个（需要 ≥4）".format(brs)


def c_table_kept(ctx):
    ok = "<table" in ctx["html"] and "常见故障" in visible(ctx["html"])
    return ok, ("表格保留且表头内容在" if ok else "表格丢失")


def c_docx_all_text(ctx):
    """内容保真：Word 里出现的每一段文字都要还在。

    这里刻意不数 <p> 个数 —— 基线把列表项压成普通段落，<p> 反而更多，
    数段落会把"丢结构"判成"更完整"。判内容要比判标签形态可靠。
    """
    vis = visible(ctx["html"])
    needed = ["Word 转换测试", "这是一段普通正文，包含加粗内容。", "加粗片段",
              "和斜体片段", "二级小节", "无序一", "无序二", "有序一", "有序二",
              "这是一段引用文字", "能力", "状态", "主题", "已支持", "Callout"]
    missing = [x for x in needed if x not in vis]
    return not missing, ("丢失内容: {}".format(missing) if missing
                         else "文档 15 处文字全部保留")


def c_docx_lists(ctx):
    h = ctx["html"]
    li = len(re.findall(r"<li[\s>]", h))
    has = "<ul" in h and "<ol" in h
    return li >= 4 and has, "li {} 个，ul/ol {}".format(
        li, "都在" if has else "缺失（列表被压成普通段落）")


def c_docx_table(ctx):
    ok = "<table" in ctx["html"] and "已支持" in visible(ctx["html"])
    return ok, ("表格保留且单元格内容在" if ok else "表格丢失")


def c_cjk_spaced(ctx):
    vis = visible(ctx["html"])
    missing = [x for x in ("用 Python", "2026 年") if x not in vis]
    return not missing, ("没补空格：{}".format(missing) if missing
                         else "「用 Python」「2026 年」都已补空格")


def c_code_untouched(ctx):
    h = ctx["html"]
    bad = "range( 3 )" in h or "range(3 )" in h
    ok = "range(3)" in h and not bad
    return ok, ("代码块被插入空格" if bad else "代码块内 range(3) 保持原样")


def c_image_embedded(ctx):
    ok = "data:image/png;base64" in ctx["html"]
    return ok, ("本地图片已嵌成 base64" if ok
                else "本地图片没嵌入（src 仍是本地路径）")


def c_image_maxwidth(ctx):
    m = re.search(r"<img[^>]*>", ctx["html"])
    if not m:
        return False, "没有 img 标签"
    ok = "max-width" in m.group(0)
    return ok, ("img 带 max-width" if ok else "img 缺 max-width")


CHECKS = {
    0: [c_out_nonempty, c_no_bad_tags, c_no_class, c_no_css_leak],
    1: [c_h2_accent, c_meta_shown, c_toc_lists_all, c_toc_no_css],
    2: [c_four_callouts, c_callout_list_kept, c_callout_title_md,
        c_callout_bodies],
    3: [c_hr_kept, c_quote_multiline, c_quote_bold, c_code_newlines,
        c_table_kept],
    4: [c_out_nonempty, c_docx_all_text, c_docx_lists, c_docx_table,
        c_no_bad_tags],
    5: [c_cjk_spaced, c_code_untouched, c_image_embedded, c_image_maxwidth],
}


# ---------------------------------------------------------------- 执行


def find_skill_creator(explicit=None):
    cands = []
    if explicit:
        cands.append(Path(explicit))
    home = Path.home()
    cands += [
        home / ".workbuddy/plugins/marketplaces/codebuddy-plugins-official"
        / "external_plugins/skill-creator",
        home / ".workbuddy/plugins/cache/codebuddy-plugins-official"
        / "skill-creator",
    ]
    for c in cands:
        if (c / VIEWER_REL).is_file():
            return c
    return None


def prepare_inputs(skill_dir, eval_def, workdir):
    """把用例声明的输入文件（含同目录素材）复制到临时工作目录。"""
    first = None
    for rel in eval_def.get("files", []):
        relpath = Path(rel)
        src = skill_dir / relpath
        if not src.is_file():
            raise FileNotFoundError("缺少用例输入: {}".format(src))
        if first is None:
            first = relpath
        parent_rel = relpath.parent
        if parent_rel.name == "files":
            # 同一批样例整棵目录一起搬：图片这类素材靠相对路径引用，
            # 只搬 .md 会导致图片解析不到（这本身就是"图片处理"用例要测的东西）
            shutil.copytree(str(skill_dir / parent_rel),
                            str(workdir / parent_rel), dirs_exist_ok=True)
        else:
            dst = workdir / relpath
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(src), str(dst))
    return workdir / first if first else None


def build_cmd(config, skill_dir, baseline, src, out, eval_id, quiet=True):
    if config == "with_skill":
        cmd = [PY, str(skill_dir / "scripts" / "convert_to_wechat.py"),
               str(src), str(out)]
        if quiet:
            cmd.append("--quiet")
        cmd += CLI_ARGS.get(eval_id, [])
        return cmd
    # 基线脚本只接受 <input> <output>，没有命令行选项
    return [PY, str(baseline), str(src), str(out)]


def execute(skill_dir, baseline, eval_def, config, run_number, run_dir):
    workdir = Path(tempfile.mkdtemp(prefix="c4b_eval_"))
    out = workdir / "article.html"
    try:
        src = prepare_inputs(skill_dir, eval_def, workdir)
        cmd = build_cmd(config, skill_dir, baseline, src, out, eval_def["id"])
        started = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              cwd=str(workdir), timeout=180)
        seconds = time.perf_counter() - started

        html = out.read_text(encoding="utf-8") if out.exists() else ""
        ctx = {"html": html, "rc": proc.returncode,
               "stdout": proc.stdout or "", "stderr": proc.stderr or "",
               "ok": proc.returncode == 0 and bool(html)}

        assertions = []
        for i, fn in enumerate(CHECKS[eval_def["id"]]):
            try:
                passed, evidence = fn(ctx)
            except Exception as exc:  # noqa: BLE001
                passed, evidence = False, "判分异常: {}: {}".format(
                    type(exc).__name__, exc)
            assertions.append({
                "text": _CHECK_TEXT[eval_def["id"]][i],
                "passed": passed, "evidence": evidence})

        passed = sum(1 for a in assertions if a["passed"])
        total = len(assertions)

        outputs = run_dir / "outputs"
        outputs.mkdir(parents=True, exist_ok=True)
        if out.exists():
            shutil.copyfile(str(out), str(outputs / "article.html"))
        (outputs / "stdout.txt").write_text(
            "$ {}\n\n[exit {}]  {:.2f}s\n\n--- stdout ---\n{}\n"
            "--- stderr ---\n{}\n".format(
                " ".join(Path(c).name if i < 3 else c for i, c in enumerate(cmd)),
                proc.returncode, seconds, proc.stdout or "", proc.stderr or ""),
            encoding="utf-8")

        grading = {
            "expectations": assertions,
            "summary": {"passed": passed, "failed": total - passed,
                        "total": total,
                        "pass_rate": round(passed / total, 4) if total else 0.0},
            "execution_metrics": {
                "tool_calls": {"executor": 1, "grader": len(assertions)},
                "total_tool_calls": 1 + len(assertions),
                "total_steps": 1,
                "files_created": sorted(p.name for p in outputs.iterdir()),
                "errors_encountered": 1 if proc.returncode else 0,
                "output_chars": len(html),
                "transcript_chars": len(proc.stdout or ""),
            },
            "timing": {"total_duration_seconds": round(seconds, 3)},
            "user_notes_summary": {
                "uncertainties": ([w for w in (proc.stdout or "").split("\n")
                                   if "[图片]" in w or "[警告]" in w]
                                  if proc.stdout else []),
                "needs_review": [],
                "workarounds": [],
            },
        }
        (run_dir / "grading.json").write_text(
            json.dumps(grading, ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "timing.json").write_text(
            json.dumps({"total_duration_seconds": round(seconds, 3),
                        "total_tokens": 0}, indent=2), encoding="utf-8")
        meta = {"eval_id": eval_def["id"], "eval_name": eval_def["name"],
                "prompt": eval_def["prompt"],
                "expectations": eval_def["expectations"],
                "configuration": config, "run_number": run_number}
        (run_dir / "eval_metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return grading, run_number
    finally:
        shutil.rmtree(str(workdir), ignore_errors=True)


# 断言文本（与 evals.json 的 expectations 顺序一一对应）
_CHECK_TEXT = {
    0: ["输出了非空的 HTML 文件",
        "输出里不含 h1 / div / script / style / iframe",
        "输出里不含 class= 属性",
        "剥掉标签后的可见文字里没有泄漏的 CSS 声明"],
    1: ["h2 主色是该主题的蓝色（#1a73e8）",
        "开头出现作者署名与摘要文字",
        "目录列出了全部 3 个 h2 小标题",
        "目录里没有把 padding-left 之类的 CSS 文本泄漏出来"],
    2: ["4 个高亮框都被渲染成带背景色的块",
        "practice 框里的 3 条有序列表文字全部保留",
        "高亮框标题里的 ** 加粗正常解析，没有裸露星号",
        "剥掉标签后仍能看到全部 4 个框的正文内容"],
    3: ["分隔线被保留为可见的分隔符（不是整条消失）",
        "引用块保留多行换行，没有被压成一行",
        "引用块里的加粗没有丢失",
        "代码块保留至少 4 行换行",
        "表格被保留下来"],
    4: ["输出了非空的 HTML 文件",
        "Word 里的每一段文字（标题/正文/列表项/引用/表格单元格）都出现在输出里",
        "列表项保留为 ul/ol + li，没有被压成普通段落",
        "表格保留为 table 元素",
        "不含 h1 / div / script / style 等违规标签"],
    5: ["中文与英文/数字之间补了空格（用 Python / 2026 年）",
        "代码块内的 range(3) 没有被插入空格",
        "本地图片被嵌入为 data:image/png;base64",
        "img 标签带 max-width 样式"],
}


def analyze(iteration):
    """
    分析师一遍（对应 skill-creator 的 analyzer 步骤）：找
      · 非区分性断言 —— 两种配置都过，说明它测的是基本功
      · 高方差用例 —— 同一配置多次运行结果飘，可能是 flaky
      · 时间/体积代价 —— 技能多花多少换回多少
    """
    notes = []
    runs = []
    for g in sorted(iteration.glob("eval-*/*/run-*/grading.json")):
        rel = g.relative_to(iteration).parts  # (eval-…, config, run-…, grading.json)
        try:
            data = json.loads(g.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        runs.append({"eval": rel[0], "config": rel[1], "data": data})
    if not runs:
        return ["没有找到任何 grading.json，无法分析。"]

    # 1) 非区分性断言（按「用例 + 断言序号」聚合，避免同名断言互相污染）
    keyed = {}
    for r in runs:
        for i, a in enumerate(r["data"]["expectations"]):
            slot = keyed.setdefault((r["eval"], i),
                                    {"text": a["text"], "with_skill": [],
                                     "without_skill": []})
            slot[r["config"]].append(a["passed"])
    per_eval_non_disc = {}
    for (ev, _i), v in sorted(keyed.items()):
        if v["with_skill"] and v["without_skill"] \
                and all(v["with_skill"]) and all(v["without_skill"]):
            per_eval_non_disc[ev] = per_eval_non_disc.get(ev, 0) + 1
    if per_eval_non_disc:
        total_nd = sum(per_eval_non_disc.values())
        notes.append(
            "非区分性断言 {} 条（两种配置都过，测的是基线也具备的基本功）：{} —— "
            "下次迭代应把这些换成更难的判据".format(
                total_nd,
                "、".join("{}×{}".format(k.split("-", 2)[-1], v)
                          for k, v in per_eval_non_disc.items())))

    # 2) 每个「用例 × 配置」内的多轮方差
    groups = {}
    for r in runs:
        groups.setdefault((r["eval"], r["config"]), []).append(
            r["data"]["summary"]["pass_rate"])
    flaky = [(k[0].split("-", 2)[-1] + "/" + k[1], vals)
             for k, vals in groups.items()
             if len(vals) > 1 and statistics.pstdev(vals) > 0.10]
    if flaky:
        for name, vals in flaky:
            notes.append("{} 的多轮通过率不一致（{}）—— 可能是 flaky".format(
                name, ["{:.0%}".format(v) for v in vals]))
    else:
        notes.append("每个「用例 × 配置」的 3 次运行结果完全一致，方差为 0 —— "
                     "这是确定性脚本该有的样子，可复现性好；"
                     "同时也意味着它对输入措辞不敏感（换成 LLM 执行就会有方差）")

    # 3) 差距最大的用例
    per_eval = {}
    for (ev, cfg), vals in groups.items():
        per_eval.setdefault(ev, {})[cfg] = statistics.mean(vals)
    gaps = [(ev.split("-", 2)[-1], v.get("with_skill", 0) - v.get("without_skill", 0))
            for ev, v in per_eval.items() if v.get("without_skill") is not None]
    if gaps:
        gaps.sort(key=lambda x: -x[1])
        top, bottom = gaps[0], gaps[-1]
        notes.append("区分度最高的用例是 {}（{:+.0%}），最低的是 {}（{:+.0%}）—— "
                     "前者最能说明技能的价值，后者说明这条路径基线也能走通".format(
                         top[0], top[1], bottom[0], bottom[1]))

    # 4) 时间代价
    ws = [r["data"]["timing"]["total_duration_seconds"] for r in runs
          if r["config"] == "with_skill"]
    wo = [r["data"]["timing"]["total_duration_seconds"] for r in runs
          if r["config"] == "without_skill"]
    if ws and wo:
        notes.append("技能平均每次多花 {:.2f} 秒（with {:.2f}s vs without {:.2f}s），"
                     "代价可以忽略".format(
                         statistics.mean(ws) - statistics.mean(wo),
                         statistics.mean(ws), statistics.mean(wo)))
    return notes


def main():
    ap = argparse.ArgumentParser(description="跑 wechat-publisher 的 eval")
    ap.add_argument("--skill", default=str(SKILL_DIR))
    ap.add_argument("--baseline", required=True,
                    help="starter kit 原版 convert_to_wechat.py 的路径")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--iteration", type=int, default=1)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--skill-creator", default=None)
    ap.add_argument("--report", default=None, help="审阅页 HTML 输出路径")
    args = ap.parse_args()

    skill_dir = Path(args.skill).resolve()
    baseline = Path(args.baseline).resolve()
    if not baseline.is_file():
        print("[!] 找不到基线脚本: {}".format(baseline))
        return 1

    eval_defs = json.loads(
        (skill_dir / "evals" / "evals.json").read_text(encoding="utf-8"))["evals"]
    for e in eval_defs:
        e["name"] = re.sub(r"[^a-z0-9]+", "-",
                           e["files"][0].split("/")[-1].rsplit(".", 1)[0]
                           if e.get("files") else "eval-{}".format(e["id"])).strip("-")

    workspace = Path(args.workspace).resolve()
    iteration = workspace / "iteration-{}".format(args.iteration)
    if iteration.exists():
        shutil.rmtree(str(iteration), ignore_errors=True)

    print("=" * 62)
    print("wechat-publisher eval  |  iteration {}  |  每配置 {} 遍".format(
        args.iteration, args.runs))
    print("  with_skill    = {}".format(skill_dir / "scripts" / "convert_to_wechat.py"))
    print("  without_skill = {}".format(baseline))
    print("=" * 62)

    matrix = []
    for e in eval_defs:
        for config in ("with_skill", "without_skill"):
            for run_number in range(1, args.runs + 1):
                run_dir = (iteration / "eval-{}-{}".format(e["id"], e["name"])
                           / config / "run-{}".format(run_number))
                run_dir.mkdir(parents=True, exist_ok=True)
                grading, _ = execute(skill_dir, baseline, e, config,
                                     run_number, run_dir)
                matrix.append((e["id"], e["name"], config, run_number, grading))
                s = grading["summary"]
                print("  eval-{} {:<14s} {:<14s} run-{}  {}/{}  {:.2f}s".format(
                    e["id"], e["name"], config, run_number, s["passed"],
                    s["total"], grading["timing"]["total_duration_seconds"]))

    # 写 eval_metadata.json 到用例目录（aggregate_benchmark.py 要读它拿 eval_id）
    for e in eval_defs:
        d = iteration / "eval-{}-{}".format(e["id"], e["name"])
        (d / "eval_metadata.json").write_text(
            json.dumps({"eval_id": e["id"], "eval_name": e["name"],
                        "prompt": e["prompt"],
                        "expectations": e["expectations"]},
                       ensure_ascii=False, indent=2), encoding="utf-8")

    sc = find_skill_creator(args.skill_creator)
    bench = iteration / "benchmark.json"
    if sc:
        print("\n[skill-creator] {}  →  {} ".format(sc, AGG_REL))
        subprocess.run([PY, str(sc / AGG_REL), str(iteration),
                        "--skill-name", "wechat-publisher",
                        "--skill-path", str(skill_dir)],
                       check=False)
    else:
        print("\n[!] 没找到带 eval-viewer 的 skill-creator，跳过官方聚合与审阅页")

    if bench.exists():
        data = json.loads(bench.read_text(encoding="utf-8"))
        data["metadata"]["runs_per_configuration"] = args.runs
        data["metadata"]["executor_model"] = "确定性脚本（非 LLM 执行）"
        data["metadata"]["analyzer_model"] = "规则式分析（run_evals.py:analyze）"
        data["notes"] = analyze(iteration)
        bench.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        print("\nbenchmark 摘要")
        for cfg, stats in data["run_summary"].items():
            if cfg == "delta":
                continue
            print("  {:<15s} 通过率 {:.1%}".format(
                cfg, stats["pass_rate"]["mean"]))
        print("  delta          {}".format(
            data["run_summary"].get("delta", {}).get("pass_rate", "—")))
        (iteration / "benchmark.md").write_text(
            render_benchmark_md(data, eval_defs), encoding="utf-8")

    if sc and (sc / VIEWER_REL).is_file():
        report = Path(args.report) if args.report else \
            (workspace / "eval_report.html")
        subprocess.run([PY, str(sc / VIEWER_REL), str(workspace),
                        "--skill-name", "wechat-publisher",
                        "--benchmark", str(bench),
                        "--static", str(report)], check=False)
        print("审阅页: {}".format(report))

    total = len(matrix)
    ok = sum(1 for _, _, _, _, g in matrix if g["summary"]["pass_rate"] == 1.0)
    print("\n完成：{} 次运行，其中 {:.0%} 全量通过".format(total, ok / total))
    return 0


def render_benchmark_md(data, eval_defs):
    names = {e["id"]: e["name"] for e in eval_defs}
    lines = ["# wechat-publisher benchmark", "",
             "| 用例 | with_skill | without_skill | 差值 |",
             "|------|-----------|---------------|------|"]
    per = {}
    for r in data["runs"]:
        per.setdefault(r["eval_id"], {}).setdefault(
            r["configuration"], []).append(r["result"]["pass_rate"])
    for eid in sorted(per):
        w = per[eid].get("with_skill", [0])
        wo = per[eid].get("without_skill", [0])
        mw, mwo = statistics.mean(w), statistics.mean(wo)
        lines.append("| {} | {:.0%} | {:.0%} | {:+.0%} |".format(
            names.get(eid, eid), mw, mwo, mw - mwo))
    s = data["run_summary"]
    lines += ["", "## 总体", ""]
    for cfg in ("with_skill", "without_skill"):
        if cfg in s:
            st = s[cfg]["pass_rate"]
            lines.append("- **{}**：平均 {:.1%}（min {:.0%} / max {:.0%}）".format(
                cfg, st["mean"], st["min"], st["max"]))
    lines.append("- **delta**：{}".format(s.get("delta", {}).get("pass_rate", "—")))
    lines += ["", "## 分析（规则式 analyzer）", ""]
    lines += ["- " + n for n in data.get("notes", [])]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
