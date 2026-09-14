# 20260914 实验补齐产物

本批次严格依据 [Linux 操作手册](../../docs/operations-linux.md) 补齐前一批次未完成的证据：重试有失败请求的主比较轮次、正常文本观察、结果汇总及服务器侧记录说明。没有新增策略、工作负载、请求数、速率或调度参数。服务器使用 A6000、Qwen2.5-7B-Instruct、TP=1、BF16、Triton attention、PyTorch sampling；实验结束后服务器没有遗留本项目进程，外部 Ollama 服务未停止、重启或修改。

## 运行清单

| run_id | 用途 | 设置 | 结果 | 详细证据 |
| --- | --- | --- | --- | --- |
| `20260914-main-prefix-r05-s2-fcfs-n600-retry1` | 重试 `20260911` 主比较中失败的 FCFS 轮次 | `prefix-conflict`，0.5 req/s，600 请求，seed=2，FCFS，K=64，aging=500 ms | 600 发送、599 成功、1 个 `ServerDisconnectedError`；失败请求无服务端记录 | 服务器保留；待补轻量证据 |
| `20260914-main-prefix-r05-s2-fcfs-n600-retry2` | 同条件第二次重试 | 同上 | 600 发送、599 成功、1 个 `ServerDisconnectedError`；失败请求无服务端记录 | 服务器保留；待补轻量证据 |
| `20260914-main-prefix-r05-s2-fcfs-n600-retry3` | 同条件第三次重试 | 同上 | 600 发送、599 成功、1 个 `ServerDisconnectedError`；失败请求无服务端记录 | 服务器保留；待补轻量证据 |
| `20260914-main-prefix-r05-s3-lpm-n600-retry1` | 重试 `20260911` 主比较中失败的 LPM 轮次 | `prefix-conflict`，0.5 req/s，600 请求，seed=3，LPM，K=64，aging=500 ms | 600/600 成功，服务端记录完整 | 服务器保留；待补轻量证据 |
| `20260914-main-prefix-r05-s3-dfs-weight-n600-retry1` | 重试 `20260911` 主比较中失败的 DFS-weight 轮次 | `prefix-conflict`，0.5 req/s，600 请求，seed=3，DFS-weight，K=64，aging=500 ms | 600/600 成功，服务端记录完整 | 服务器保留；待补轻量证据 |
| `20260914-text-fcfs` | 正常文本功能观察 | `workloads/text-check.jsonl`，FCFS，K=64，aging=500 ms | 3/3 成功，无错误；包含文本、完成原因和输出长度 | 服务器保留；待补轻量证据 |
| `20260914-text-short-remaining` | 正常文本功能观察 | 同一输入，short-remaining，K=0，aging=500 ms | 3/3 成功，无错误；包含文本、完成原因和输出长度 | 服务器保留；待补轻量证据 |

## 失败证据

`fcfs` 的四次同条件运行（原始轮、`retry1`、`retry2`、`retry3`）各有一个不同的客户端 `ServerDisconnectedError`，失败请求没有进入 `server-requests.jsonl`。据服务器说明，服务器返回码为 0，日志没有 OOM 或服务崩溃证据；收尾阶段的 `CancelledError` 来自 `run_case` 按手册结束服务进程时的后台取消。原始目录和四个分析结果均保留，不能把这些轮次标记为零失败。

`20260911` 主比较的 30 轮中，27 轮为 600/600；`r05/seed=2/fcfs`、`r05/seed=3/lpm`、`r05/seed=3/dfs-weight` 各有一个失败。后两轮的 `20260914` 同条件重试均为 600/600；FCFS 条件仍保留上述失败缺口。主比较汇总在 [results/20260911](../20260911/)；`repair-comparison.csv` 仅汇总本批次重试轮次，不替换主比较表。

## 正常文本观察

修正了环境中 `apply_chat_template` 返回 `BatchEncoding` 的序列化问题，将 `input_ids` 转换为普通 JSON 数组后在服务器生成 `workloads/text-check.jsonl`。两个策略均完成 3 个问题；据服务器人工检查，两轮输出一致，第二个问题正确得到 391，三个请求均有 `finish_reason` 且无错误。`text-0` 达到 256 token 上限，另外两个请求正常停止。该观察不计入合成性能主表。

## 文件说明

- 每个 CSV、PNG 和 `repair-comparison.*` 均由完整运行目录分析生成。
- 本批次 7 个运行的完整记录保留在服务器 `runs/` 目录，归档未上传；逐请求标量、错误片段与文本正文待按手册补齐。
- `code/` 保留本批次实际使用的后台续跑和修复脚本副本；脚本源文件位于项目 `scripts/`。
- `config-used.json`、环境包清单、源码提交和工作差异用于追溯实际运行条件。
- 本目录不包含模型权重、`.venv` 或离线 wheel。
