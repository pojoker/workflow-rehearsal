# 海外公司新闻扩容：Kimi 最终交接

> 本文件是 `codex/overseas-news` 工作树中的只读交接清单，不替代主工作树
> `refs/CODEX-KIMI-COLLAB.md`。主账本仍实行 `next_writer` 单写者协议。

## 交付状态

```yaml
handoff_at: 2026-08-13
owner: codex
reviewer: kimi
status: implementation_complete_ack_pending
worktree: /Users/jowang/Downloads/workflow-rehearsal-overseas-news
branch: codex/overseas-news
base_commit_exclusive: 010ce5c8b38a3630ad08cd678e3c2741044843e0
implementation_head: acb03a6
commit_count: 12
push_or_merge_authorized: false
canonical_write: forbidden_and_verified
```

Kimi CLI 的本轮直接复核因计费周期额度返回 403，尚未形成 ACK。CodeBuddy 的两次
只读调用均未返回审计文本并已安全终止；不能记作“复核通过”。OpenCode 已完成只读审计，
结论为无阻断问题；其指出的“前瞻表述可能误挂成熟商业阶段”已在 `acb03a6` 加入机器闸门和
正反测试。以上工具均未改写工作树。

## 已完成范围

- 新增候选公司 64 家，全部完成分层：23 家晋级季度覆盖、31 家晋级事件监控、10 家保留在
  发现队列。
- 当前正式季度公司 37 家；共 158 条来源、70 条 legacy claim。每家公司都有四个不同季度
  槽；34 家四槽均可用，AAOI、Lumentum 与 AXT 的缺口保留为 `not_collected` 或
  `unavailable`，没有用预告、新闻或空白材料冒充季度覆盖。
- 当前事件监控 36 家；另有 10 条 `promoted` 历史身份记录只用于别名/并购去重，不重复计数。
- 当前发现队列 10 家；未给它们创建虚假季度槽或事件事实。
- 事件雷达 28 条：26 条 `asserted`、2 条 `corroborated`。同源联合稿按 `origin_group`
  去重；只有不同起源的独立来源支持才可提升为 `corroborated`。
- 46 个披露件中 38 个已完成锚点复核，8 个明确记为 `no_relevant_claims`；后者只表示在登记
  的复核范围内未提取到相关主张，不构成行业负面证据。
- 官网博客按内容权限分层：技术演示、公司叙事和商业披露不会自动升级为已验证事实。
- `volume_order`、`first_shipment`、`ramping`、`scaled` 等成熟商业阶段现在必须至少有一条
  非前瞻支持主张；纯前瞻表述和纯技术博客均不能单独支撑成熟阶段，混合的前瞻 + 事实证据合法。
- WorkBuddy 页面已接入季度覆盖、事件监控、发现队列、处理队列、原文短引、锚点、来源链接、
  `asserted/corroborated` 状态及 Guidance/Demo/Actual 区分。

## 数据边界

- 本工作包只写 `calls/**`、`CONTEXT.md`、`docs/adr/**` 和 `docs/research/**`；没有修改
  `tree.yaml`、`knowledge.yaml`、`points.csv`、`edges.csv`、`route_bom.csv`、
  `capability_details.csv`、`corpus/**` 或其他 canonical/语料文件。
- `calls` 只读引用当前 canonical 做节点定位；同 cell、同主题或 capability overlap 不得推导
  合作、竞争、供货、替代或卡点已解决。
- `calls/out/**` 是由事实 CSV 和确定性投影生成的版本化产物，不允许手改。当前 `calls all`
  生成 45 个文件。
- 实际 WorkBuddy 成品位于：
  `/Users/jowang/Workbuddy/2026-07-26-11-49-54/光模块产业链全景图_公司能力细化版.html`。

## 验收记录

在 `acb03a6` 使用项目解释器执行：

```bash
/Users/jowang/miniconda3/bin/python3 -B -m unittest discover -s calls/tests -q
# Ran 116 tests ... OK

/Users/jowang/miniconda3/bin/python3 -B -m calls check
# 37 companies / 158 sources / 70 claims
# 21 themes / 12 cross-checks / 9 commitments / 4 technology feedback rows
# 28 reviewed radar events; canonical references closed; no canonical file written

/Users/jowang/miniconda3/bin/python3 -B -m calls all
# rendered 45 files under calls/out

/Users/jowang/miniconda3/bin/python3 -B build_detailed_capability_report.py --html-only
# companies=88 capabilities=181 nodes=37

git diff --check
# passed
```

提交钩子的不变量 ①–⑪ 与 `--verify` 一致性检查也已通过。系统 Python 缺 PyYAML 会产生假
失败，复核时必须使用上面的 Miniconda 解释器或把它置于 `PATH` 首位。

OpenCode 的只读审计还核对了：64 家候选分层闭合、37×4 季度槽、36 家 active watch、
10 家发现队列互不混入、同源联合稿只计一个 origin、calls 对 canonical 只读、WorkBuddy 原文
入口存在。其余低优先级文案问题已在 `acb03a6` 修正。

## Kimi 回执动作

1. 只读核对 `010ce5c..acb03a6` 的 12 个线性提交，不要直接改本工作树文件。
2. 在主工作树协作账本中按 `next_writer=kimi` 写 ACK：记录复核 SHA、命令、结论和是否接受
   `calls/out/**` 作为版本化派生产物，然后把令牌交回 Codex。
3. 若需要集成，由用户/Kimi 明确选择 cherry-pick、merge 或继续保持双轨；当前没有 push、merge
   或改写主分支授权。
4. 集成后重跑本节命令，并确认 WorkBuddy 页面仍显示“季度公司 37 家 / 事件监控 36 家 /
   发现队列 10 家”。

任何新一轮海外公司扩容应从新的候选批次开始，继续遵守“广发现、严晋级、事件状态不覆盖历史、
第一方主张不自动变真”的规则。
