# 研究图闭环修复与活性验收报告：research graph closure reducer pilot

- 日期：2026-09-02
- 基线提交：`4150e55b52012663743a13793702ad53fcc3804b`
- 工作分支：`codex/research-graph-closure-pilot-fix-codebuddy`
- 范围：只读 relation index、relation lead/funnel、窄 lifecycle question、跨构建 snapshot/reducer
- 实现：CodeBuddy hy4-preview 初稿，Luna max 收敛修复
- 独立复审：OpenCode / GLM 5.3 Flash + 主代理生产路径反例
- 状态：**已完成本轮活性验收；随本分支固定提交发布**

## 1. 范围与修改文件

本轮没有修改 `points.csv`、`route_bom.csv`、`calls/*.csv`、`knowledge.yaml`、`tree.yaml`，没有迁移 legacy/canonical ledger，没有修改页面语义，没有新增 relation type，也没有把 derived relation 晋升为 canonical。

修改或新增：

- `contracts/relation_types.yaml`：把 exact lifecycle stage 纳入 `product_has_lifecycle_stage` slot identity。
- `contracts/question_generation_rules.yaml`：冻结 route-service rule 为 lead-only，并加入唯一获准的窄 lifecycle pilot rule。
- `tools/research/build_relation_index.py`：修正 reached-stage 时间语义，增加显式 temporal/raw CLI 边界、lead 输出和跨构建兼容摘要。
- `tools/research/recompute_question_state.py`：生成 lead/funnel 与真实 lifecycle question，并验证跨构建 snapshot、目标身份、规则版本、parent 链、as-of 和 transition cause。
- `tests/research/test_relation_graph_closure_latest.py`：真实 calls lifecycle 的 CLI A/B/C、raw/temporal CLI 边界、跨投影身份/合同/lineage 篡改、悬空/异 slot/未来 cause 负例。
- `tests/research/test_relation_graph_closure.py`：把旧 route-question 断言改为冻结后的 lead-only 语义，并删除手写 satisfied snapshot 的伪历史测试。

`contracts/relation_adapters.yaml`、`relation_assertions.yaml`、reviewed gate、`scan.py` 及 canonical CSV/YAML 本轮均未修改。为让人工审阅不必先运行代码，本提交保存一次显式 `as_of=2026-09-02` 的 disposable projection：`out/relation_assertion_index.jsonl`、`out/relation_slot_states.jsonl`、`out/relation_leads.jsonl`、`out/relation_lead_funnel.json` 与 `out/generated_diagnostic_questions.jsonl`。这些文件可由合同和 canonical 账本重建，不是事实源。
- `out/光模块知识体系/`：仅在验收时由既有 reader builder 临时生成并通过 site reader 校验；它是可重建页面产物，不纳入本次内核提交。未改 canonical 页面语义，`knowledge.yaml` 保持不变。

## 2. GPT Pro findings / 合同十项 disposition

| 项 | disposition | 证据与边界 |
|---|---|---|
| 1 reviewed gate | **fixed** | receipt 必须注册且 subject/reviewer/receipt kind 一致；`reviewed_at` 严格 ISO；source/evidence 非空、按 kind 解析、同主体并有真实 source↔evidence link；`supports`/`does_not_support` 保存并验证非空语义；canonical origin 从 registry 派生；完整审核字段保留在 index。claims.csv 没有 claimant 列时按其 `source_id` 关联 source 的 universe company，不再落到 `company:`。独立 CLI 与 scan ⑮ 均接入。 |
| 2 route identity/semantics | **fixed / guarded** | profile 必须有 `revision`、`identity_hash`、`requirement_contract_version`、`source_route_item_ids` 等字段，hash 由 identity axes 重算；LPO 使用显式 `one_of`/`all_of` groups，RB002 的 C1/C4 不再被整体展开成一个 `all_of`；broad route BOM 只投影为 `derived_candidate`。FRO/discrete 语义保持 `UNKNOWN`，不生成 exact requirement/match/question。 |
| 3 actual coverage | **fixed / lead-only** | overlap 先按 `as_of`/modality 过滤并计算 actual/planned/unmatched cells；单格或 partial 命中只产生 lead，不能称为 route capability，也不能产生 formal route question。 |
| 4 real target binding | **guarded / not admitted** | `company_serves_route` 若进入正式流，target 仍必须是完整 slot（canonical company、真实 product、exact `route_profile_id`、受控 `service_kind`）；本轮冻结 rule 为 `experimental/not_admitted`，因此 production 没有 route-service question，也没有用 component/demo/product family 补假 target。 |
| 5 reopened/prior state | **fixed / guarded** | satisfied 不从 projection 中无声删除；reopened 只接受带 manifest、rows hash、query/contract/registry binding、完整 target identity 的 previous snapshot，或带 manifest、时点及连续 transition 的 append-only event log。完整历史 ledger 与正式问题晋升仍 deferred。 |
| 6 as_of/modality | **fixed** | ISO 日期/时间严格解析；先过滤时间与 query modality，再应用 withdrawal/limit/conflict；未来 withdrawal/ planned limit 不影响过去 actual；`modality=None` 明确表示保留所有 modality，但 effect 只能在相同 modality/comparison surface 内生效。 |
| 7 revision provenance / calls P2 | **fixed / guarded** | 保存并验证 `revision_kind`、`revises_assertion_ids`、`effective_at`、`retroactive`；`withdraws` 与 `supersedes` 均只在 effective_at/as_of 后、相同 relation/identity/comparison surface 与 modality 内生效，superseder 自身保留为新断言参与状态；`corrects` 在生产 adapter 中明确拒绝，不映射成 limiting。calls 的 P2 语义隔离只投影 `product_stage`，不可靠的 `previous_event_id` 不虚构 revision chain，保持未投影。pilot 不做 bitemporal 历史回写。 |
| 8 comparison/context | **fixed** | 五类 relation 都声明 `slot_identity_fields`、`comparison_fields`、`context_fields`；index/state 输出 `identity_scope` 与 `assertion_context`。geography/customer/program 进入 company-service comparison surface，US support 与 EU contradiction/limit 不会误判为同一可比条件；`contradicting_assertion_ids` 与 independent count 只统计可比较面，异面 contradiction 留在 `non_comparable_contradicting_assertion_ids` 审计字段。 |
| 9 raw withdrawal | **fixed** | raw sidecar 没有生成态 `slot_id` 时，从 relation/subject/object/scope 重算 identity；未知、跨 slot、跨 modality、跨 comparison surface、自引用或重复 withdrawal 均受控拒绝，不再以 KeyError 代替校验。 |
| 10 deterministic manifest | **fixed** | manifest 严格要求三份完整合同引用、relative path、SHA-256、row count/hash 与 combined data hash；recompute 对实际传入 JSONL rows 重算并比对，不只比较 build_id；extra registry 的 path/hash 必须列入 manifest。跨 worktree deterministic regression 通过，生成文件不含绝对路径。 |

