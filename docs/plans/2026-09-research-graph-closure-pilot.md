# 研究图双向闭环 pilot 设计

日期：2026-09-01
状态：implementation contract
范围：只读索引、候选问题与状态重算；不改变现有 canonical 账本或页面语义

## 1. 目标与边界

本 pilot 在现有 CSV/YAML 账本之上增加一个窄而深的索引模块。调用者只面对“关系断言、关系槽位、问题候选”三个接口，不需要理解 `points.csv`、`route_bom.csv`、`calls/*.csv` 的特殊字段。

现有文件继续承担原角色：

- `points.csv`：公司物理能力点 canonical；
- `route_bom.csv`：路线能力要求 canonical；
- `calls/*.csv`：事件与产品阶段账本；
- `relation_assertions.yaml`：仅保存不能从上述账本机械产生的显式审核语义关系；
- `out/*.jsonl`：可删除、可重建的只读索引，不是事实源。

本轮不迁移账本、不改渲染器、不创建正式研究问题、不引入图数据库。

## 2. 深模块 seam

模块输入是 legacy adapters 与显式 sidecar，输出是标准化断言和槽位状态：

```text
points / route_bom / calls / explicit sidecar
                    │
              legacy adapters
                    ↓
       Relation Assertion Index
                    ↓
          Relation Slot States
                    ↓
        diagnostic question rules
                    ↓
       candidate question + state
```

模块接口保证：

1. 断言不会覆盖历史；同一 slot 可同时保存 supporting、limiting、contradicting、withdrawn。
2. `source_encoded`、`explicit_reviewed`、`derived_candidate` 严格分层。
3. `route_bom × points` 只产生 `capability_matches_route` 候选。
4. 只有 `relation_assertions.yaml` 中 exact-scope 的 `explicit_reviewed` 断言可满足 `company_serves_route`。
5. KN 共引 route item 与 point 不是本接口的服务关系 adapter。

## 3. Slot 与 Assertion

Relation Slot 表示一个待判断的、作用域固定的关系：

```yaml
relation_type: company_serves_route
subject_ref: company:剑桥科技
object_ref: route_profile:RPF-800G-DR8-LPO-SIPH-FPP-V1
scope:
  route_profile_id: RPF-800G-DR8-LPO-SIPH-FPP-V1
```

Relation Assertion 是围绕 slot 的具体、不可变记录。索引至少标准化：

```yaml
scope: {}
valid_time: {start: null, end: null}
modality: actual
polarity: supporting
epistemic_status: explicit_reviewed
origin_group: OG-...
adapter_version: explicit_relation_assertions_v1
source_refs: []
```

`withdrawn` 是新断言，并通过 `withdraws_assertion_ids` 指向被撤回断言；历史断言不被原地改写。独立证据计数按 `origin_group` 去重。

冲突只在同 slot、scope 相等、modality 相同且有效时间重叠时成立。不同 modality 或不重叠时间的生命周期陈述可以并存，例如“当前 demonstrated”与“未来 planned ramp”不自动构成逻辑冲突。

## 4. Route identity 修正

旧式 `800G DR4/DR8` 文本不能作为关系对象身份。本 pilot 冻结：

```text
RPF-800G-DR8-LPO-SIPH-FPP-V1
```

其身份轴为：

- product standard：`800GBASE-DR8`；
- electrical architecture：`LPO`；
- placement / package：`front_panel_pluggable`；
- photonic platform：`silicon_photonics`；
- legacy requirement source：`RB001`–`RB005`。

该 ID 是 pilot 的对象身份合同，不表示仓库已经证明某公司服务该路线，也不把 `route_bom.csv` 的可选实现描述改写成事实。任何问题文本、fingerprint 和 `object_ref` 都从同一个冻结定义生成，因此不会再发生问题文本为 DR4、target 却为 DR8 的漂移。

合同另冻结 `RPF-800G-DR8-FRO-DISCRETE-FPP-V1` 作为隔离对照。它不进入本轮问题生成规则，只用于证明另一 exact profile 的服务断言不能误关闭 LPO/SiPh profile 的问题。

## 5. 问题合同

生成规则仅产生 candidate：

```text
某公司有 capability_matches_route
且 exact company_serves_route slot 未满足
→ 生成 diagnostic candidate
```

问题的 `target` 指向 slot，不指向 point、KN 或 source row。`display_parent` 仅用于页面投影，真实依赖保存在 `depends_on[]`。

`workflow_status` 与 `resolution_status` 分开：

- workflow：`candidate`，未经人工晋升不会进入正式问题集；
- resolution：`open / partial / blocked / satisfied / reopened / conflicted`。

满足条件是同一 frozen route profile 上至少一条 active、supporting、`explicit_reviewed` 的 `company_serves_route` 断言。组件产品证据、KN 共引、derived match、不同 route profile 都不能关闭问题。

撤回最后一条合格支持断言后为 `reopened`；同 scope/time/modality 的有效反证并存时为 `conflicted`。UNKNOWN 与反证继续保存在 assertion index 中。

## 6. 可回滚性与完成标准

删除 `contracts/`、`relation_assertions.yaml`、两个工具和生成的 `out/*.jsonl` 即可完整回滚；原账本内容不变。

自动化测试必须证明：

```text
无目标关系 → 生成候选问题
加入 exact reviewed 支持 → satisfied
加入撤回 → reopened
加入同条件反证 → conflicted
```

以上过程只调用索引与问题接口，不直接读取 legacy CSV/YAML 字段。
