# 光模块研究主线削减设计

- 日期：2026-09-02
- 审计基线：`d0ab510d97e197cfba5de6c2f18d3b5a664b12de`
- 新主线基点：`codex/industry-chain-v2@227f5037b73669aa490097924b273c0295698766`
- 本文状态：削减设计；不授权实现新功能、关系类型或状态

## 0. 一页结论

`d0ab510` 应冻结为：

> 已证明 as-of relation reducer 和跨构建状态响应的实验。

它证明了一个窄机制：给定预先指定的 Program、Lifecycle Stage 和 `as_of`，关系投影可以从
`open` 变为 `satisfied`，并在测试撤回后变为 `reopened`。该证明应留在固定提交和实验分支中，
但不应成为光模块研究主线的基础设施。

削减的核心依据不是代码行数本身，而是生产活性与领域产出不匹配：

| 指标 | `d0ab510` 生产投影 |
|---|---:|
| relation assertions | 405 |
| `company_has_capability_at` | 271 |
| derived `capability_matches_route` | 113 |
| `route_requires_capability` | 11 |
| `product_has_lifecycle_stage` | 10 |
| slot states | 386，全部 `supported` |
| explicit reviewed assertions | 0 |
| 生产 withdrawal / contradiction | 0 / 0 |
| relation leads | 83 |
| formal questions | 1 个硬编码 lifecycle query |

三份合同约 345 行，两个执行脚本约 5,300 行，两份专项测试约 2,700 行。复杂度主要用于 slot
identity、comparison surface、receipt、manifest、snapshot lineage 和 recursive replay；这些机制没有
直接回答本轮三个领域问题，也没有生产中的非平凡状态调用方。

因此新主线采取以下决策：

1. 从 `codex/industry-chain-v2@227f503` 开新分支，不 cherry-pick `29cc861`、`4150e55`、
   `eec30f7` 或 `d0ab510`。
2. 保留现有 canonical ledgers、人工问题导航、`knowledge.yaml#why_links` 和 calls 事件账本。
3. 只重做一个小型、机械、只读的 relation-lead 投影；它输出引用，不计算事实状态。
4. 正式研究问题由人选择；答案由人审核后写回既有 canonical，不自动关闭或重开。
5. d0 pilot 的代码、合同、测试和输出留在 Git 历史/实验分支，不复制到新主线。

目标主线不是“通用研究图引擎”，而是：

```text
canonical ledgers
    -> 机械类型化视图 / leads
    -> 人工选择问题
    -> 研究与审核
    -> 写回原 canonical
    -> 既有页面投影
```

## 1. Pilot 冻结边界

### 1.1 冻结定义

固定实验：

- commit：`d0ab510d97e197cfba5de6c2f18d3b5a664b12de`
- branch：`codex/research-graph-closure-pilot-fix-codebuddy`
- 证明对象：as-of relation projection、跨 build question identity、测试 revision 响应
- 不证明：问题自然生长、产品对象发现、通用 reviewed writeback、正式问题生命周期

### 1.2 不再向 pilot 增加

- relation type；
- question type；
- product registry；
- actor role；
- semantic entailment；
- UI；
- 新的 snapshot schema、event-sourcing 能力或兼容层。

如需复查实验，直接 checkout 固定提交。新主线只保留一篇短说明和提交链接，不复制实验实现。

## 2. 文件级 keep / archive / replace / delete 表

分类含义：

- `retain_in_domain_core`：直接服务领域答案，且已有真实调用方；
- `retain_as_experimental_reference`：实验结论有价值，但实现不进入主线；
- `replace_with_simpler_implementation`：保留领域意图，丢弃通用机制；
- `delete_or_do_not_merge`：不从 pilot 合入新主线。