## 3. 反例结果（before → after）

- Lumentum claim + Coherent source，或未注册 receipt/错误 reviewer：**可被旧路径放过 → reviewed gate 拒绝**。
- `RB002` 的 C1/C4/P1/D12：**宽行可整体冒充 required → C1/C4 为 `one_of`，必要格为声明的 `all_of`**；FRO exact semantics：**猜测 → UNKNOWN 且无 exact output**。
- 2026 evidence 在 `as_of=2020`：**可能污染 coverage → 被 filtered state 排除**；planned withdrawal/limit：**可能影响 actual → 跨 modality 不生效**。
- partial/single-cell/planned coverage：**可能生成 route capability wording → 现在只生成带 coverage 细节的 lead**；`formal_question_candidates=0` 是合同规定的未准入结果。
- route-only、synthetic product、不同 product/service_kind、component/demo/listing：**可能聚合或交叉关闭 → 本轮不进入 route formal question 流，也不跨 profile/service kind 关闭**。
- withdrawal/supersedes/corrects：**可能静默忽略或映射 limiting → strict revision validation；supersedes 在 effective_at 后停用旧断言并保留新断言，corrects rejected，calls ambiguous previous event unprojected**。
- 异 geography/customer/program/modality contradiction：**可能进入阻断集合 → 只保留在 non-comparable audit 集合，不影响可比较面的 resolution**。
- raw withdrawal 无 `slot_id`：**KeyError/把受控拒绝误当成功 → 从 raw identity 计算并验证**。
- 篡改 assertion/slot JSONL 但保留 build_id：**可能继续重算 → rows count/data_hash/combined hash mismatch，退出失败**。
- 满足状态与 reopened：**可能从当前 withdrawal 猜 reopened → 没有真实 prior history 保持 open；真实 snapshot/event 才能 reopened**。

## 4. 本轮真实生产投影结果

使用显式 `--as-of 2026-09-02` 构建（省略 `--as-of` 的 temporal CLI 会 fail closed）：

- relation assertion index：**405** rows；slot states：**386** rows。
- `out/relation_leads.jsonl`：**83** 条 overlap lead；每条都带 exact `route_profile_id`、actual/planned 命中格、未命中格、coverage kind、deferred reason 和 `capability_matches_route` assertion IDs。
- funnel：`overlap_leads=83`、`role_eligible_leads=83`、`product_bound_leads=0`、`formal_question_candidates=0`、`reviewed_assertions=0`。
- lifecycle question：**1** 条真实问题，来自 `calls` 的 EV003/ECL003/EE003，目标为 `PRG_AVGO_TAURUS / sampling`；在 2026-09-02 投影中为 `satisfied`。
- 本轮前的可比基线是 **0 formal route questions / 83 deferred overlaps**；本轮后是 **83 可观察 leads + 1 条真实 lifecycle question**。这不是“83 条路线能力问题被关闭”。
- 本次构建 build `D202A071022FDDBB7188B9A9`，`data_hash=d202a071022fddbb7188b9a90842a0222e2cf0bf47f42711927d093dab90d9dd`。生成层仍只保存引用和状态，不改 canonical CSV/YAML。

