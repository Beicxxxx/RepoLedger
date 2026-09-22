# RepoLedger 📜

> **Git-native entity tracking for long-running AI agent work.**
>
> 给任务、决策与问题稳定的编号，让每次引用都能找到登记记录和证据。

[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#当前能力与边界)

RepoLedger 是一个保存在 Git 仓库里的实体账本。它通过 **CLI 分配编号、Markdown 登记、物理锚点和只读静态检查**，帮助 Agent 在跨会话协作时追踪同一件事。

无需外部数据库或后台服务，运行时仅依赖 Python 标准库与 Git。配套 Skill 指导 Agent 按需查询，确定性规则由 CLI 执行。

[快速上手](#快速上手) · [配置](#配置) · [Agent 接入](#agent-接入) · [能力边界](#当前能力与边界) · [设计文档](docs/rfc-architecture.md)

## 为什么需要 RepoLedger？

一个项目经过数周、多个 Agent 和许多次交接后，容易出现这些问题：

| 协作中遇到的问题 | RepoLedger 提供的支持 |
| --- | --- |
| 新 Agent 不清楚某项工作是否已有登记，又创建一份任务 | 先查询已有实体；新实体通过 `allocate` 获取稳定 ID |
| 注释写着“实现 TASK-99”，却找不到这项任务 | `check` 在配置扫描范围内检出未登记引用并定位到行列 |
| 一个代号只有简短标题，没有需求或证据来源 | 每条记录默认关联受控文件 `anchor`，也可以先锚定提案 |
| 为了解当前任务，接手者被迫读整个账本和聊天历史 | `lookup <ID> --json` 只返回一个实体及其直接关系 |
| 历史代号在正文里悄悄复活，或旧代号被误当成新实体 | `legacy` 别名解码与 `check-legacy` 守卫把旧写法导回当前 ID |

首版关注**引用完整性与可追溯性**。它不能判断两个不同标题是否表达同一件事，也不把文件存在解释为工作完成。

## 快速上手

需要 Python 3.11+ 和 Git。当前从源码使用；尚未发布 PyPI 软件包。

### 1. 获取源码并体验闭环

```sh
git clone https://github.com/Beicxxxx/RepoLedger.git
cd RepoLedger
python examples/demo.py
```

演示在临时 Git 仓库中依次完成：

```text
初始化账本 → 分配 TASK-1 → 单实体查询 → 检查通过
                                      ↓
                         写入 TASK-999 → 检出未登记引用
```

这个演示无需安装 Python 依赖，也不会更改当前项目的账本。可以用 `python -m repo_ledger --help` 查看命令。

### 2. 安装本地 CLI

在 RepoLedger 源码目录运行：

```sh
python -m pip install -e .
repo-ledger --help
```

安装需要构建依赖 `flit_core`；测试还需要 `pytest`。源码运行已验证，本轮环境未完成安装与 wheel/sdist 构建验证，详见[验证记录](docs/validation.md)。

### 3. 在新项目中登记第一项任务

以下命令创建独立示例仓库，并先写入、跟踪一份提案文件：

```sh
git init ledger-demo
cd ledger-demo
python -c "from pathlib import Path; Path('docs').mkdir(); Path('docs/proposal.md').write_text('# Rate limiter proposal\n', encoding='utf-8')"
git add docs/proposal.md
repo-ledger init
repo-ledger allocate TASK "Implement rate limiting" --anchor docs/proposal.md --status IN_PROGRESS --json
repo-ledger lookup TASK-1 --json
repo-ledger check --json
```

`init` 创建 `ledger.toml` 与 `.ledger/ENTITY_REGISTRY.md`，不会覆盖已有配置或账本。默认类型为 `TASK`、`DECISION`、`ISSUE`，支持配置扩展。

`anchor` 是证据载体，不是责任人。首版要求它指向仓库内已被 Git 跟踪的现有普通文件；探索性任务可以引用需求或提案，无需提前创建实现文件。

### 4. 检出一个未登记引用

继续在示例仓库中运行：

```sh
python -c "from pathlib import Path; Path('next.md').write_text('Investigate TASK-999\n', encoding='utf-8')"
repo-ledger check --json
```

检查以退出码 `1` 结束。返回的诊断包含以下字段（节选）：

```json
{
  "code": "ERR_UNREGISTERED_ENTITY",
  "location": "next.md:1:13",
  "entity": "TASK-999",
  "reason": "Reference has no registered entity"
}
```

修复顺序：**先查询已有实体 → 判断误写还是确有新实体 → 修正引用或显式分配**。`check` 不会自动补登记，也不会猜测替代编号。

## 命令一览

| 命令 | 用途 |
| --- | --- |
| `repo-ledger init` | 初始化配置和带 schema 的账本 |
| `repo-ledger allocate TASK "Title" --anchor docs/proposal.md` | 校验锚点并分配新 ID |
| `repo-ledger lookup TASK-1 --json` | 按当前 ID 或历史 `legacy` 别名返回当前实体 |
| `repo-ledger check --json` | 只读校验工作树，输出诊断和可审计的扫描范围 |
| `repo-ledger check-legacy --json` | 单独运行退役代号守卫；`check` 已自动聚合它 |
| `repo-ledger tree` | 输出简易实体与父关系列表 |

查询输出不会展开整个账本；内部仍严格解析全账本。退出码：`0` 通过，`1` 规则违规，`2` 配置错误或不支持的能力，`3` 扫描/I/O 未完成。

## 配置

`init` 生成可直接使用的配置。以下示例展示默认扫描范围，实体类型和状态采用内置默认值：

```toml
[ledger]
schema_version = "1.0"
registry_path = ".ledger/ENTITY_REGISTRY.md"
allow_gaps = true
code_extensions = [".py", ".ts", ".js", ".go", ".rs", ".json", ".md"]
ignore_globs = []

[legacy_guard]
enabled = true
scope_globs = ["*.py", "**/*.py", "*.json", "**/*.json", "*.md", "**/*.md"]
exclude_globs = []
forbidden_tokens = []
file_exemptions = []
column_masks = {}
fence_exemptions = []
string_line_exemptions = {}
```

- 编号采用 `TYPE-N`，不补零，按类型递增。断号默认合法；取消或废弃实体应保留记录，不复用编号。
- `parent` 是可选单实体关系，`supersedes` 是逗号分隔的多实体关系；分别检查目标存在、自引用和环。历史引用已被替代的实体仍可合法存在。
- `legacy` 是可选的历史别名；非空值只能登记一次，且不能与任何当前 ID 共用命名空间，lookup 会返回当前 ID。正文写入只使用当前 ID，旧别名只走解码读取路径。
- 名称、备注和 legacy 支持中文、竖线与反斜杠。写入时 `|` 编码为 `\|`，反斜杠编码为 `\\`。缺失 schema、坏行、重号、重复 legacy 或冲突标记会使检查失败。
- 工作树扫描包含受控文件及未被 Git 忽略的新文件。`.md` 始终属于适用扩展名；其他扩展名由配置指定。JSON 列出实际扫描与排除项。
- 退役代号守卫只接受枚举字面量（配置中的 `forbidden_tokens` 加登记表中的 legacy），内部对字面量转义后匹配；它不接受用户提供的“形状正则”。`scope_globs`、`exclude_globs`、整文件豁免、列掩码、教学围栏和定向行豁免都会写入 JSON 审计范围。守卫不是结构化 JSON key 审计，生成或转义的 key 仍需额外检查。

自定义类型的完整例子见 [示例配置](examples/basic_project/ledger.toml)；配置字段、空值、转义与诊断语义见[架构与格式](docs/rfc-architecture.md)。

## Agent 接入

使用 [RepoLedger Skill](skills/repo-ledger/SKILL.md)，或将以下约定纳入项目已有的 Agent 指令：

```markdown
- 引用或创建实体前，先检查相关已有记录，并用 repo-ledger lookup <ID> --json 查询。
- 如果引用来自冻结页、旧提交说明或授权文本，先用同一个 lookup 解码 legacy，再在新正文写当前 ID；外部标准记号不进入 legacy 映射。
- 新实体必须通过 allocate 分配；使用命令返回的 ID，不自行猜号。
- 按需读取单实体及其 anchor，不在启动时加载整个账本。
- 状态更新应依据明确证据，更新后运行 repo-ledger check --json。
- 遇到错误先定位原因，不伪造登记、不扩大忽略范围以绕过检查；退役代号命中时运行 check-legacy 并修复或留下窄范围豁免。
- 草案、任务书和评审文本不铸号；只有落地提交内才分配并写入新 ID。锁只保护一次分配，不是跨克隆的唯一性证明。
```

### 与 cross-harness-sync 联合使用

RepoLedger 管理**实体身份、状态、关系与锚点**；独立的 cross-harness-sync 管理**当前关注点、进度叙述和会话交接**。双方都可以单独使用。

Agent A 在交接文档中引用 `TASK-1`，Agent B 读取运行上下文后执行 `lookup TASK-1 --json`，按需读取锚点并继续工作。sync 可通过公开 `extra_checks` 接口调用 `repo-ledger check`，无需再手工维护一份权威任务状态表。

这称为“按需上下文”。RepoLedger 不执行 git pull/push，也不生成交接文档。见[集成指南与双 Agent 演示](docs/integration-cross-harness-sync.md)和[可选配置](examples/sync-extra-checks.json)。

### 统一编码系统的边界

`id` 是不可变身份；当前实现仍把 `order` 校验为 ID 序号，渲染视图和独立可变的计划顺序尚未实现。若未来拆开二者，order 只能服务渲染，不能反推身份或完成状态。新鲜度也必须以一次逐字节渲染为准，不能用“最后提交日期”替代。

唯一允许的第二拼写是代码标识符和 JSON 键中的 `TYPE_N`，检查器应将它解释为 `TYPE-N`；正文仍使用连字符写法。该等价目前由当前引用扫描之外的消费者自行负责，不能声称已形成全局共享辅助函数。

决策提交台账、按 `(zone, old)` 键控的批量改名映射、数据键改名后的 canonical digest/lineage、历史提交号沿革表和按类型准入规则都保留为后续设计；本版本明确不提供这些功能。

## 当前能力与边界

| 能力 | 当前状态 |
| --- | --- |
| 严格 Markdown 解析、字段转义、合法状态集合、直接关系校验 | 已实现 |
| legacy 列、非空别名唯一性、按 legacy lookup 当前 ID | 已实现；旧 9 列账本可读取，写回时升级表头 |
| 受控工作树文件锚点、未知引用检测、JSON 诊断与重复问题聚合 | 已实现 |
| 枚举字面量退役代号守卫、分层豁免、聚合到 `check` | 已实现；JSON key 语义审计仍是盲区 |
| 主工作区短锁、锁内重新读取、编号高水位、原子文件替换 | 已实现；支持同一主工作区多个本地进程分配 |
| order 渲染视图、决策提交台账、批量改名映射、digest lineage | 未实现；明确拒绝把日期、锁或摘要猜测当作替代机制 |
| 历史锚点：commit:path、完整 commit 对象 ID | 未实现，明确拒绝 |
| 暂存区、增量、提交树检查 | 未实现；相关参数明确拒绝，绝不回退为工作树检查 |
| 状态迁移基线、完成证据策略、历史删除审计、标题搜索 | 后续工作 |
| hook install、CI 合并门禁 | 尚未提供 |
| 多 worktree 或跨克隆铸号 | 不支持；linked worktree 分配明确拒绝 |

`check` 通过仅表示**本次工作树配置范围内的校验通过**。扫描期间并发编辑不提供一致性快照保证。编号回退保护依赖保留主工作区的 `.git` 高水位元数据，不能视为跨克隆原子分配保证。

下一阶段优先实现 index/待合并提交树检查，再补历史锚点与按类型、状态配置的证据规则。50ms 只是未来小型增量场景的待测目标，目前没有性能承诺。

## 开发与验证

```sh
python -m pip install -e ".[test]"
python -m pytest -v
```

本轮验证：Windows、Python 3.14.5 上 **66 个测试通过**，新增覆盖 legacy 解码/唯一性、旧表兼容、退役代号守卫、聚合接入和分层豁免。完整环境、命令与未验证项见[验证记录](docs/validation.md)。这些结果来自本项目，未引用外部长期项目的测试或性能数字。

| 路径 | 内容 |
| --- | --- |
| `repo_ledger/` | Python CLI 与核心实现 |
| `skills/repo-ledger/` | 配套 Agent Skill |
| `tests/` | 本项目的回归测试 |
| `examples/` | 可运行闭环、账本示例和可选集成配置 |
| `docs/` | 架构、集成与验证说明 |

GitHub 仓库：[Beicxxxx/RepoLedger](https://github.com/Beicxxxx/RepoLedger)。Python distribution 与 CLI 采用名称 `repo-ledger`，import 为 `repo_ledger`；PyPI 名称可用性尚未核实，软件包尚未发布。

## License

[MIT](LICENSE) © 2026 Beichen.