| 文件 | 分类 | 直接帮助的领域问题 | 生产数据是否经过 | fixture-only 部分 | 删除损失 | 替代方式 |
|---|---|---|---|---|---|---|
| `tree.yaml`、`edges.csv` | `retain_in_domain_core` | A 的组件、接口和物理连接 | 是，既有页面和校验持续读取 | 无 | 会直接丢失物理骨架 | 原位保留 canonical，不迁移 |
| `route_bom.csv` | `retain_in_domain_core` | A 的 800G DR8 BOM；B 的 RB004 电职责边界 | 是 | 无 | 会丢失路线链及标准锚 | 原位保留 canonical；机械视图只引用 RB ID |
| `points.csv` | `retain_in_domain_core` | C 的公司能力/产品族证据与 lead 来源 | 是 | 无 | 会丢失已过判定闸的公司证据 | 原位保留 canonical；不复制 quote |
| `knowledge.yaml`、`research_questions.yaml` | `retain_in_domain_core` | B 的 WHY；A/B/C 的人工问题导航和答案回填 | 是，现有 reader/scan 使用 | `why_links` 当前为空不是 fixture | 会丢失人工研究主线 | 继续使用现有 KN/WQ seam；不建立自动 lifecycle |
| `calls/*.csv` | `retain_in_domain_core` | C 的 disclosure/claim/event/stage 证据 | 是，calls validator/renderer 使用 | 无 | 会丢失海外产品和事件证据 | 原位保留各自 canonical；不复制成 assertion index |
| `contracts/relation_types.yaml` | `replace_with_simpler_implementation` | A 的 route/cell 映射；C 的能力 overlap 边界 | 五类均有 schema；实际只有 capability、route requirement、match、lifecycle 有行 | reviewed、withdrawal、conflict 语义仅 fixture 走到非空分支 | 丢失统一 Slot/Assertion 本体和时态比较定义 | 只保留 3 个机械视图名：`route_has_bom_group`、`bom_group_maps_to_cell`、`company_has_cell_evidence`；overlap 为 derived lead，不设 slot state |
| `contracts/relation_adapters.yaml` | `replace_with_simpler_implementation` | A/C 的 points × route_bom 读取规则 | points、route_bom、calls 均真实读取 | receipt registry、extra registry、FRO 反例、精确 profile 门主要由 fixture 驱动 | 丢失 frozen profile 和适配器版本摘要 | 用一个小型 `relation_views.yaml` 声明源文件与列映射；route identity 直接使用 canonical `route_item_id`，不另造 exact profile |
| `contracts/question_generation_rules.yaml` | `delete_or_do_not_merge` | 不直接回答 A/B/C；只生成 lead 或硬编码 Taurus query | lifecycle rule 真实输出 1 行；route rule 正式问题为 0 | route formal lifecycle、reopen 条件主要由 fixture 验证 | 丢失自动状态查询模板 | 保留 `research_questions.yaml` 的人工策划问题；machine lead 永不自动晋升 formal question |
| `relation_assertions.yaml` | `delete_or_do_not_merge` | 理论上服务 C，实际上为空 | 否，`assertions: []` | 合法/非法 reviewed assertion 均为 fixture | 不损失生产事实 | 人工研究结果写回 `knowledge.yaml`、`points.csv`、`calls/*.csv` 或 `why_links` 的原 canonical 槽 |
| `tools/research/build_relation_index.py` | `replace_with_simpler_implementation` | A 的机械组件链、C 的候选 overlap | 读取 271 points、route_bom 与 10 lifecycle assertions | receipt、revision、conflict、extra registry 的非平凡分支主要在测试 | 丢失通用 assertion index、slot state 和 lifecycle adapter | 新建单一深模块 `build_relation_leads.py`：读取 canonical，返回带 source refs 的 lead 列表；不生成 assertion/slot/manifest |
| `tools/research/recompute_question_state.py` | `retain_as_experimental_reference` + `delete_or_do_not_merge` | 不直接回答 A/B/C；证明 as-of reducer | Taurus A/B 使用真实 calls；C 为测试撤回 | recursive replay、伪造防护、route product binding、conflict/reopen 大量依赖 fixture | 丢失跨 build 自动状态响应实验 | Git 固定提交即可替代；主线由人工复核当前证据，Git history 记录变化 |
| `tools/research/validate_reviewed_assertions.py` | `delete_or_do_not_merge` | 理论上验证 C 的 reviewed 关系，生产无 assertion | 生产只验证空集合 | 所有正负 reviewed gate 用例都是 fixture | 不损失生产写入能力 | 使用现有 calls validator、point 判定闸和人工 promotion review；不新建 receipt registry |
| `scan.py` 的 relation gate ⑮ | `delete_or_do_not_merge` | 不直接回答 A/B/C | 只对空 `relation_assertions.yaml` 通过 | 非空语义均由测试构造 | 丢失空 sidecar 的总闸检查 | 新分支从 227f503 开始，天然没有该 gate；保留原有 canonical 校验 |
| `tests/research/test_relation_graph_closure.py` | `retain_as_experimental_reference` + `delete_or_do_not_merge` | 验证 pilot 内部合同，不验证用户最终答案 | 少量生产读取；大部分构造 assertion/registry | reviewed、withdrawal、supersession、comparison、product binding 等 | 丢失 pilot 防回归能力 | 实验分支保留；新主线只写三个垂直切片的 observable outcome tests |
| `tests/research/test_relation_graph_closure_latest.py` | `retain_as_experimental_reference` + `delete_or_do_not_merge` | 验证 Taurus as-of A/B/C | A/B 使用真实 calls，C 为临时 withdrawal | history tamper 和 future cause 为 fixture | 丢失跨 build 实验的可复现证明 | 固定提交和报告足够；主线不承诺该行为 |
| `tests/fixtures/research_graph/*` | `delete_or_do_not_merge` | 不回答 A/B/C | 否 | 全部 | 只损失 pilot 合同反例 | 不替代；主线测试使用真实 RB、point、claim IDs |
| `out/relation_assertion_index.jsonl` | `delete_or_do_not_merge` | 间接调试 A/C | 是，405 行 | 无，但只是生成态 | 丢失可检查的统一行表 | 需要时直接从 canonical 构建短 lead；不保存完整 assertion 副本 |
| `out/relation_slot_states.jsonl` | `delete_or_do_not_merge` | 不直接回答 A/B/C | 是，386 行但全部 `supported` | 非 supported 状态只在 fixture | 丢失当前状态调试表 | 直接读取 canonical 当前字段；历史由 Git 和原账本日期保留 |
| `out/generated_diagnostic_questions.jsonl` | `delete_or_do_not_merge` | 不回答本轮三切片；仅 Taurus sampling | 是，1 个硬编码 query | reopen 只在测试 snapshot | 丢失实验问题快照 | 人工问题仍在 `research_questions.yaml`；答案链接由人工审核 |
| `out/relation_leads.jsonl` | `replace_with_simpler_implementation` | C 的候选研究入口 | 是，83 个 overlap | 无 | 丢失“哪些公司与 route cells 有交集”的可见性 | 重建成更小的 `relation_leads.jsonl`，身份用 `route_item_id + company + cell_id`，不使用 route profile、actor role、slot 或状态 |
| `out/relation_lead_funnel.json` | `delete_or_do_not_merge` | 不直接回答领域问题；83→83 是重复计数 | 是 | product/formal/reviewed 三层为空 | 丢失 funnel 诊断 | CLI 结束时打印 `lead_count` 与按 cell/route_item 计数即可；不保存状态漏斗 |
| `docs/plans/2026-09-research-graph-closure-pilot.md`、pilot reports/reviews | `retain_as_experimental_reference` | 解释为何停止 engine 路线 | 文档引用生产运行 | 含 fixture 验收 | 丢失决策历史 | 固定分支保留；新主线只放一篇 experiment pointer |

