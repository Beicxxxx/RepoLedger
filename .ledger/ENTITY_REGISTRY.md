<!-- schema: 1.0 -->
# RepoLedger 自身登记表

> RepoLedger 自己的工作登记在这里（DECISION-1）。规则同 README：`TYPE-N` 每类型单调、只追加、不复用；
> 铸号只在能把行与 ID 一起落地的提交里做（主工作树里 `repo-ledger allocate`）。

| id | name | status | parent | order | anchor | supersedes | date | legacy | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DECISION-1 | RepoLedger 的工作在自己的登记表追踪 | IN_FORCE |  | 1 | AGENTS.md |  | 2026-09-26 |  | 所有者 2026-09-26 的决定（font-repertoire-expansion 项目侧登记为该项目的 DECISION-65）：RepoLedger 的改动在本仓库 .ledger/ENTITY_REGISTRY.md 追踪，与改动同一次落地；使用 RepoLedger 的项目只登记采用这一步。 |
| TASK-1 | 按类型编号总表 | DONE |  | 1 | repo_ledger/index.py |  | 2026-09-26 |  | repo-ledger index 为每个已声明类型写一页 Markdown 目录（父子关系用标题分级）并写总览页；[index] check = true 让 check、check-legacy 与 lint_all 核页面新鲜度，只有与再生成结果逐字节一致的页面才从引用扫描和退役代号守卫中排除。独立评审 REJECT 九项 → 返工（红先行，另带可选 1、6、10）→ 快速复跑一致；测试 183 → 199；未声明 [index] 时输出与之前逐字节相同。 |
| TASK-2 | 全名与字母序号守卫 | DONE |  | 2 | repo_ledger/naming.py |  | 2026-09-26 |  | 给人看的文字里孤立的 TYPE-N 与带字母的章节号、列表号机器拦截：[full_name_guard]、[letter_label_guard] 与只减不增的 [naming_baseline]，默认关闭，未配置时 check 输出与之前逐字节相同；check-naming --emit-baseline 生成历史基线。所有者 2026-09-25 的要求（font-repertoire-expansion 项目登记为该项目的 TASK-43 全名与字母序号守卫）。独立评审 REJECT 七项 → 返工（红先行，规则版本升为 2）→ 快速复跑九笔提交红绿一致；测试 199 → 388。 |