## 5. 真实 lifecycle A/B/C 跨构建序列

下面的命令在一个临时 production fixture 上执行；fixture 只复制真实 `calls` 账本，C 步骤额外加入测试用 EV900/ECL900/EE900 withdrawal，不写入仓库 canonical 数据。

```text
# A: 2026-03-10，EV003 尚未生效，question=open
python tools/research/build_relation_index.py --root "$FIXTURE" --output-dir "$A" --as-of 2026-03-10
python tools/research/recompute_question_state.py --assertion-index "$A/relation_assertion_index.jsonl" --slot-states "$A/relation_slot_states.jsonl" --rules "$FIXTURE/contracts/question_generation_rules.yaml" --adapters "$FIXTURE/contracts/relation_adapters.yaml" --contracts-dir "$FIXTURE/contracts" --output "$A/questions.jsonl" --as-of 2026-03-10

# B: 2026-03-12，读取 snapshot A，EV003 已生效，question=satisfied
python tools/research/build_relation_index.py --root "$FIXTURE" --output-dir "$B" --as-of 2026-03-12
python tools/research/recompute_question_state.py --assertion-index "$B/relation_assertion_index.jsonl" --slot-states "$B/relation_slot_states.jsonl" --rules "$FIXTURE/contracts/question_generation_rules.yaml" --adapters "$FIXTURE/contracts/relation_adapters.yaml" --contracts-dir "$FIXTURE/contracts" --output "$B/questions.jsonl" --as-of 2026-03-12 --previous-snapshot "$A/questions.jsonl"

# C: 先把测试用 withdrawal 写入临时 fixture；读取 snapshot B，question=reopened
python tools/research/build_relation_index.py --root "$FIXTURE" --output-dir "$C" --as-of 2026-03-14
python tools/research/recompute_question_state.py --assertion-index "$C/relation_assertion_index.jsonl" --slot-states "$C/relation_slot_states.jsonl" --rules "$FIXTURE/contracts/question_generation_rules.yaml" --adapters "$FIXTURE/contracts/relation_adapters.yaml" --contracts-dir "$FIXTURE/contracts" --output "$C/questions.jsonl" --as-of 2026-03-14 --previous-snapshot "$B/questions.jsonl"
```

| snapshot | as_of | build_id | data_hash | status | transition cause |
|---|---|---|---|---|---|
| A | 2026-03-10 | `1C8C88136447DD6F1930E9AE` | `1c8c88136447dd6f1930e9ae073062560aaf560941b303d8a71cfea05f944a4d` | `open` | — |
| B | 2026-03-12 | `200FC5336FD06D4B5F72CFBB` | `200fc5336fd06d4b5f72cfbbe6139e9b95210c44309c7bca808ddedd0c4f36fb` | `satisfied` | `RA-799F3C0B881EB858` (EV003) |
| C | 2026-03-14 | `1DF72665403E98B762293B5A` | `1df72665403e98b762293b5a2050a6e814f6bc5ef564474c7101724866d14b1e` | `reopened` | `RA-1A89535C9D1E16F6` (EV900) |

三次均保持同一 `question_id=GQ-E9B8ED07C94B`、同一 exact target slot `RS-1C817400D991A05B`（`sampling`），但 build/data hash 不同；snapshot 链、as_of 单调性、target identity、rule/contract compatibility 和 cause assertion 均经过校验。

## 6. 仍不能宣称什么

1. 这仍是 reducer activity pilot，不是完整 question-graph closed loop；candidate→formalized 晋升、研究结果通用写回和正式问题 ledger 仍未实现。
2. `QGR-CAPABILITY-WITHOUT-EXACT-SERVICE-V1` 仍是 `experimental / not_admitted`，只产 lead；route closure 仍未成功，也没有 full-BOM 单公司准入门。
3. 生产 registry 没有可验证的 exact product master，因此没有把 component、demo、product family 或任一 capability cell 升格成 `company_serves_route`。
4. FRO/discrete exact requirement semantics、calls 不可靠 `previous_event_id` 的通用 revision chain 仍保持 UNKNOWN/未投影。
5. 没有新增网页、图数据库、问题类型或 canonical CSV/YAML 迁移；页面仍是既有投影。

## 7. 验证与回归

```text
python -m unittest tests.research.test_relation_graph_closure tests.research.test_relation_graph_closure_latest -q
Ran 59 tests ... OK

python -m unittest discover -v
175 tests ... OK

python -m py_compile tools/research/build_relation_index.py tools/research/recompute_question_state.py tools/research/validate_reviewed_assertions.py scan.py
exit 0

git diff --check
exit 0
```

专用测试还覆盖跨 worktree 的确定性输出、raw-only/no-as-of 边界、未来 cause、悬空/异 slot cause，以及 projection 身份、合同和 lineage 篡改。独立定向复核另外验证：自洽重写 root snapshot 为 `satisfied` 会被 reducer replay 拒绝；只改 acceptance 语义但不升级 `rule_version` 会被兼容性校验拒绝。报告中的生成文件是可复现审阅快照，不改变其 disposable projection 身份。
