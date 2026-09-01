# 研究图闭环 pilot 交付报告

日期：2026-09-01
运行范围：当前工作区，只读索引；未修改原始事实账本和页面语义

## 1. Before / After

| 项目 | Before | After |
|---|---|---|
| 关系接口 | 调用者分别理解 `points.csv`、`route_bom.csv`、`calls/*.csv` | 五类关系统一输出标准 Assertion 与 Slot State |
| 路线身份 | 页面或研究文件可能仅用 DR4/DR8 文本 | target 固定使用 `RPF-800G-DR8-LPO-SIPH-FPP-V1`；文本与 object_ref 同源 |
| 能力匹配 | 渲染/研究代码内临时推导 | `capability_matches_route` 明示为 `derived_candidate`，不可晋升 canonical |
| 路线服务 | KN 共引可能被页面逻辑解释 | 只有 explicit reviewed sidecar 可产生 `company_serves_route` |
| 缺口问题 | 不会由 relation slot 状态统一触发 | 能力匹配且 exact service slot 未满足时生成 candidate |
| 关闭条件 | 任一 KN/WHY 引用覆盖 | exact profile 的 reviewed supporting assertion；不认 KN、组件证据或异 profile |
| 重开 | 无通用执行器 | 支持撤回为 `reopened`；同条件反证为 `conflicted` |

## 2. 当前真实数据运行结果

- relation assertion index：564 条；
- relation slot states：505 个；
- `company_has_capability_at`：271 条；
- `route_requires_capability`：24 条；
- `capability_matches_route`：246 条，全部为 `derived_candidate`；
- `product_has_lifecycle_stage`：23 条；
- `company_serves_route`：0 条，因为正式 `relation_assertions.yaml` 目前为空；
- generated diagnostic questions：83 条；
- workflow：83 条均为 `candidate`；
- resolution：83 条均为 `open`。

这 83 条不是正式研究问题，也未进入 `research_questions.yaml`。生成文件全部位于 `out/`，删除后可由原账本重建。

## 3. 端到端 fixture 轨迹

测试对象：`company:Lumentum` × `route_profile:RPF-800G-DR8-LPO-SIPH-FPP-V1`。

| 输入变化 | target slot 状态 | 问题状态 |
|---|---|---|
| 只有 point 与 route requirement | slot 不存在 | `candidate / open` |
| 加入 exact、actual、supporting、explicit_reviewed assertion | supported | `candidate / satisfied` |
| 服务 assertion 指向另一 frozen route profile | 当前 target 仍为空 | `candidate / open` |
| 用 withdrawn assertion 指向最后一条合格支持 | withdrawn | `candidate / reopened` |
| 保留支持并加入同 scope/time/modality 反证 | conflicted | `candidate / conflicted` |

组件产品阶段 assertion 不满足 acceptance。planned ramp 与 current demonstrated 因 route/object、时间和 modality 不同，不被自动判为逻辑冲突。同一 `origin_group` 的两条记录在索引中保留两条 assertion，但独立证据计数仍为 1。

## 4. 验证结果

- 两次关系索引输出 SHA-256 完全一致；
- `scan.py --check`：不变量 ①–⑭ 全绿；
- `python -m calls check`：14 家公司、66 个来源、70 条 claims、21 个 reviewed radar events 全部通过；
- 当前工作区完整测试：158 项通过（其中包含工作区已有、尚未纳入本
  pilot 提交的研究检查）；本 pilot 自身新增 8 项闭环测试；
- 页面测试通过，现有页面语义未修改；
- `git diff --check` 与新 Python 文件编译检查通过。

## 5. 明确未实现范围

本 pilot 有意不实现：

1. candidate 经人工审核后进入正式问题 DAG 的晋升写入器；
2. 研究包自动写回 `relation_assertions.yaml` 或现有 canonical 账本；
3. `conflict / weak_evidence / stale_evidence / new_event / human_agenda` 的其他生成规则；
4. 除首批五种类型外的 relation type registry；
5. 针对全部 route profile 的正式身份库与版本迁移；
6. assertion 的人工审核 UI、权限和签收流程；
7. 页面展示、通知、定时重算和事件触发器；
8. 跨账本实体解析、公司别名统一和产品身份主数据；
9. 历史正式问题的自动关闭/重开；本轮只管理 generated diagnostic candidates。

下一步若继续，应先做“candidate → formalized”的人工晋升 seam，再做研究结果写回 adapter；不应先扩展更多关系类型或页面。

## 6. 已知语义缺陷

当前 83 个问题不是 83 种问题，而是同一条
`capability_matches_route → missing company_serves_route` 规则在 83 家公司的实例。
更重要的是，底层触发条件只是公司至少命中路线要求中的一个
`capability_cell_id`，问题模板却写成“具备路线所需能力”，容易被理解为具备完整路线能力。

在进入正式问题图前，应把措辞改成“在路线所需的若干能力格中有记录”，并在问题中列出：

- 实际命中的 capability cells；
- 尚未覆盖的 route requirement cells；
- 这是局部能力重合，不是完整路线能力或路线服务证明。
