# 可选 cross-harness-sync 集成

RepoLedger 管理实体身份、状态、关系与锚点；cross-harness-sync 管理跨 Agent、会话、机器的进度叙述与交接。两者独立安装、独立使用。本项目不提供组合插件、适配包、共享运行时或 sync 源码。

本轮只读核对已安装 sync 的 SKILL.md 与公开 reference.md 配置说明，没有读取其内部状态或复制脚本。该版本默认启动文件包括 CURRENT/TASK/BLOCKERS，并支持项目 PRIME.md；这里演示的 CURRENT.md 与 NEXT_PROMPT.md 是联合工作流需按需读取的运行上下文，不替代 sync 自身约定或项目 AGENTS.md 等强制指令。

## 配置

将 examples/sync-extra-checks.json 中的 extra_checks 项手工合并到独立 sync 已有的 .ai/sync_config.json，保留其他检查，勿整份覆盖。公开接口使用 name 与 cmd 数组：

```json
{"extra_checks": [{"name": "RepoLedger working tree", "cmd": ["repo-ledger", "check", "--json"]}]}
```

需在项目根目录运行并确保 CLI 在 PATH。此检查是工作树反馈，不是暂存区或 CI 合并检查。未采用 RepoLedger 的项目不添加此项，sync 独立使用不受影响。

若项目在 ledger.toml 中声明 `[index]` 且 `check = true`，同一个检查项也会把缺失或过期的目录页报为 ERR_INDEX_STALE；账本变更后运行 `repo-ledger index` 重新生成，并与账本改动一起提交。无需为此另加检查项。

## 双 Agent 接力（按需上下文）

Agent A：
1. 遵守 AGENTS.md 与独立 sync 的启动协议，读 CURRENT.md 和 NEXT_PROMPT.md 了解关注点。
2. 对提及的 TASK-1 执行 `repo-ledger lookup TASK-1 --json`，按需读 anchor。
3. 创建前 search 候选，落地时新任务用 allocate；状态只在 RepoLedger 账本维护。根据证据用 update 的 --status/--note 和 --expected-status 更新后 check。
4. 使用 sync 自己的交接流程记录“当前关注 TASK-1，原因是边界测试仍待验证，下一步检查失败案例”；不要再维护一张权威任务状态表。

Agent B：
1. 读取同样的运行上下文和项目强制指令。
2. 交接使先前查询缓存失效；重新 lookup 涉及的 ID 及其锚点，不输出整个 ENTITY_REGISTRY.md。
3. 从证据与下一步继续，完成后更新 RepoLedger 记录，并由 sync 叙述关注点变化。

这称为“按需上下文”，不声称零 Token 成本。RepoLedger 不执行 pull/push，也不生成交接文档。sync 的会话咨询锁协调其工作交接；RepoLedger 的短锁保护一次分配或状态/备注更新，两者不能互相替代，更不是跨克隆原子锁。
