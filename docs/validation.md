# 首轮验证记录

日期：2026-09-22。环境：Windows，Python 3.14.5，pytest 9.1.1。
Python 3.11 是声明的最低版本，本次未执行 3.11 或 Linux/macOS 矩阵。

## 实际执行

首次原型测试因默认临时目录访问受限而未运行成功；改为仓库内新建 .test-runs 目录，并禁用不可写的 pytest 缓存。最终命令：

```sh
python -m pytest -v -p no:cacheprovider --basetemp .test-runs/final
```

本轮命令 `python -m pytest -v`：99 passed in 80.68s，无跳过。该时间为测试套件耗时，不是 CLI 性能基准。
重跑时使用新的 basetemp 子目录，避免 pytest 清理已有目录。

覆盖 schema 缺失/未知版本、中文/竖线/连续反斜杠/空字段往返、非法控制字符、错列、重号、无法解析记录、合并冲突、未知引用、非法状态、无效锚点、自引用与关系环、六个独立进程竞争分配、锁超时、账本回退与写入中断后的编号保留、定制类型、只读扫描、聚合诊断、UTF-8 失败与受控文件删除。
还验证 linked worktree 拒绝铸号，以及 index 与工作树不同时工作树模式仍读取工作树；暂存区模式明确拒绝，不能将此测试解释为已实现 index 校验。
新增验证 legacy 列与旧 9 列读取兼容、legacy 唯一性、按 legacy lookup 当前 ID、枚举字面量退役代号守卫、守卫接入聚合 check，以及范围/整文件/围栏/列掩码/定向行五层豁免。
本轮再新增 33 个用例：字面子串搜索与排序/边界/只读（14），受锁状态更新、转义保留、陈旧状态条件、双写竞争、锁内重读最新配置与路径变化拒绝、linked worktree 拒绝（15），以及 search/lookup/update/check-legacy 的 CLI 场景回归（4）。

## 独立代理行为评测

为验证 Skill 是否改变实际行为，使用真实 CLI 在隔离 Git 沙箱中运行固定场景，并核对 registry/config 哈希与编号高水位是否被改动。这些是有限样本，不构成普遍遵循的证明。

- 未知简称：注入 `issue30` 引用。代理 lookup 失败后未猜号、未伪造名称、未新增登记，改用当前 ID 修复正文引用，check 与 check-legacy 均为 PASS，registry/config 未被改动。
- 证据驱动更新：另一 Agent 先写入 `INVESTIGATING` 状态与验证记录，代理重新 lookup 读取新证据后执行带 `--expected-status` 的 update，把 `ISSUE-1` 更新为 RESOLVED 并运行 check PASS。
- 旧别名与草案（首轮失败）：代理正确把 `task36` 解析为 TASK-1，但把旧别名复写进新草案并因“未更新实体”跳过 check；同一批的独立交接摘要漏掉 ID 与登记名称。修正 Skill 后换新沙箱重测：草案只使用 TASK-1 及其登记名称，未复写旧别名，check PASS，registry/config 未变、无编号高水位。
- 草案不铸号（独立代理）：`deepseek/deepseek-flash` 子代理在全新沙箱中搜索“缓存/cache”等关键词（0 命中），写入标注“草案，未立项，未分配 ID”的 notes.md 后 check PASS。主代理复核：未生成编号高水位、registry/config 哈希未变、草案未复写旧别名，并正确列出 TASK-1、TASK-36、ISSUE-1 作为主题相近候选。

## Skill 同步到本机 harness

本机已安装的 RepoLedger Skill 副本共 6 处：.codex、.agents、.claude、.cursor（skills 与 skills-cursor 两个根）、.qoder。同步前六处均为旧哈希
`69A388216C8263AE2900E58A0DC9B62E84E6280FF805FEDA7DF28A8FDF7C2F04`，同步后全部等于仓库版本
`909DBF0F045C1413594F99C7448FD261BE80595DF064B02F167016AA7314FE56`。
新增 `scripts/sync_skill.py`（默认同步、`--check` 只报告、`--install` 补装），`--check` 运行结果为六处 same、退出码 0。
`.gemini` brain scratch 下的同名目录是只读参考原型，不是安装副本，未改动；harness 自带 builtin skills 也未改动。

评测过程中发现并已修复两个可观察缺陷（新文档复写退役别名；独立摘要漏登记名称），这正是把行为评测与单元测试分开记录的原因。

## 子代理模型记录

首轮评测使用默认模型子代理；额度中断后按要求改用 DeepSeek。
`agentrouter/deepseek-v4-flash` 两次 spawn 均在启动阶段被 provider 拒绝：
`Provider error 400: Invalid schema for function 'mcp__cua_repl__js_reset': null is not of type "array"`，
属环境侧工具 schema 校验问题。改用用户指定的 `deepseek/deepseek-flash` 后启动正常并完成评测（结果见上节）。
这些评测均为有限样本，只证明被观察到的若干场景，不代表普遍遵循。

执行 python examples/demo.py，实际完成：初始化 schema 账本 → 分配带受控文件 anchor 的实体 → 单实体 JSON 查询 → check 通过 → 添加 TASK-999 引用 → ERR_UNREGISTERED_ENTITY，定位 next.md:1:13。
示例在临时 Git 仓库运行，未初始化或更改本项目自身账本。

python -m repo_ledger --help、pyproject.toml 解析及 git diff --check 通过。AGENTS.md 保持在 65 行以内。

## 尚未验证

构建环境缺少 flit_core。尝试仅安装到 .test-runs/build-deps 时包源返回 “No matching distribution found”；未完成 wheel/sdist 构建或 console-script 安装验证。已验证的是 python -m repo_ledger 与源码 demo。没有全局安装、发布、远端创建、提交或推送。

未测历史锚点、SHA-256 仓库、浅克隆、提交树、暂存区增量检查、跨克隆并发、状态迁移/完成证据策略；这些均未实现。搜索/更新已实现并经测试，但其并发保证仅限同一主工作区的短锁，不检测同状态备注覆盖或状态往返。没有性能承诺或借用历史项目指标。

## 后续优先级

1. index/合并提交树视图与基线历史审计，随后加入不会覆盖已有 hook 的入口。
2. 真实 Git 对象校验、历史 anchor、浅克隆诊断。
3. 按实体类型/状态的完成证据及显式基线迁移策略。
4. 构建与 Python/操作系统测试矩阵及可复现性能测量。
