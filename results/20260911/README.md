# 20260911 实验产物

本批次依据新版操作手册，在 A6000、Qwen2.5-7B-Instruct、TP=1、BF16、Triton attention、PyTorch sampling 配置下，完成候选范围与 trace/no-trace 对照，并完成 `prefix-conflict` 两档速率、600 请求、3 个 seed 的主比较。历史 300 请求、4 req/s 的候选范围和 trace/no-trace 结果与主比较共存于本日期目录；每轮使用独立端口和独立运行目录。主比较 30 轮中 27 轮为 600/600，3 轮各有 1 个客户端断开，完整记录和原始包均保留。

## 运行清单

| run_id | workload | seed | rate | K | 状态 | 计划/成功 | 短请求成功数 | short TTFT P95/P99 | 原始包 |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | --- |
| `20260911-short-remaining-prefix-r4-s2-k128` | `prefix-conflict` | 2 | 4.0 | 128 | `finished` | 300/300 | 99 | 20.956/27.716 s | [raw/20260911-short-remaining-prefix-r4-s2-k128.tar.gz](raw/20260911-short-remaining-prefix-r4-s2-k128.tar.gz) |
| `20260911-short-remaining-prefix-r4-s2-k0-retry1` | `prefix-conflict` | 2 | 4.0 | 0 | `finished` | 300/300 | 99 | 5.140/5.989 s | [raw/20260911-short-remaining-prefix-r4-s2-k0-retry1.tar.gz](raw/20260911-short-remaining-prefix-r4-s2-k0-retry1.tar.gz) |
| `20260911-short-remaining-prefix-r4-s3-k128` | `prefix-conflict` | 3 | 4.0 | 128 | `finished` | 300/300 | 106 | 11.861/22.946 s | [raw/20260911-short-remaining-prefix-r4-s3-k128.tar.gz](raw/20260911-short-remaining-prefix-r4-s3-k128.tar.gz) |
| `20260911-short-remaining-prefix-r4-s3-k0` | `prefix-conflict` | 3 | 4.0 | 0 | `finished` | 300/300 | 106 | 2.039/2.236 s | [raw/20260911-short-remaining-prefix-r4-s3-k0.tar.gz](raw/20260911-short-remaining-prefix-r4-s3-k0.tar.gz) |
| `20260911-trace-prefix-r4-s2-short-remaining-k64` | `prefix-conflict` | 2 | 4.0 | 64 | `finished` | 300/300 | 99 | 201.093/227.554 s | [raw/20260911-trace-prefix-r4-s2-short-remaining-k64.tar.gz](raw/20260911-trace-prefix-r4-s2-short-remaining-k64.tar.gz) |
| `20260911-no-trace-prefix-r4-s2-short-remaining-k64` | `prefix-conflict` | 2 | 4.0 | 64 | `finished` | 300/300 | 99 | 200.819/227.288 s | [raw/20260911-no-trace-prefix-r4-s2-short-remaining-k64.tar.gz](raw/20260911-no-trace-prefix-r4-s2-short-remaining-k64.tar.gz) |

每轮的 CSV 和分析图与 `run_id` 同名。完整请求、服务端记录、调度记录和日志保存在对应原始包中。

客户端对照数据见 [trace-comparison.csv](trace-comparison.csv)。trace 轮有完整调度记录；no-trace 轮没有 `server-trace.json`，调度 CPU、长请求服务端记录和请求回撤等字段缺失属于测量设计结果，不用于补算等待指标。

`config-used.json`、`environment-packages.txt` 和 `server-source-commit.txt` 是本批次共用的配置、环境和源码快照；服务器项目没有独立的项目 Git 工作树，因此本批次不生成 `project-working.diff`。

## 主比较

主比较使用 `prefix-r05`（0.5 req/s）和 `prefix-r1`（1.0 req/s），每个速率使用 seed=1/2/3，每个 seed 比较 `fcfs`、`lpm`、`dfs-weight`、`hrrn` 和 `short-remaining K=0`，每轮 600 请求。30 个运行目录、逐轮 CSV、图表和原始包均以 `20260911-main-prefix-...-n600` 命名；同条件重试记录在 `results/20260914/`，不覆盖本目录的原始失败轮次。

主比较汇总见 [comparison.csv](comparison.csv) 及其图表。`r05/seed=2/fcfs`、`r05/seed=3/lpm`、`r05/seed=3/dfs-weight` 的原始轮各有一个 `ServerDisconnectedError`；后两轮的同条件重试在 `results/20260914/` 中为 600/600，FCFS 的同条件重试仍各有一个不同请求断开。失败请求没有服务端记录，不能填成成功或等待为零。

在 1.0 req/s、K=64、阈值 300000 ms 的 `aged-remaining` 与 `aged-cost` 对照中，候选扫描记录显示前者最大 aged 数为 80、出现 aged 的调用为 862/2070，后者最大为 79、出现 aged 的调用为 861/2069。该阈值高于观察等待尺度，本轮只比较成本排序，不验证 aging 公平性。

日期目录中还保留了早期后台脚本生成的 `20260911-text-fcfs` 和 `20260911-text-short-remaining` 产物；当时 tokenizer 返回的 `BatchEncoding` 未转换为 JSON 数组，两个输入文件为空，CSV 的 `planned=0`，不属于有效文本观察。有效文本观察使用修正后的轨迹，归档在 `results/20260914/`，不使用这两个零请求产物。

## 未计入性能样本的尝试

`runs/20260911-short-remaining-prefix-r4-s2-k0/` 是第一次启动 `K=0` 的尝试，因默认端口 `30000` 短时仍被占用，在服务启动前退出，没有生成 `run.json`，也没有请求样本。该目录保留在服务器上；正式重试使用 `k0-retry1` 和端口 `30001`，不覆盖前一次目录。

## 本批次观察

- 六轮正式运行均为 `failed=0`、`succeeded=300`；候选范围轮的 prefix 轨迹中只有 99 或 106 个成功短请求，尾延迟仍容易受少数样本影响。
- 在 `seed=2` 和 `seed=3` 中，`K=0` 的短请求 TTFT P95/P99 都低于 `K=128`；两组结果方向一致，但当前只有两个 seed，不能据此确定最终最优候选上限。
- trace/no-trace 的客户端短请求 TTFT P95/P99 接近；这只说明本次轨迹和负载下未观察到明显客户端差异，不能用 no-trace 轮分析调度 CPU 或长请求等待。
- `K=0` 表示全部普通候选，不表示无限并发。它的调度 CPU 和评分开销仍需结合 `comparison.csv`、原始 `scheduling.csv` 及后续更大样本比较判断。
- 该批次仍是 300 请求、4 req/s 的严重积压条件，结论只覆盖当前模型、A6000、后端和轨迹设置，不能宣传为大样本稳定 P99。
- 服务器上的 Ollama 外部服务未被终止、重启或修改；实验在其模型自然释放显存后顺序运行。