## 3. 核心函数分类

### 3.1 `build_relation_index.py`

下表显式覆盖全部顶层函数；同组函数具有相同削减结论。

| 函数组 | 分类 | 生产情况 | 删除损失与替代 |
|---|---|---|---|
| `load_yaml`、`load_csv`、`canonical_json`、`stable_id` | `replace_with_simpler_implementation` | CLI/测试真实使用 | 新 lead builder 内保留局部读取和 deterministic lead ID；不保留兼容 API |
| `parse_iso_datetime`、`normalized_time` | `retain_as_experimental_reference` | lifecycle projection 使用 | 主线不计算 as-of slot；日期继续由 calls/points 自有 validator 校验 |
| `relation_slot_identity`、`slot_identity`、`_field_value`、`comparison_values` | `retain_as_experimental_reference` | 所有 index 行经过 | 主线删除 Slot identity；lead identity 只由源行 ID 组合产生 |
| `validate_relation_contract`、`make_assertion` | `retain_as_experimental_reference` | 所有 405 行经过 | 主线不创建 assertion 对象；机械视图直接输出 source refs |
| `_canonical_company` | `replace_with_simpler_implementation` | points/calls 适配使用 | 公司名沿用 canonical ledger；若确有 alias，只在现有 universe/映射表解决 |
| `_load_extra_registry`、`ReferenceRegistry.__init__`、`build_reference_registry` | `delete_or_do_not_merge` | production 解析现有 refs；extra registry 为空 | 不再建立通用对象 registry；各 ledger validator 对自己引用负责 |
| `build_receipt_registry`、`derive_origin_group`、`derive_origin_groups` | `delete_or_do_not_merge` | production receipt 为空 | 不建立 receipt/origin 状态系统；人工审核记录留在研究包或原 ledger 字段 |
| `route_profile_identity_hash`、`validate_route_profiles`、`evaluate_requirement_group` | `retain_as_experimental_reference` | LPO profile 真实构建；FRO 无 requirements | 不把 broad BOM 冻结成 exact profile；A 使用 RB001–RB005，产品 exactness 由人工证据判断 |
| `adapt_points`、`adapt_route_requirements`、`derive_capability_matches` | `replace_with_simpler_implementation` | 271 / 11 / 113 行真实生成 | 保留机械 join 意图，改成 route-item/cell/company lead；禁止完整 BOM 或服务推断 |
| `adapt_calls` | `delete_or_do_not_merge` | 10 product-stage assertions | calls 已有 schema、validator、renderer；C 直接读 calls，不再复制一层 relation assertions |
| `validate_explicit_reviewed`、`adapt_explicit_assertions` | `delete_or_do_not_merge` | production sidecar 为空 | 删除不损失事实；人工 promotion 使用既有判定闸，不建立另一套审核门 |
| `_time_overlap`、`is_active_at_as_of`、`assertions_conflict`、`_same_comparison_surface`、`compute_slot_states` | `retain_as_experimental_reference` | production 只有 supporting，386 states 全 supported | 非平凡分支无生产调用；实验 commit 足够保留知识 |
| `_independent_origin_count`、`_computed_slot_id`、`_validate_revision_fields`、`validate_assertions`、`validate_withdrawals` | `delete_or_do_not_merge` | production revision/explicit 集为空 | 主线不承诺自动冲突/撤回；由人读当前证据及反证，Git 保存修订历史 |
| `build_relation_graph` | `replace_with_simpler_implementation` | 生产总入口 | 用一个 `build_relation_leads(root)` 外部 seam 取代；调用方只知道输入 canonical、输出 lead |
| `reducer_contract_compatibility`、`compute_build_manifest` | `delete_or_do_not_merge` | 每次 build 使用 | 不再有跨 build reducer 合同；输出记录生成时间和 source commit 即可，不作为状态依据 |
| `write_jsonl`、`parse_args`、`main` | `replace_with_simpler_implementation` | CLI 使用 | 新脚本保留一个 CLI 和确定性 JSONL 输出，不保留多模式参数 |

