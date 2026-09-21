# 首轮验证记录

日期：2026-09-21。环境：Windows，Python 3.14.5，pytest 9.1.1。
Python 3.11 是声明的最低版本，本次未执行 3.11 或 Linux/macOS 矩阵。

## 实际执行

首次原型测试因默认临时目录访问受限而未运行成功；改为仓库内新建 .test-runs 目录，并禁用不可写的 pytest 缓存。最终命令：

```sh
python -m pytest -v -p no:cacheprovider --basetemp .test-runs/final
```

结果：60 passed in 20.20s，无跳过。该时间为测试套件耗时，不是 CLI 性能基准。
重跑时使用新的 basetemp 子目录，避免 pytest 清理已有目录。

覆盖 schema 缺失/未知版本、中文/竖线/连续反斜杠/空字段往返、非法控制字符、错列、重号、无法解析记录、合并冲突、未知引用、非法状态、无效锚点、自引用与关系环、六个独立进程竞争分配、锁超时、账本回退与写入中断后的编号保留、定制类型、只读扫描、聚合诊断、UTF-8 失败与受控文件删除。
还验证 linked worktree 拒绝铸号，以及 index 与工作树不同时工作树模式仍读取工作树；暂存区模式明确拒绝，不能将此测试解释为已实现 index 校验。

执行 python examples/demo.py，实际完成：初始化 schema 账本 → 分配带受控文件 anchor 的实体 → 单实体 JSON 查询 → check 通过 → 添加 TASK-999 引用 → ERR_UNREGISTERED_ENTITY，定位 next.md:1:13。
示例在临时 Git 仓库运行，未初始化或更改本项目自身账本。

python -m repo_ledger --help、pyproject.toml 解析及 git diff --check 通过。AGENTS.md 为 34 行。

## 尚未验证

构建环境缺少 flit_core。尝试仅安装到 .test-runs/build-deps 时包源返回 “No matching distribution found”；未完成 wheel/sdist 构建或 console-script 安装验证。已验证的是 python -m repo_ledger 与源码 demo。没有全局安装、发布、远端创建、提交或推送。

未测历史锚点、SHA-256 仓库、浅克隆、提交树、暂存区增量检查、跨克隆并发、状态迁移/完成证据策略；这些均未实现。没有性能承诺或借用历史项目指标。

## 后续优先级

1. index/合并提交树视图与基线历史审计，随后加入不会覆盖已有 hook 的入口。
2. 真实 Git 对象校验、历史 anchor、浅克隆诊断。
3. 按实体类型/状态的完成证据及显式基线迁移策略。
4. 构建与 Python/操作系统测试矩阵、轻量搜索及可复现性能测量。
