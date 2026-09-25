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

演示还包含有限候选搜索与附带旧状态条件的更新。无需安装 Python 依赖，也不会更改当前项目的账本。可以用 `python -m repo_ledger --help` 查看命令。

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
| `repo-ledger search "rate" --json --limit 5` | 按 ID、名称或 legacy 字面子串查找有限候选 |
| `repo-ledger update TASK-1 --status READY --expected-status BACKLOG --json` | 在短锁内校验并更新状态；可用 `--note` 更新备注 |
| `repo-ledger check --json` | 只读校验工作树，输出诊断和可审计的扫描范围 |
| `repo-ledger check-legacy --json` | 单独运行退役代号守卫；`check` 已自动聚合它 |
| `repo-ledger tree` | 输出简易实体与父关系列表 |
| `repo-ledger index --out docs/ledger-index` | 为每个已声明类型写一页 Markdown 目录，另写总览页；省略 `--out` 时读 `[index] out_dir` |
| `repo-ledger index --check` | 在内存中重新生成并与磁盘逐字节比较，列出缺失、过期与多余页面；不写任何文件 |

查询输出不会展开整个账本；内部仍严格解析全账本。退出码：`0` 通过，`1` 规则违规（含 `index --check` 发现差异），`2` 配置错误或不支持的能力，`3` 扫描/I/O 未完成。

搜索忽略大小写，不猜测简称、不使用正则或语义相似度。默认最多返回 5 条，`--limit` 范围为 1–100；`total` 表示全部命中数。先核对候选并 lookup，再判断是否需要新实体。没有搜索命中不等于语义上不存在重复任务。

更新只接受当前 ID，只能修改 status/note，不能借 legacy 改派实体。锁内重新读取配置和账本后原子写入，与 allocate 使用同一短锁。`--expected-status` 可检测状态是否已被他人更改；冲突时重新查询和判断，不盲目重试。它不检测同状态的备注覆盖或状态往返，也不是跨克隆事务。`--note ""` 清空备注；状态合法并不证明工作完成，迁移矩阵仍未实现。

### 按类型目录页（`repo-ledger index`）

`index` 为每个已声明类型写一页 `<TYPE>.md`（没有实体的类型也写，并注明为空），另写总览 `README.md`：每个类型一行，列出 ledger.toml 中的 `description`、实体数、按状态计数和页面链接。每页首行是 HTML 注释，记录账本路径和账本文件字节 sha256 的前 12 位，并注明由 `repo-ledger index` 生成、不要手改。这里的 index 指生成的目录页，与 Git 暂存区（index 视图）无关。

- 父子关系用标题层级表达：顶层实体（无 parent，或 parent 属于其他类型）为 `##`，子实体为 `###`，依次到 `######`；更深的实体在第六级标题下改为嵌套列表，顺序不变。
- 同级先按 `order`（计划位置）再按 ID 数字排序；未开启 `independent_order` 时 order 等于序号，即按 ID 数字排序。计划位置并列时同样按 ID 数字排序。
- 标题为“ID + 完整登记名称”。标题下一行是紧凑字段：status、date、anchor（owner 布局显示为 owner；路径渲染为从页面出发的相对链接，提交哈希只显示为不带链接的代码文本）、legacy（行内代码）、supersedes 与 superseded by（两个方向都写“ID + 名称”）、note。
- parent 属于其他类型的实体列在自己类型页的顶层，并带 `parent:` 字段；父实体所在的页面在该父实体下写一行 `children of other types:`。
- 页面中每处 ID 后都紧跟完整登记名称：note 与类型 `description` 中出现的已登记 ID 若后面没有名称，生成时补上；未登记的 token 原样保留，登记名称本身逐字输出。
- 登记文本只对会触发 Markdown 或 HTML 语法的字符加反斜杠转义（例如成对星号、反引号、尖括号标签、词边界下划线）；普通文字、中文和词内下划线逐字保留，因此原文里“ID + 名称”的写法不被转义打断。
- 输出确定：只读取 ledger.toml 和一次账本字节，不调用 Git、不写时间戳，UTF-8、LF、结尾恰好一个换行；重复运行逐字节相同，与项目所在的绝对路径无关，导出的非 Git 副本也能生成。账本和输出目录建议在 `.gitattributes` 中设为 `-text` 或 `eol=lf`，否则跨平台换行转换会改变指纹或页面字节。
- `--out` 相对当前目录解析，优先于 `[index] out_dir`（相对项目根）；两者都没有时以 `ERR_INDEX_OUT_DIR` 退出码 `2` 结束。`index` 从不删除文件，拒绝覆盖首行不是生成标记的文件，也拒绝把项目根或账本所在目录用作输出目录；多余页面只在输出里列出。
- `--check` 在内存中重新生成并逐字节比较；任一页面缺失、过期，或输出目录顶层有生成器不会写的 `.md` 文件，都以退出码 `1` 列出，不写任何文件。账本任何字节变化都会让全部页面过期，因为每页页首都带账本指纹。
- 账本关系错误（parent 或 supersedes 指向不存在的实体、自引用、环）时拒绝生成，不输出残缺页面。

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