### 3.2 `recompute_question_state.py`

| 函数组 | 分类 | 生产情况 | 删除损失与替代 |
|---|---|---|---|
| `read_jsonl`、`read_index_with_manifest`、`_file_hash`、`_contract_ref`、`target_identity_hash` | `retain_as_experimental_reference` | question CLI 使用 | 主线不读取 assertion/slot snapshot；question ID 由人工 YAML 固定 |
| `_validate_manifest_shape`、`_require_same_build`、`_resolve_relative_ref`、`_validate_relation_artifacts`、`_assert_replayed_snapshot_matches`、`_require_query_matches_manifest` | `delete_or_do_not_merge` | d0 A/B 路径使用；tamper 分支由测试触发 | 丢失 snapshot 防伪；Git commit、原 ledger ID 和人工复核替代 |
| `PriorQuestionState.__init__`、`empty`、`_validate_history_manifest`、`from_snapshot`、`from_events`、`load`、`has_question`、`status_for`、`was_satisfied` | `retain_as_experimental_reference` + `delete_or_do_not_merge` | 真实 A/B 使用，C test withdrawal 使用 | 丢失跨 build reopen；主线明确不提供自动 question lifecycle |
| `actual_coverage_cells`、`project_group_cells`、`evaluate_coverage` | `delete_or_do_not_merge` | 83 companies 走过 partial overlap | 完整产业链 BOM 不是单公司准入门；改为逐格 overlap lead |
| `_identity_scope`、`bind_target_slot`、`candidate_product_refs` | `delete_or_do_not_merge` | production 没有 product registry，route formal questions 为 0 | 不建立 product registry；C 由人工确认具名 SKU 和证据对象 |
| `_profile_required_cells`、`_profile_unmatched_cells` | `delete_or_do_not_merge` | funnel/lead 使用 | 新 lead 只陈述 matched cell，不把 unmatched 解释为公司能力缺口 |
| `generate_relation_leads` | `replace_with_simpler_implementation` | 真实输出 83 leads | 保留“可发现 overlap”能力，去掉 profile、role、product、admission、state 字段 |
| `question_fingerprint`、`lifecycle_question_fingerprint` | `delete_or_do_not_merge` | Taurus query 使用 | question ID 与依赖由人策划，不由 reducer dedupe |
| `_qualified_supports`、`compute_resolution`、`transition_cause_assertion_ids` | `retain_as_experimental_reference` + `delete_or_do_not_merge` | production 只有单一 supporting path | 不自动计算 open/satisfied/reopened/conflicted |
| `generate_diagnostic_questions` | `delete_or_do_not_merge` | production 只生成硬编码 Taurus query | 人工从 leads 和研究议程挑问题，写入现有 question graph |
| `parse_args`、`main` | `delete_or_do_not_merge` | CLI 使用 | 不需要 question-state CLI；保留 lead builder CLI 即可 |

