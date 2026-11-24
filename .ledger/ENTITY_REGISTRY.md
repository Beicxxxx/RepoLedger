<!-- schema: 1.0 -->
# RepoLedger 自身登记表

> RepoLedger 自己的工作登记在这里（DECISION-1）。规则同 README：`TYPE-N` 每类型单调、只追加、不复用；
> 铸号只在能把行与 ID 一起落地的提交里做（主工作树里 `repo-ledger allocate`）。

| id | name | status | parent | order | anchor | supersedes | date | legacy | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DECISION-1 | RepoLedger 的工作在自己的登记表追踪 | IN_FORCE |  | 1 | AGENTS.md |  | 2026-09-26 |  | 所有者 2026-09-26 的决定（font-repertoire-expansion 项目侧登记为该项目的 DECISION-65）：RepoLedger 的改动在本仓库 .ledger/ENTITY_REGISTRY.md 追踪，与改动同一次落地；使用 RepoLedger 的项目只登记采用这一步。 |
| TASK-1 | 按类型编号总表 | DONE |  | 1 | repo_ledger/index.py |  | 2026-09-26 |  | repo-ledger index 为每个已声明类型写一页 Markdown 目录（父子关系用标题分级）并写总览页；[index] check = true 让 check、check-legacy 与 lint_all 核页面新鲜度，只有与再生成结果逐字节一致的页面才从引用扫描和退役代号守卫中排除。独立评审 REJECT 九项 → 返工（红先行，另带可选 1、6、10）→ 快速复跑一致；测试 183 → 199；未声明 [index] 时输出与之前逐字节相同。 |
| TASK-2 | 全名与字母序号守卫 | DONE |  | 2 | repo_ledger/naming.py |  | 2026-09-26 |  | 给人看的文字里孤立的 TYPE-N 与带字母的章节号、列表号机器拦截：[full_name_guard]、[letter_label_guard] 与只减不增的 [naming_baseline]，默认关闭，未配置时 check 输出与之前逐字节相同；check-naming --emit-baseline 生成历史基线。所有者 2026-09-25 的要求（font-repertoire-expansion 项目登记为该项目的 TASK-43 全名与字母序号守卫）。独立评审 REJECT 七项 → 返工（红先行，规则版本升为 2）→ 快速复跑九笔提交红绿一致；测试 199 → 388。 |
| TASK-3 | 归档登记表联合查询与决定激活视图 | DONE |  | 3 | docs/archive-registries.md |  | 2026-10-10 |  | 用户2026-10-10要求决定库归档支持；主表与归档联合lookup/check/allocate，主表独写、归档只读，索引按ACTIVE及DORMANT可见范围；6feab53干净归档语义测试9passed，原基点5failed/4passed；相关既有工具检查部分通过，4个Windows符号链接权限fixture失败保留，不声称完整套全绿。86db1187收拢索引单次读取主表文本与其digest一致，避免重读；实际使用项目名单另等用户确认。；323c8c0a干净主树归档语义9passed in 7.97s；同轮cleanup先干跑后apply，工具候选树整体移入待用户删除目录，archive标签远端已核，squash分支-d拒绝后保留，不永久删除。 |
| TASK-4 | 父实体显示、改挂与检查提速 | DONE |  | 4 | tests/test_parent_views.py |  | 2026-11-25 |  | 项目所有者2026-11-25：从属关系看不明显，采用扁平编号加 parent 字段并显示树状（不用 TASK-30.1 式层级编号）。lookup 文本列父实体、祖先路径、子实体与截断备注；lookup --ref 输出汇报用单行「ID 名称（↳ 父ID 父名称）」；lookup --json --relations 加 ancestors 与 children，默认 JSON 字段不变；update --parent 改挂或解除父实体，锁内校验存在、自引用与环，independent_order 下取新父下一个计划位置；tree 支持 ID 子树、--type、--all、--json，同级按类型声明顺序、计划位置、ID 数字排序（原先按字符串，TASK-10 排在 TASK-2 前）；search 文本显示父 ID；管道被读端关闭时静默退出；check 提速：整文件一次正则并只为未登记引用算行号、行首边界改在 Python 判、拆表格行按记号而非逐字符、名称历史按行缓存，font-repertoire-expansion 项目 check 53 秒到 18 秒，check --json 输出与旧版逐字节相同；测试 397 到 412。 |
