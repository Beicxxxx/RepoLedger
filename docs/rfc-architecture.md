# RepoLedger 首轮架构与格式

## 产品边界

运行时为 Python 3.11+ 标准库与 Git CLI；配置用 tomllib。无数据库、MCP Server、后台服务或分布式调度。只交付 RepoLedger CLI 与 RepoLedger Skill；sync 负责跨会话上下文与交接，双方独立可用。

现有目录确有原型，本轮在其文件与表格式上修订。旧版跳过坏行、仅凭 hash 外形接受锚点、吞掉扫描读取错误、用工作树 hook 冒充提交检查的行为已移除。原型内的 sync 副本不属于交付，不修改外部安装版本。

## 数据格式与 Fail-Closed

默认 ledger.toml 位于 Git 仓库根；权威账本为 .ledger/ENTITY_REGISTRY.md。
第一行必须精确为 `<!-- schema: 1.0 -->`，只支持 1.0。此前言允许空行、`# ` 标题和 `> ` 说明，新写入账本使用如下十列：

```text
| id | name | status | parent | order | anchor | supersedes | date | legacy | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
```

id、name、status、order、date 必填；anchor 默认必填，可按类型 require_anchor 配置。parent、supersedes、legacy、note 用空单元格表示空值；不要用 “-” 或 “null”。legacy 是旧代号到当前 ID 的只读映射，非空值不得重复，也不能与当前 ID 共用命名空间。为保持增量兼容，读取器也接受旧的九列表头（此时 legacy 为空），第一次保存会升级为十列；不接受任意其他列数。

`id` 是身份，append-only，不能由 order、标题或日期推断。`order` 目前仍要求等于 ID 的十进制序号；未来若提供渲染视图，order 才能独立表示计划位置，并且只能用于渲染，不能参与身份、状态或完成推断。

字段内 `|` 编码为 `\|`，反斜杠编码为 `\\`；先编码反斜杠再编码竖线。读取逐字符识别这两种转义，不直接 split("|")，不接受其他转义。单元格两侧空白仅作排版；API 拒绝有首尾空白的值。拒绝换行、控制字符和 Unicode 行分隔符。中文和字段内部空格保留。Markdown 代码围栏不能代替转义。

缺失/未知/重复 schema、重复 ID、错列、非法字段、坏转义、无法解析的行及冲突标记都失败，不跳行报成功。错误至少包含稳定 code、file:line:column、entity（若可解析）、reason、suggestion。行结构错误定位到行首并说明列数或转义位置；引用错误定位到实际字符列。

读取路径与写入路径分开：冻结页、旧提交说明或授权文本中的 legacy 只能通过 `lookup` 解码到今天的 ID；新正文只写当前 ID。RepoLedger 不把外部标准记号（例如 Unicode/IRG 记号）放进 legacy 映射，也不允许用 legacy 重新铸造一个新 ID。`update` 只接受当前 ID 并仅修改 status/note，不能重命名身份或改派 legacy；历史手工修改的不可变性审计仍未实现。

TYPE-N：类型为大写字母与下划线，首字母大写；N 为无前导零正整数。每类型行序严格递增，默认允许断号。取消/废弃通过状态保留记录，不删记录、不重排、不回收编号。类型与合法状态来自配置，未知配置项拒绝。旧 doc_dirs 兼容接受但不限制扫描目录，避免悄悄漏扫；建议不再配置它。

## 表布局与 order 语义

读取器只接受三种已声明布局，绝不猜测未知表头：规范十列（anchor，supersedes 在 legacy 之前）、项目十列（owner 即证据载体，legacy 在 supersedes 之前）、旧九列（无 legacy，首次保存升级为规范十列）。owner 与 anchor 指同一列的同一含义。写入沿用载入时的布局，新账本使用规范布局。

默认 order 必须等于 ID 的十进制序号；independent_order = true 后 order 成为同一类型、同一 parent 作用域内的计划位置，可被 update --order 重排，只用于 tree 渲染，不参与身份、状态或完成判断。计划位置允许并列；unique_order_within_scope = true 才把同作用域重复视为错误。无论开关如何，order 都必须是正整数、不补零，依然禁止用 order 反推身份。


## 关系与状态

parent 为可选单 ID；supersedes 为逗号分隔的多个不同 ID。分别验证目标存在、自引用和有向环；暂不定义混合两类边的环为违规。不引入通用图引擎或 derived_from。

supersedes 不使旧实体消失，也不使历史引用自动失效。首轮校验存在性，不推断当前适用性。