## 4. 新主线分支方案

### 4.1 分支关系

```text
codex/industry-chain-v2 @ 227f503
  └─ codex/domain-research-simplification-design   # 本文，纯设计
      └─ codex/domain-research-mainline            # 未来实施，需用户另行授权

codex/research-graph-closure-pilot-fix-codebuddy @ d0ab510
  └─ frozen experiment，不合并
```

### 4.2 合并策略

- 不 merge pilot 分支；
- 不 cherry-pick pilot 的任何实现提交；
- 只允许人工重写以下两个概念：
  1. `capability overlap` 必须叫 lead，不叫 route capability；
  2. generated output 只保存 canonical refs，不成为事实源。
- d0 的 Slot、Assertion、manifest、snapshot、question state 类型不得以“兼容”为由复制。

### 4.3 未来实施提交顺序（本轮不执行）

1. 冻结实验说明与三个垂直切片验收合同；
2. 实现机械 `relation_views.yaml + build_relation_leads.py + 1 个 outcome test`；
3. 先完成 A 的可读答案；
4. 人工完成 B 的 WHY 审核与写回；
5. 人工完成 C 的具名产品证据表；
6. 三个切片验收通过前，不扩展任何关系或问题类型。

## 5. 最小目录结构

保留现有 canonical 位置，不进行迁移：

```text
tree.yaml                         # 物理格与结构骨架 canonical
edges.csv                         # 物理连接 canonical
route_bom.csv                     # 路线/BOM canonical
points.csv                        # 公司能力证据 canonical
knowledge.yaml                    # KN 与人工 WHY canonical
research_questions.yaml           # 人工问题导航 canonical
calls/                            # 来源、claim、event、evidence、stage canonical

relation_views.yaml               # 未来：只声明机械映射，不保存事实
tools/research/
  build_relation_leads.py         # 未来：唯一新生成模块
tests/research/
  test_domain_slices.py           # 未来：只测 A/B/C 可观察答案和边界

docs/research/
  answers/                        # 人工审核后的领域答案/研究卡
  experiments/
    relation-reducer-d0ab510.md   # 只放固定提交、证明范围和停止理由

out/research/
  relation_leads.jsonl            # generated；可删除重建；非 canonical
```

不在新主线创建：

- `relation_assertions.yaml`；
- `relation_assertion_index.jsonl`；
- `relation_slot_states.jsonl`；
- `generated_diagnostic_questions.jsonl`；
- relation/question state contracts；
- product/receipt/origin registry。

## 6. 三个垂直切片