# 可选：repo-ledger index 的目录页；check = true 让 check 同时校验它们
# [index]
# out_dir = ".ledger/index"
# check = true
```

- 编号采用 `TYPE-N`，不补零，按类型递增。断号默认合法；取消或废弃实体应保留记录，不复用编号。
- `parent` 是可选单实体关系，`supersedes` 是逗号分隔的多实体关系；分别检查目标存在、自引用和环。历史引用已被替代的实体仍可合法存在。
- 默认 `order` 必须等于 ID 序号。设置 `independent_order = true` 后，`order` 成为同一类型、同一 parent 下的计划位置：可被 `update --order` 重排，只影响 `tree` 与 `index` 目录页的渲染顺序，不参与身份、状态或完成判断。此时计划位置允许并列（真实账本常出现），需要严格唯一时再设 `unique_order_within_scope = true`。
- RepoLedger 写入规范十列布局，同时接受两种既有布局：旧九列表（保存时升级为十列），以及把 `anchor` 写作 `owner`、legacy 排在 supersedes 之前的项目十列布局。未知表头一律拒绝而不猜测。
- `[reference_exemptions]` 为个别文件声明未登记的字面 token（例如教学反例或断言自身检查器的测试夹具）。豁免按文件+token 精确匹配，命中写入 `check --json` 的 `scope.suppressed`，不静默通过，也不接受形状正则。
- `legacy` 是可选的历史别名；非空值只能登记一次，且不能与任何当前 ID 共用命名空间，lookup 会返回当前 ID。正文写入只使用当前 ID，旧别名只走解码读取路径。
- 名称、备注和 legacy 支持中文、竖线与反斜杠。写入时 `|` 编码为 `\|`，反斜杠编码为 `\\`。缺失 schema、坏行、重号、重复 legacy 或冲突标记会使检查失败。
- 工作树扫描包含受控文件及未被 Git 忽略的新文件。`.md` 始终属于适用扩展名；其他扩展名由配置指定。JSON 列出实际扫描与排除项。
- 退役代号守卫只接受枚举字面量（配置中的 `forbidden_tokens` 加登记表中的 legacy），内部对字面量转义后匹配；它不接受用户提供的“形状正则”。`scope_globs`、`exclude_globs`、整文件豁免、列掩码、教学围栏和定向行豁免都会写入 JSON 审计范围。守卫不是结构化 JSON key 审计，生成或转义的 key 仍需额外检查。
- `[index]` 可选：`out_dir` 是仓库相对的目录页输出目录；`check = true`（需要 `out_dir`）让 `repo-ledger check` 同时运行目录页新鲜度检查，缺失、过期或多余页面报 `ERR_INDEX_STALE`，定位到 `<out_dir>/<页面>:1:1`。JSON 只新增 `scope.index`（out_dir、registry_sha256、pages、missing、stale、extra），已有字段不变。只有与再生成结果逐字节一致的页面才按精确路径从引用扫描和退役代号守卫中排除，并在 `excluded` 中写明原因 `generated index page verified by the index check`：这些页面的内容就是账本内容，已由逐字节再生成校验，页面上的 legacy 别名因此不会触发守卫。缺失或过期的页面（包括手改、手写的文件和符号链接）不排除，按普通文件扫描：过期页上的 legacy 别名等命中与 `ERR_INDEX_STALE` 一起报告，重新生成后随之消失；符号链接页不被跟随，报扫描不完整。目录中的其他文件照常扫描。`check-legacy` 与 `lint_all` 在 `check = true` 时运行同一比较，使用同一排除范围。无法重新生成（例如关系错误）时报 `ERR_INDEX_UNVERIFIED`，检查不完整（退出码 `3`），不会判为通过，此时页面不被排除、按普通文件扫描。未声明 `[index]` 或 `check` 为 false 时 `check` 行为完全不变，生成页按普通文件扫描（页面上的 legacy 别名会被守卫报告），此时应开启 `check`，或把页面放在扫描范围之外。

自定义类型的完整例子见 [示例配置](examples/basic_project/ledger.toml)；配置字段、空值、转义与诊断语义见[架构与格式](docs/rfc-architecture.md)。

## Agent 接入

使用 [RepoLedger Skill](skills/repo-ledger/SKILL.md)，或将以下约定纳入项目已有的 Agent 指令：

```markdown
- 引用前按原文 lookup；创建前 search 相关关键词，再 lookup 候选。不把 task36 等模糊简称自动改成当前 ID。
- 如果引用来自冻结页、旧提交说明或授权文本，先用同一个 lookup 解码 legacy，再在新正文写当前 ID；外部标准记号不进入 legacy 映射。
- 新实体必须通过 allocate 分配；使用命令返回的 ID，不自行猜号。
- 按需读取单实体及其 anchor；同一账本上下文中复用已核实结果，账本变化、切换分支/工作区或交接后刷新，不在启动时加载整个账本。
- 独立交接摘要包含当前 ID 与完整登记名称；新文档不复写旧别名，草案也应在写入后运行 check，但不铸号。
- 状态更新应依据明确证据，通过 update 的 --status/--note 和 --expected-status 写入，随后运行 check --json。
- 遇到错误先定位原因，不伪造登记、不扩大忽略范围以绕过检查；退役代号命中时运行 check-legacy 并修复或留下窄范围豁免。
- 草案、任务书和评审文本不铸号；只有落地提交内才分配并写入新 ID。锁只保护一次分配，不是跨克隆的唯一性证明。
```

### 与 cross-harness-sync 联合使用

RepoLedger 管理**实体身份、状态、关系与锚点**；独立的 cross-harness-sync 管理**当前关注点、进度叙述和会话交接**。双方都可以单独使用。

Agent A 在交接文档中引用 `TASK-1`，Agent B 读取运行上下文后执行 `lookup TASK-1 --json`，按需读取锚点并继续工作。sync 可通过公开 `extra_checks` 接口调用 `repo-ledger check`，无需再手工维护一份权威任务状态表。

这称为“按需上下文”。RepoLedger 不执行 git pull/push，也不生成交接文档。见[集成指南与双 Agent 演示](docs/integration-cross-harness-sync.md)和[可选配置](examples/sync-extra-checks.json)。

### 统一编码系统的边界

`id` 是不可变身份；默认 `order` 仍校验为 ID 序号，`independent_order = true` 时 order 是只服务渲染（`tree` 与 `index` 目录页）的计划位置，不能反推身份或完成状态。目录页的新鲜度以一次逐字节渲染为准（`index --check`），不用“最后提交日期”替代。

唯一允许的第二拼写是代码标识符和 JSON 键中的 `TYPE_N`，检查器应将它解释为 `TYPE-N`；正文仍使用连字符写法。该等价目前由当前引用扫描之外的消费者自行负责，不能声称已形成全局共享辅助函数。

决策提交台账、按 `(zone, old)` 键控的批量改名映射、数据键改名后的 canonical digest/lineage、历史提交号沿革表和按类型准入规则都保留为后续设计；本版本明确不提供这些功能。

## 当前能力与边界

| 能力 | 当前状态 |
| --- | --- |
| 严格 Markdown 解析、字段转义、合法状态集合、直接关系校验 | 已实现 |
| legacy 列、非空别名唯一性、按 legacy lookup 当前 ID | 已实现；旧 9 列账本可读取，写回时升级表头 |
| 有限候选搜索、状态/备注 update | 已实现；状态更新可附带旧状态校验，不提供语义查重或完成判定 |
| `independent_order` 开关 | 已实现；开启后 order 是同父计划位置，可改、只用于渲染，与 ID 序号解耦 |
| 项目 `owner` 列布局、未登记引用的窄豁免 | 已实现；两种布局都严格校验，未知表头仍拒绝 |
| 受控工作树文件锚点、未知引用检测、JSON 诊断与重复问题聚合 | 已实现 |
| 枚举字面量退役代号守卫、分层豁免、聚合到 `check` | 已实现；JSON key 语义审计仍是盲区 |
| 主工作区短锁、锁内重新读取、编号高水位、原子文件替换 | 已实现；支持同一主工作区多个本地进程分配 |
| 按类型目录页（`index`）：标题层级树、账本指纹、逐字节新鲜度检查、可选接入 `check` | 已实现；不调用 Git，不删除文件，不覆盖非生成文件 |
| 决策提交台账、批量改名映射、digest lineage | 未实现；明确拒绝把日期、锁或摘要猜测当作替代机制 |
| 历史锚点：commit:path、完整 commit 对象 ID | 未实现，明确拒绝 |
| 暂存区、增量、提交树检查 | 未实现；相关参数明确拒绝，绝不回退为工作树检查 |
| 状态迁移基线、完成证据策略、历史删除审计 | 后续工作 |
| hook install、CI 合并门禁 | 尚未提供 |
| 多 worktree 或跨克隆铸号 | 不支持；linked worktree 分配明确拒绝 |

`check` 通过仅表示**本次工作树配置范围内的校验通过**。扫描期间并发编辑不提供一致性快照保证。编号回退保护依赖保留主工作区的 `.git` 高水位元数据，不能视为跨克隆原子分配保证。

下一阶段优先实现 Git 暂存区（index 视图）与待合并提交树检查，再补历史锚点与按类型、状态配置的证据规则。50ms 只是未来小型增量场景的待测目标，目前没有性能承诺。

## 开发与验证

```sh
python -m pip install -e ".[test]"
python -m pytest -v
```

### 把 Skill 同步到本机各 harness

`skills/repo-ledger/SKILL.md` 是唯一源文件；安装到各 harness 后需要同步更新：

```sh
python scripts/sync_skill.py            # 同步已安装的副本
python scripts/sync_skill.py --check    # 只报告差异，有漂移时退出码 1
python scripts/sync_skill.py --install  # 额外安装到存在但尚未安装的 harness
```

脚本按 SHA-256 比对，只处理已探测到的 harness Skill 根目录，不触碰其他 Skill。

本轮验证：Windows、Python 3.14.5 上 **135 个测试通过**，覆盖 legacy 解码/唯一性、退役代号守卫、有限候选搜索、受锁状态更新与并发冲突，以及 Agent 工作流回归。另做了独立代理行为评测：未知简称与证据驱动更新通过；首轮评测发现“新文档复写旧别名”和“交接摘要漏 ID/名称”两处问题，修订 Skill 后重测通过，细节与局限见[验证记录](docs/validation.md)。这些结果来自本项目，未引用外部长期项目的测试或性能数字。

目录页一轮：Linux、Python 3.11.15 上 **183 个测试通过**（新增 48 个），并在一个真实项目账本的导出副本（317 个实体、11 种类型）上只读试生成，见[验证记录](docs/validation.md)。

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
