# wechat-publisher benchmark

| 用例 | with_skill | without_skill | 差值 |
|------|-----------|---------------|------|
| basic | 100% | 100% | +0% |
| themed | 100% | 50% | +50% |
| callouts | 100% | 75% | +25% |
| structure | 100% | 20% | +80% |
| sample-report | 100% | 40% | +60% |
| cjk-images | 100% | 50% | +50% |

## 总体

- **with_skill**：平均 100.0%（min 100% / max 100%）
- **without_skill**：平均 55.8%（min 20% / max 100%）
- **delta**：+0.44

## 分析（规则式 analyzer）

- 非区分性断言 14 条（两种配置都过，测的是基线也具备的基本功）：basic×4、themed×2、callouts×3、structure×1、sample-report×2、cjk-images×2 —— 下次迭代应把这些换成更难的判据
- 每个「用例 × 配置」的 3 次运行结果完全一致，方差为 0 —— 这是确定性脚本该有的样子，可复现性好；同时也意味着它对输入措辞不敏感（换成 LLM 执行就会有方差）
- 区分度最高的用例是 structure（+80%），最低的是 basic（+0%）—— 前者最能说明技能的价值，后者说明这条路径基线也能走通
- 技能平均每次多花 0.10 秒（with 1.58s vs without 1.48s），代价可以忽略