### A. 800G DR8 物理组件链

#### 用户最终看到的答案

800G DR8 是 8 路并行单模短距链路。当前账本支持的边界是：

1. 主机侧为 800GAUI-8 / 8×100G-class 电通道；
2. 发射链为 8 路 PAM4 光发射，光源可由离散激光器或 SiPh PIC 实现，经封装进入光引擎；
3. 接收链为 8 路探测器加 TIA；
4. 模块电链可以是 DSP/Retimer，也可以是线性模拟链；DR8 标准本身不等于 LPO；
5. 外围包含 MPO/光纤阵列、透镜、PCB、结构与散热；
6. SiPh、LPO、front-panel pluggable 是不同选择轴，不能互相自动推出。

答案必须显示 `RB001–RB005` 及 cell refs，不显示公司名单。

#### 数据、缺失与最小结构

| 项 | 内容 |
|---|---|
| 读取账本 | `route_bom.csv#RB001–RB005`、`tree.yaml` 的 C1/C3/C4/C5/P1/D7/D9/B1/B2/D12、必要时 `edges.csv` |
| 缺失数据 | 产品特定内部 BOM、离散光与 SiPh 的 exact alternatives、具体 driver/DSP 型号、产品级结构/散热实现 |
| 最小关系类型 | `route_has_bom_group`、`bom_group_maps_to_cell`、现有 physical edge |
| 最小问题结构 | TQ005–TQ010 负责路线轴和变化；PQ004/PQ005/PQ010 负责组件、接口和通用/变化项 |
| 值得自动化 | 拆 `cell_ids`、解析引用、补 cell 名称、按 BOM group 排序、检查悬空 refs、渲染链表 |
| 必须人工 | 判断 alternative vs required；判断规范事实与典型实现；禁止把 LPO/SiPh 当成 DR8 必然属性 |

### B. LPO 为什么降低模块功耗及责任转移

#### 用户最终看到的答案

LPO 的模块功耗机制不是“所有处理消失”，而是模块信号路径不再使用完整 DSP/Retimer，减少一条
模块内数字处理和耗电路径。与此同时，host 必须承担或配合更多 FEC、equalization、channel
configuration 和端到端 BER/FEC margin 责任；模块仍可能保留 Tx equalization、driver/TIA AGC、
管理与控制功能。

因此结论是有条件的：只有 capable host、合格电通道损耗、host-module 联合配置和验证成立时，
LPO 才具有降低模块功耗/时延/成本的相对价值。它不证明系统总功耗必然下降，也不支持固定百分比。
Retimed module 是明确替代方案；host compatibility、channel-loss margin、启动训练和联合测试是新瓶颈。

#### 数据、缺失与最小结构

| 项 | 内容 |
|---|---|
| 读取账本 | `route_bom.csv#RB004`、`research_questions.yaml` 的 TQ002/TQ003/TQ006/TQ010/TQ014 与 WQ001–WQ003、现有 reviewed route-chain draft 的 S1–S4/S10 锚 |
| 缺失数据 | 同条件系统总功耗、成本、时延对照；host 额外功耗；不同 loss class 的可用边界；生产工序/设备净变化 |
| 最小关系类型 | 复用现有 WHY：`need_to_constraint`、`bottleneck_to_choice`、`choice_to_physical` |
| 最小问题结构 | WQ001：需求→约束；WQ002：瓶颈→LPO；WQ003：LPO→组件/接口/测试；TQ014：条件、代价、新瓶颈、替代方案 |
| 值得自动化 | 校验证据 refs、链顺序、主张类型、条件/取舍/替代方案非空、渲染 WHY 卡 |
| 必须人工 | 因果蕴含、适用条件、比较可比性、UNKNOWN、反例与禁止外推 |

该切片直接使用已有 `knowledge.yaml#why_links` seam，不建立通用 relation assertion engine。

### C. 哪些公司有 800G LPO 具名产品级证据

#### 用户最终看到的答案

当前应分三层回答，不能合并：