首轮仅校验合法状态集合。迁移矩阵、完成证据策略未实现，任何暗示其启用的配置字段都会被拒绝。下一轮应采用显式 Git 基线比较 old/new；初次登记、删除、状态变化分别定义规则。完成证据应按类型和状态配置，不能把文件存在解释为完成。

## 锚点

本轮仅支持规范的仓库相对 POSIX 文件路径。拒绝绝对路径、反斜杠、冒号、空组件、.、..、.git 组件及符号链接；解析后的目标须留在仓库内。路径必须在 Git index 受控清单中且在工作树为普通文件。探索任务可锚定需求或理论文件。未提交但已暂存的新文件可作工作树锚点；这不表示 index 检查已实现。

目标完整设计有三种形式：相对文件路径、commit:path、完整 commit 对象 ID。当前所有含冒号的形式以及裸 40/64 位十六进制 token 均返回 ERR_UNSUPPORTED_ANCHOR，不据外观认定 commit 有效。哈希形文件名请置于目录下以消歧。

后续历史实现须按 Git 对象格式识别完整 OID，核实对象确为 commit，commit:path 对应 blob 存在，明确诊断缺失历史/浅克隆且不自动 fetch。历史锚点应允许工作树文件删除。现在删除一个仍被路径锚定的文件会失败，这是已知限制。

## 分配与并发

唯一铸号来源是主工作区的当前账本。linked worktree 或 separate git-dir 分配被拒绝；不是共享锁后读取各自账本。多个克隆之间没有原子分配保证。

短锁 .git/repo-ledger-allocate.lock 用排他创建实现，覆盖重新读取、验证、取号、写入。超时不会偷锁；崩溃遗留锁须确认没有写入进程后人工清理。扫描与查询不会创建锁。

.git/repo-ledger-serials.json 是本地保守编号高水位，不是第二份实体状态表。先原子持久化高水位，再原子替换账本；中断最多保留一个断号。账本回退仍不会重复发号，前提是保留该工作区的 .git 元数据。迁移铸号职责到新克隆、丢失高水位、并行切换分支或手工改账本均不在并发保证内；必须保留全部发行记录并人工协调。未实现跨 Git 历史的删除审计。不得用重复发号消解合并冲突。

唯一性不靠锁。登记表故意不声明 `merge=union`：两人在表尾追加时应产生可见文本冲突，而不是把同一号静默并成一行；读取器仍对同号两行报错。短锁有等待超时，没有过期自动回收 TTL；其他克隆不可见。allocate 和 update 共用该短锁，只保护本地主工作区的一次写入。

草案、任务书和评审文本不铸号；铸号应发生在落地提交中，分配、追加登记行和把当前 ID 写进正文属于同一个落地边界。仓库外草案若先写号，落地时可能与已经发行的号冲突；Skill 因此只允许用名字指代尚未落地的实体。

## 扫描视图

当前 check 从 Git 获取受控清单和未忽略的新文件，读取工作树内容。默认扫描 .md 及 code_extensions；ignore_globs 使用区分大小写的 fnmatch 仓库相对路径匹配。受控文件不受 .gitignore 排除，显式 ignore_globs 除外；账本始终先解析。非 UTF-8、受控文件缺失、逃逸路径、子模块和未合并 index 均不静默通过。扫描期间并发编辑不提供一致性快照保证。

JSON scope 给出 tracked、untracked、git_ignored、ignore_globs、scanned、excluded；重复错误按 code/entity/reason/category 聚合，count 保留总数，最多十个位置。仅识别配置类型的数字型引用，包含非法前导零；不扫描其他类型及任意自然语言代号。

### 退役代号守卫

`repo-ledger check-legacy` 是只读的显式守卫，`repo-ledger check` 必须聚合调用它。守卫的 token 集合是配置 `legacy_guard.forbidden_tokens` 与登记表非空 `legacy` 值的并集；匹配器只把这些词逐个 `re.escape` 后组成字面量枚举，不接受用户提供的形状正则。这样能避免把外部记号、普通数据数字或自然语言前缀误判为退役代号。

`legacy_guard` 声明扫描范围 `scope_globs`、范围排除 `exclude_globs`、整文件 `file_exemptions`、一基列号 `column_masks`、教学围栏 `fence_exemptions` 和一基行号 `string_line_exemptions`。每个命中给出文件、行列、旧 token/解析到的实体和可执行下一步；JSON scope 同时列出 scanned 与 excluded。登记表本身始终单独解析，不把其中的 legacy 定义误报为正文复活。

