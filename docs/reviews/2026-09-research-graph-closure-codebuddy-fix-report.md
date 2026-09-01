# 研究图闭环修复与验收报告：research graph closure reducer pilot

- 日期：2026-09-02
- 基线提交：`29cc861bf78821af1a0193bc7081de97521f7695`
- 工作分支：`codex/research-graph-closure-pilot-fix-codebuddy`
- 范围：只读 relation index、slot-state projection、diagnostic candidate 与其校验
- 实现：CodeBuddy hy4-preview 初稿，Luna max 收敛修复
- 独立复审：OpenCode / GLM 5.3 Flash + 主代理生产路径反例
- 状态：**已完成提交前验收；固定提交与 GitHub 链接由主代理发布**

## 1. 范围与修改文件

本轮没有修改 `points.csv`、`route_bom.csv`、`calls/*.csv`、`knowledge.yaml`、`tree.yaml`，没有迁移 legacy/canonical ledger，没有修改页面语义，没有新增 relation type，也没有把 derived relation 晋升为 canonical。

修改或新增：

- `contracts/relation_types.yaml`：review receipt/evidence gate、revision enum、modality policy、service-kind、identity/comparison/context contract。
- `contracts/relation_adapters.yaml`：严格 route profile identity 与 requirement groups；FRO/discrete 保持 `UNKNOWN`；calls 仅允许 `product_stage`。
- `contracts/question_generation_rules.yaml`：完整 ACTUAL coverage gate、真实 product/service target 与安全停用规则。
- `tools/research/build_relation_index.py`：reference/receipt registry、生产 adapters、relation-specific identity、时点/模态 reducer、withdrawal/revision 校验及 content-addressed manifest。
- `tools/research/recompute_question_state.py`：manifest/rows 重验、严格 query、真实 prior snapshot/event history、coverage 与 candidate lifecycle；保留旧 Python API 返回形状。
- `tools/research/validate_reviewed_assertions.py`：独立 reviewed-write-gate CLI。
- `scan.py`：将 reviewed/revision gate 接入不变量 ⑮，并从 raw subject/relation/object/scope 计算 withdrawal slot identity。
- `tests/research/test_relation_graph_closure.py`、`tests/fixtures/research_graph/relation_assertions_exact_support.yaml`、`tests/fixtures/research_graph/test_registry.yaml`：生产路径反例及可解析测试 registry。
- `out/relation_assertion_index.jsonl`、`out/relation_slot_states.jsonl`、`out/generated_diagnostic_questions.jsonl`：按当前合同重新生成的 disposable projections。
- `out/光模块知识体系/`：仅在验收时由既有 reader builder 临时生成并通过 site reader 校验；它是可重建页面产物，不纳入本次内核提交。未改 canonical 页面语义，`knowledge.yaml` 保持不变。

## 2. GPT Pro findings / 合同十项 disposition

| 项 | disposition | 证据与边界 |
|---|---|---|
| 1 reviewed gate | **fixed** | receipt 必须注册且 subject/reviewer/receipt kind 一致；`reviewed_at` 严格 ISO；source/evidence 非空、按 kind 解析、同主体并有真实 source↔evidence link；`supports`/`does_not_support` 保存并验证非空语义；canonical origin 从 registry 派生；完整审核字段保留在 index。claims.csv 没有 claimant 列时按其 `source_id` 关联 source 的 universe company，不再落到 `company:`。独立 CLI 与 scan ⑮ 均接入。 |
| 2 route identity/semantics | **fixed / guarded** | profile 必须有 `revision`、`identity_hash`、`requirement_contract_version`、`source_route_item_ids` 等字段，hash 由 identity axes 重算；LPO 使用显式 `one_of`/`all_of` groups，RB002 的 C1/C4 不再被整体展开成一个 `all_of`；broad route BOM 只投影为 `derived_candidate`。FRO/discrete 语义保持 `UNKNOWN`，不生成 exact requirement/match/question。 |
| 3 actual coverage | **fixed** | 先读取按 `as_of`/modality 过滤后的 slot state，再验证所有必要 `all_of` 与 `one_of` 组；单格、partial、planned 均不能产生 route-service gap。 |
| 4 real target binding | **fixed / guarded** | target 必须是完整 `company_serves_route` slot，主体为 canonical company，`product_ref` 为 registry 中同公司的真实 product，`service_kind` 固定为五种受控值；listed/qualifying/demo 等不交叉关闭 demonstrated/shipping/deployed。生产 registry 目前没有 product，83 个实例先在 coverage gate deferred；若完整 coverage 但仍无 product，则明确记录 `no_resolvable_product_binding`，不补假目标。 |
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
- partial/single-cell/planned coverage：**可能生成 route capability wording → deferred，不生成 candidate**；完整必要组 coverage 仍会生成 gap candidate（测试明确覆盖 positive case）。
- route-only、synthetic product、不同 product/service_kind、component/demo/listing：**可能聚合或交叉关闭 → 无法绑定则安全停用，已绑定 slot 才逐项 resolution**。
- withdrawal/supersedes/corrects：**可能静默忽略或映射 limiting → strict revision validation；supersedes 在 effective_at 后停用旧断言并保留新断言，corrects rejected，calls ambiguous previous event unprojected**。
- 异 geography/customer/program/modality contradiction：**可能进入阻断集合 → 只保留在 non-comparable audit 集合，不影响可比较面的 resolution**。
- raw withdrawal 无 `slot_id`：**KeyError/把受控拒绝误当成功 → 从 raw identity 计算并验证**。
- 篡改 assertion/slot JSONL 但保留 build_id：**可能继续重算 → rows count/data_hash/combined hash mismatch，退出失败**。
- 满足状态与 reopened：**可能从当前 withdrawal 猜 reopened → 没有真实 prior history 保持 open；真实 snapshot/event 才能 reopened**。