| 层级 | 当前可说的内容 | 不可说的内容 |
|---|---|---|
| exact named listing（reviewed draft） | Hyper Photonix / 芯速联的 `HSO6-800-LP-P8S`、`HSD2-800-LP-P8S` 被研究草稿记录为 800G DR8 LPO SiPh finished-product listings | 不能说已量产、已出货或有具名客户；该证据尚未写入 canonical |
| company/product announcement（canonical） | `calls/claims.csv#CL012` 支持 Cisco 宣布 800G LPO；`points.csv#P209` 支持华工科技对 800G SiPh LPO 系列规模交付的公司披露 | Cisco 行缺 SKU；华工行是系列级公司口径；均不能自动补 exact product identity |
| near-route / partial evidence | Eoptolink demo、新易盛分别披露的 LPO/SiPh 项目、联特 2×DR4/2×FR4 LPO NPI 等可作为研究线索 | 不得拼成同一 DR8 SiPh LPO SKU，不得推 named-customer adoption |

所以当前 canonical 的诚实结论是：**有 800G LPO 公司级或产品族证据，但 exact named SKU 的正式
canonical 晋升仍未完成。** 人工下一步是核验 Hyper 两个 listing 的原始页面和边界，再决定是否写回
一个 KN 或适当的 calls disclosure/claim；不是先建立 product registry。

#### 数据、缺失与最小结构

| 项 | 内容 |
|---|---|
| 读取账本 | `calls/claims.csv`、`calls/disclosures.csv`、`calls/events.csv`、`calls/event_claims.csv`、`points.csv`；reviewed draft 的 S6/S7/S13–S15 仅作为 promotion candidate |
| 缺失数据 | Hyper listing 的 canonical promotion；SKU 与 route axes 的逐项核验；shipment/customer；Cisco SKU；系列口径到具体产品的绑定 |
| 最小关系类型 | generated `source_mentions_route_terms` lead；人工 `product_has_route_axes` 判断；已有 calls `product_stage` 字段 |
| 最小问题结构 | TQ012 候选能力群、TQ013 路线级直接证据、WQ004 物理能力→公司证据边界 |
| 值得自动化 | 按显式 `800G`/`LPO`/RB/cell 字段筛候选；解析 source/claim IDs；生成“待人工判定”表 |
| 必须人工 | 是否具名产品、SKU 是否 exact route、announcement/demo/listing/shipment 的阶段、主体与证据边界、是否晋升 |

## 7. 最小 relation-lead interface

未来唯一新增 module 的外部 interface 应保持为：

```text
build_relation_leads(repo_root) -> list[RelationLead]
```

调用方只需知道：输入是现有 canonical，输出是可删除的 leads。每条 lead 最多包含：

- `lead_id`；
- `relation_view`；
- `subject_ref`；
- `object_ref`；
- `source_refs`；
- `reason`；
- `human_review_required: true`。

不得包含：

- slot state；
- resolution status；
- workflow status；
- actor role；
- coverage score；
- product binding；
- independent evidence count；
- snapshot/build lineage；
- 自动晋升结果。

这是一个深 module：机械读取、去重、稳定 ID、悬空引用检查和输出排序隐藏在一个小 interface 后面。
测试和 CLI 都调用同一 interface，不为测试暴露内部 adapter seam。

## 8. 复杂度预算

### 8.1 Source of truth 所有权

| 事实 | 唯一 source of truth |
|---|---|
| 物理格与结构连接 | `tree.yaml` / `edges.csv` |
| 路线与 BOM 分组 | `route_bom.csv` |
| 公司能力证据 | `points.csv` |
| 来源、claim、事件、阶段 | `calls/*.csv` 各自账本 |
| 解释性知识与 WHY | `knowledge.yaml` |
| 人工问题导航 | `research_questions.yaml` |
| relation leads | 无 canonical；随时从上述账本重建 |

### 8.2 硬预算

1. generated output 不作为 canonical，不被其他 canonical 文件引用；
2. 无生产数据触发的状态不进入主内核；
3. 新 relation view 最多修改三处：`relation_views.yaml`、builder、一个 outcome test；
4. 不保留 d0 Python 兼容 API；没有第二个生产调用方就不设 adapter seam；
5. 不为未来 conflict/withdrawal 建历史状态机；发生真实案例后先由人处理并记录；
6. 第一版 lead builder 建议不超过 300 行，单一 CLI、单一输出；
7. 第一版 domain outcome tests 建议不超过 12 个，只验证 A/B/C 用户可见结果与禁止外推；
8. 三切片完成前，不新增目录、合同、registry 或页面。

