# 光模块供应链图谱（点先行 v2）

产品：一棵光模块 BOM 树，每个格子挂着做这件事的公司，每家带披露引语+锚。
状态：重启五会话已全部完成（2026-07-25），系统进入日常态。章程已归档 archive/RESTART-v2.md。

## 日常怎么用（全流程）
1. 新年报/招股书 PDF 扔进 corpus/annual/<代码>/，在 corpus/_frozen.csv 记一行（带出处）
2. `python3 scan.py` —— 机器翻书出待办清单（自动跳过已处理过的）
3. 判定闸会话：逐条判 入点/驳回/待判，写 points.csv 和 triage.csv，**会话末必跑 `python3 scan.py --check`**
4. `python3 render.py` —— 重建 out/全景.md 与 .html
5. 你只看 git diff 点头/摇头；commit 信息带"产出: +N点 +M边 驳回K"

年报季提示：A股年报4月末集中披露；美股10-K财年后60-90天。
边界：语料宇宙见 corpus/_frozen.csv（每文件一行带出处）；archive/ 为旧结构冷冻区（默认禁读）。