## 4. 当前真实投影结果

本次生产默认构建 build `175440912CF507ACC2898593`：

- assertion index：**405** rows；slot states：**385** rows。
- assertion relation counts：`company_has_capability_at` 271、`route_requires_capability` 11、`capability_matches_route` 113、`product_has_lifecycle_stage` 10、`company_serves_route` 0。
- slot relation counts：`company_has_capability_at` 267、`route_requires_capability` 10、`capability_matches_route` 99、`product_has_lifecycle_stage` 9。
- modalities：actual 366、planned 35、unknown 4；derived assertions 124，source-encoded 281。
- generated diagnostic questions：**0**；deferred：`incomplete_actual_coverage: 83`。生产 registry 无 product，所以不会伪造 83 个 product/service target；使用合同绑定的 test registry 时路径可重验，但当前 production capability coverage 仍不足，仍不生成问题。
- manifest 包含 assertion/slot row hashes、combined `data_hash`、三份合同 hash 与 registry 引用；默认没有 extra registry，输出及 manifest 不含绝对路径。

## 5. 仍不能宣称什么

1. 这仍是 reducer pilot，不是完整 question-graph closed loop；candidate→formalized 晋升、研究结果写回和正式历史问题 ledger 不在本轮。
2. 生产仓库没有可验证 product master，因此真实 route-service candidate 被安全停用；没有把 component、demo 或 product family 擅自升级成 exact product。
3. FRO/discrete 的 exact requirement semantics 仍 UNKNOWN；未以 LPO 语义猜测填充。
4. calls 的不可靠 `previous_event_id` 只保持未投影；没有虚构修正链。
5. 页面、canonical ledger 与既有 relation vocabulary 未迁移或扩展。

## 6. 命令与真实退出码

以下均在当前 worktree 直接运行，未用管道末端状态代替命令退出码：

```text
/Users/jowang/miniconda3/bin/python3 tools/research/build_relation_index.py
exit 0
relation index: 405 assertions, 385 slots -> out (build 175440912CF507ACC2898593)

/Users/jowang/miniconda3/bin/python3 tools/research/recompute_question_state.py
exit 0
diagnostic questions: 0 -> out/generated_diagnostic_questions.jsonl ({}) [build 175440912CF507ACC2898593] deferred={'incomplete_actual_coverage': 83}

/Users/jowang/miniconda3/bin/python3 -m unittest tests.research.test_relation_graph_closure -v
exit 0
Ran 51 tests ... OK

/Users/jowang/miniconda3/bin/python3 tools/research/validate_reviewed_assertions.py
exit 0
REVIEWED-GATE: 0 explicit assertion(s) passed write-gate validation

/Users/jowang/miniconda3/bin/python3 scan.py --check
exit 1
只剩既有环境缺失的 4 条不变量⑧：KN001、KN003、KN005 两条记录引用的 corpus/annual 年报 .pdf.txt 未在该沙箱抽取；未出现关系不变量⑮错误。

/Users/jowang/miniconda3/bin/python3 -m calls check
exit 0
OK: validated 14 companies / 66 sources / 70 claims
OK: validated 21 themes / 12 cross-checks / 9 commitments / 4 technology feedback rows
OK: event ledger validated / 21 reviewed radar events; canonical references are closed; no canonical file was written

/Users/jowang/miniconda3/bin/python3 tools/site/build_optical_module_site.py
exit 0
status: PASS; canonical_unchanged: true

/Users/jowang/miniconda3/bin/python3 -m unittest tests.site.test_optical_module_reader -v
exit 0
Ran 10 tests ... OK

/Users/jowang/miniconda3/bin/python3 -m unittest discover -v
exit 0
Ran 167 tests ... OK

/Users/jowang/miniconda3/bin/python3 -m py_compile tools/research/build_relation_index.py tools/research/recompute_question_state.py tools/research/validate_reviewed_assertions.py scan.py
exit 0

git diff --check
exit 0
```

专用测试还包含跨 worktree 输出字节一致性与“只改 rows、不改 build_id”时的 manifest 拒绝；两项均通过。以上命令均在固定提交生成前运行；随后由主代理在不改动已验收内容的前提下创建并发布 GitHub 固定提交。
