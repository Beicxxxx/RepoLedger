# RepoLedger

面向长周期 Agent 工作的 Git 原生实体账本：稳定编号、结构化登记、物理锚点与静态引用校验。首轮实现关注引用完整性和可追溯性，不宣称解决语义漂移。

本仓库提供 Python CLI、RepoLedger Skill、测试、示例和文档。cross-harness-sync 是可选的独立生态伙伴，不随本项目打包。

预期名称：仓库 RepoLedger，distribution `repo-ledger`，import `repo_ledger`，CLI `repo-ledger`。外部名称可用性尚未核实，也未注册或发布。没有采用旧字体项目的测试、归一化或性能数字。

## 本地运行

需要 Python 3.11+ 与 Git。运行时仅用标准库；开发测试使用 pytest。

```sh
python -m pip install -e ".[test]"
repo-ledger --help
python -m pytest -v
```

也可在本仓库直接运行 `python -m repo_ledger`，无需安装。下面示例在一个独立的 Git 工作区执行：

```sh
git init demo
cd demo
# 创建 docs/proposal.md，写下任务的需求或提案
git add docs/proposal.md
repo-ledger init
repo-ledger allocate TASK "验证 max|SMD| 方案" --anchor docs/proposal.md --json
repo-ledger lookup TASK-1 --json
repo-ledger check --json
```

`init` 不覆盖已有配置或账本。锚点必须是已 `git add` 的现有受控普通文件。然后在某个 Markdown 文件写入 `TASK-999`，再次 check 会返回 `ERR_UNREGISTERED_ENTITY`。先查询已有实体，判断误写还是新实体，再修正引用或显式 allocate；不要为检查通过伪造登记。

可直接运行的自包含演示：`python examples/demo.py`。它在临时 Git 仓库执行初始化、分配、查询、检查和未知引用检测，不改变当前仓库账本。

## 当前边界

- 实现：严格 schema 1.0 Markdown、中文/竖线/反斜杠往返、合法状态集合、单 parent 和多 supersedes 的存在性/自引用/环检查。
- 实现：主工作区短锁内重新读取账本、持久化编号高水位、原子替换。多个本地进程可串行分配；已分配工作可由多个 Agent 执行。
- 实现：工作树完整配置范围扫描；包含受控文件及未被 Git 忽略的新文件。JSON 输出扫描清单、排除理由及聚合错误。
- 未实现：历史锚点、暂存区/增量/提交树检查、状态迁移基线、完成证据策略、历史删除审计和搜索。
- `--staged`、`--commit`、`--incremental` 明确失败，绝不改查工作树。暂不提供 hook install，也没有可宣称为合并门禁的 CI。
- 保留原型的 `tree` 简易父关系列表；不会默认输出整个账本到 Agent 上下文。

状态可根据真实证据编辑账本后 check；首轮只验证状态词汇，不验证迁移合法性或工作是否真的完成。anchor 是证据载体，不是 assignee。

单次 `lookup ID --json` 输出该实体字段与直接关系；内部仍严格解析全账本。check 始终只读。退出码：0 通过，1 规则违规，2 配置/不支持能力，3 扫描或 I/O 未完成。JSON 的 complete 表示检查是否完整执行，并不等于通过。

详见 [架构与格式](docs/rfc-architecture.md)、[可选集成](docs/integration-cross-harness-sync.md)、[RepoLedger Skill](skills/repo-ledger/SKILL.md)。50ms 仅为将来小型增量场景的待测目标，不是承诺。本轮测试结果和限制见 [验证记录](docs/validation.md)。

MIT；见 LICENSE。