## 9. 第一批应删除或隔离的代码

因为新主线从 227f503 开始，最安全的“删除”是根本不合入：

1. 整个 `contracts/` pilot 三文件；
2. `relation_assertions.yaml`；
3. `build_relation_index.py`；
4. `recompute_question_state.py`；
5. `validate_reviewed_assertions.py`；
6. relation closure 两份测试与 fixtures；
7. assertion index、slot states、diagnostic questions、funnel；
8. `scan.py` relation gate ⑮；
9. pilot 为 Python package 新增的、没有其他调用方的 `tools/__init__.py`、`tools/research/__init__.py`、`tests/research/__init__.py`，按实际 import 需要决定，不为兼容保留。

只隔离、不复制：

- d0 验收报告；
- A/B/C snapshot 测试；
- relation type/slot/assertion 设计；
- recursive replay 与 semantic-hash 防伪实现。

## 10. 不能继续做的事项

- 不再以“再加一个真实 case”扩展通用 reducer；
- 不再把 company capability overlap 发展成自动 route-service 问题；
- 不建立完整 BOM coverage、product registry 或 actor-role taxonomy；
- 不自动 formalize、close、reopen research questions；
- 不为 reviewed relation 另建 receipt/origin registry；
- 不把 calls events 复制成第二份 relation assertion ledger；
- 不把页面、JSONL 或 Markdown 当 canonical；
- 不为保留 d0 测试而保留兼容 interface；
- 不在没有真实 conflict/withdrawal 调用方时建设 event sourcing；
- 不用更多内部测试数量替代领域答案验收。

## 11. 精简后研究能力不下降的验收标准

### 11.1 领域结果

1. A 页面/研究卡能从 RB001–RB005 重建完整 800G DR8 组件链，所有 cell refs 可解析；
2. A 明确显示 DR8 ≠ LPO、LPO ≠ SiPh，不把典型 BOM 写成产品事实；
3. B 给出可读的 LPO 功耗机制与责任转移链，包含条件、代价、新瓶颈、替代方案和 UNKNOWN；
4. B 不给无证据百分比，不把模块功耗外推成系统总功耗；
5. C 能把 exact named listing、announcement、demo、shipment、customer adoption 分层；
6. C 至少保留当前已发现的 Hyper/Cisco/华工及 near-route 证据，不因删除 reducer 丢失 source refs；
7. C 不从 capability overlap 推导产品、供货或客户关系。

### 11.2 机械能力

1. 新 builder 从真实 `route_bom.csv × points.csv` 产生 deterministic leads；
2. 每条 lead 的 source refs 均可回到 canonical；
3. 重复运行不重复；删除 output 后可以完整重建；
4. builder 不写 canonical，不读取测试 registry，不输出状态；
5. 新 relation view 的一次变更不超过三个 module。

### 11.3 回归与删除证明

1. 227f503 已有 `scan.py --check`、`render.py --verify`、calls 校验和页面测试继续通过；
2. 新主线 `rg` 不出现生产用 `PriorQuestionState`、`recursive replay`、`receipt registry`、
   `question resolution_status`；
3. 不存在 tracked assertion index、slot-state snapshot 或 diagnostic question output；
4. 新主线无需理解 d0 contracts 即可完成 A/B/C；
5. 将 d0 pilot 整体删除后，三个领域答案、source refs、人工问题导航和 canonical 写回能力不减少。

满足以上标准，才证明削减不是“功能倒退”，而是把实验性机制从领域主线中移除，同时保留真正的
研究能力。

## 12. 最终决策

| 决策对象 | 结论 |
|---|---|
| d0 pilot | 冻结为成功的 reducer 实验，不再开发 |
| 新领域主线 | 从 227f503 开始，不合入 pilot |
| 关系图 | 只保留 canonical 派生的机械类型化视图和 leads |
| 问题图 | 人工策划、人工选择、人工审核写回；不设自动生命周期 |
| 历史 | Git + 原账本日期；不建通用状态机 |
| 优先级 | 先交付 A/B/C 三个答案，再讨论任何抽象扩展 |