豁免不是把规则改成“通过”：它们只缩小声明范围，并保留在审计输出中。守卫是行文本检查，不是 JSON 语义审计；它不证明生成的、转义的或只存在于 JSON 对象 key 语义中的旧词已被覆盖。引用守卫通过时，必须同时说明当次 scope、排除区和文件清单，不能只引用 pass 数。

[reference_exemptions] 允许按文件 glob 声明未登记的字面 token，供教学反例或断言自身检查器的测试夹具使用。匹配是文件+token 双重精确，不使用形状正则；每次命中都会写入 scope.suppressed（含文件、行列、token，最多 50 条），审计可见。豁免只缩小未登记引用的报告范围，不改变已登记实体的校验，也不能隐藏同一文件里的其他 token。


暂存区、提交树和增量未实现，显式参数返回 ERR_UNSUPPORTED_VIEW。后续 hook 必须读取 index 的配置、账本和文件，测试部分暂存；新增/修改可局部扫，删除/重命名/配置/账本/锚点影响应升级全量。CI 必须检查待合并结果的完整提交树。本地 hook 只是反馈入口，不应覆盖已有 hook；当前无 hook 安装命令。

### 尚未落码的长期项目经验

决策规则“一个决策一个提交，正文在提交信息、另加无限制追加台账；推翻只加新行”是推荐治理约定，RepoLedger 当前不生成或校验决策台账。`TYPE_N` 只作为代码标识符和 JSON key 的唯一允许第二拼写；正文使用 `TYPE-N`，当前 CLI 未声称有跨消费者共享的规范化辅助函数。

按 `(zone, old)` 键控的改名映射、精确文件/目录前缀/通配符优先级、提交说明域与文件域分离、幂等应用器、摘要重钉与 `artifact | old_root | new_root | canonical_digest | snapshot` lineage 表都尚未实现。数据键改名会改变文件字节，未来若支持 commit:path 或哈希锚点，必须先证明改名前后“键映射后规范化 JSON”的 canonical digest 相等，再重算根摘要和钉点；旧收据中的摘要仍原样保留。历史重写同理：旧提交号只能原样保留并另立 old→new 沿革表，且须证明文件树逐字节未变。本版本明确拒绝这些锚点与审计能力。

类型准入（完整英文单词、全大写、至少四字母、两字说明、全库零命中后才加入词表）、每类型在登记表头声明状态集合、渲染页摘要/新鲜度和“现在在这里”标记，均是未来设计，不由本轮 Skill 另立一套规则。

## 查询、缓存与更新

`search QUERY --json --limit 5` 只读解析账本，在 id/name/legacy 上做忽略大小写的字面子串匹配。精确 ID/legacy 命中优先，其次精确名称，再次普通子串；同级保留账本行序。返回 query、total、limit 和有限 results，每项含 id/name/status/anchor/parent/supersedes/legacy，不展开 note 或历史。空查询及 1–100 范围外的 limit 拒绝。搜索不做正则、拼写规范化或语义去重。

`lookup` 按原文精确查当前 ID 或已登记 legacy，不把 task36 自动解释为 TASK-36。Skill 允许复用同一仓库/工作区、同一已知账本状态下的查询；账本被任一 Agent 修改、切换分支/工作区、交接或无法确定新鲜度时必须刷新。这是上下文复用约定，不是 CLI 持久缓存，也没有引入另一个状态文件。

`update ID --status VALUE --note TEXT [--expected-status OLD]` 只允许更新 status/note，至少指定一项。空 note 表示清空。写入时要求主工作区，在与 allocate 相同的短锁内重新加载配置和账本，验证状态词汇、字段转义、关系和锚点后原子替换；不取号、不修改高水位。配置位置变化须拒绝陈旧目标，不能更新旧账本。

expected-status 是可选的旧值条件，不匹配时返回 ERR_UPDATE_CONFLICT 且不写入。它只检测状态值变化，不是版本号或迁移规则：同状态下两次 note 写入仍可能后写覆盖，状态往返也不会被检测。不同字段的协作更新保留锁内读到的未修改字段。并发分支切换、手工改文件及跨克隆写入不在锁保证内。

## 模块与后续顺序

config：配置与 legacy_guard；registry：严格 codec、legacy 映射、分配与更新；search：有限候选检索；git：Git inventory 和路径约束；linter：关系/锚点/引用/退役代号守卫；cli：命令与诊断；errors：共享诊断结构。

优先级：1. index 与合并提交树视图及基线审计；2. 历史锚点与 SHA-1/SHA-256/浅克隆测试；3. 类型/状态完成证据与迁移规则；4. 非覆盖 hook 与更细粒度并发版本检查。性能测量在语义稳定后进行，须报告环境、文件规模和方法。
