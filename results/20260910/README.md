# 20260910 实验产物

本目录保存已报告的 30 轮性能汇总，以及成本模型和 320 条正式标定样本。每轮计划发送 300 个请求。日期表示整理／回传批次；真实运行时间以各轮 run.json 为准。

完整结论与下一步见 [实验进度](../../docs/experiment-status.md)，回传格式见 [Linux 手册](../../docs/operations-linux.md)。

## 原始归档

- 已收到：下表逐轮 CSV、`calibration/` 下的模型及正式样本，原始归档体积过大未上传，尚未在本地核验。
- 据服务器说明，36 个归档覆盖本目录 30 条性能汇总、`calibration-a6000-r1` 标定轮，以及服务器保留的重试、失败和启动尝试；早期 `first-run` 与后续运行目录的命名不完全一致，不能仅按文件名机械一一对应。归档包内保留服务器上的 `runs/<run_id>/` 路径，包含实际存在的输入、预热、客户端与服务端记录、调度 trace、日志和环境快照；启动失败目录没有人为补造 `run.json`。
- `dfs-weight-mixed-r1-s1.tar.gz` 与 `dfs-weight-mixed-r1-s1-retry1.tar.gz` 没有 `run.json`，保留其启动失败证据；`short-remaining-prefix-r4-s1-k128.tar.gz` 保留首次 K=128 OOM 目录，成功重试使用独立的 `short-remaining-prefix-r4-s1-k128-retry1` 包。
- `first-run`、`short-input-mixed-r1-s1`、`short-remaining-mixed-r1-s1`、`hrrn-prefix-r4-s1` 各有 1 个失败请求；对应客户端错误、服务端缺失记录和日志均保留，不能把汇总 CSV 解读为所有请求成功。
- 本目录不包含模型权重、`.venv` 或离线 wheel。服务器仍保留未压缩的原始 `runs/` 目录。

## 运行清单

| CSV | 策略 | seed | rate | K | 阈值 ms | 成功/计划 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| [aged-cost-prefix-r4-s1.csv](aged-cost-prefix-r4-s1.csv) | aged-cost | 1 | 4.0 | 64 | 500 | 300/300 |
| [aged-remaining-mixed-r1-s1.csv](aged-remaining-mixed-r1-s1.csv) | aged-remaining | 1 | 1.0 | 64 | 500 | 300/300 |
| [aged-remaining-prefix-r4-s1-tau100.csv](aged-remaining-prefix-r4-s1-tau100.csv) | aged-remaining | 1 | 4.0 | 64 | 100.0 | 300/300 |
| [aged-remaining-prefix-r4-s1-tau1000.csv](aged-remaining-prefix-r4-s1-tau1000.csv) | aged-remaining | 1 | 4.0 | 64 | 1000.0 | 300/300 |
| [aged-remaining-prefix-r4-s1.csv](aged-remaining-prefix-r4-s1.csv) | aged-remaining | 1 | 4.0 | 64 | 500 | 300/300 |
| [dfs-weight-mixed-r1-s1.csv](dfs-weight-mixed-r1-s1.csv) | dfs-weight | 1 | 1.0 | 64 | 500 | 300/300 |
| [dfs-weight-prefix-r4-s1.csv](dfs-weight-prefix-r4-s1.csv) | dfs-weight | 1 | 4.0 | 64 | 500 | 300/300 |
| [dfs-weight-prefix-r4-s2.csv](dfs-weight-prefix-r4-s2.csv) | dfs-weight | 2 | 4.0 | 64 | 500 | 300/300 |
| [dfs-weight-prefix-r4-s3.csv](dfs-weight-prefix-r4-s3.csv) | dfs-weight | 3 | 4.0 | 64 | 500 | 300/300 |
| [fcfs-prefix-r4-s1.csv](fcfs-prefix-r4-s1.csv) | fcfs | 1 | 4.0 | 64 | 500 | 300/300 |
| [fcfs-prefix-r4-s2.csv](fcfs-prefix-r4-s2.csv) | fcfs | 2 | 4.0 | 64 | 500 | 300/300 |
| [fcfs-prefix-r4-s3.csv](fcfs-prefix-r4-s3.csv) | fcfs | 3 | 4.0 | 64 | 500 | 300/300 |
| [first-run.csv](first-run.csv) | fcfs | 1 | 1.0 | 64 | 500 | 299/300 |
| [hrrn-mixed-r1-s1.csv](hrrn-mixed-r1-s1.csv) | hrrn | 1 | 1.0 | 64 | 500 | 300/300 |
| [hrrn-prefix-r4-s1.csv](hrrn-prefix-r4-s1.csv) | hrrn | 1 | 4.0 | 64 | 500 | 299/300 |
| [hrrn-prefix-r4-s2.csv](hrrn-prefix-r4-s2.csv) | hrrn | 2 | 4.0 | 64 | 500 | 300/300 |
| [hrrn-prefix-r4-s3.csv](hrrn-prefix-r4-s3.csv) | hrrn | 3 | 4.0 | 64 | 500 | 300/300 |
| [lpm-mixed-r1-s1.csv](lpm-mixed-r1-s1.csv) | lpm | 1 | 1.0 | 64 | 500 | 300/300 |
| [lpm-prefix-r4-s1.csv](lpm-prefix-r4-s1.csv) | lpm | 1 | 4.0 | 64 | 500 | 300/300 |
| [lpm-prefix-r4-s2.csv](lpm-prefix-r4-s2.csv) | lpm | 2 | 4.0 | 64 | 500 | 300/300 |
| [lpm-prefix-r4-s3.csv](lpm-prefix-r4-s3.csv) | lpm | 3 | 4.0 | 64 | 500 | 300/300 |
| [short-input-mixed-r1-s1.csv](short-input-mixed-r1-s1.csv) | short-input | 1 | 1.0 | 64 | 500 | 299/300 |
| [short-input-prefix-r4-s1.csv](short-input-prefix-r4-s1.csv) | short-input | 1 | 4.0 | 64 | 500 | 300/300 |
| [short-remaining-mixed-r1-s1.csv](short-remaining-mixed-r1-s1.csv) | short-remaining | 1 | 1.0 | 64 | 500 | 299/300 |
| [short-remaining-prefix-r4-s1-k0.csv](short-remaining-prefix-r4-s1-k0.csv) | short-remaining | 1 | 4.0 | 0 | 500 | 300/300 |
| [short-remaining-prefix-r4-s1-k128-retry1.csv](short-remaining-prefix-r4-s1-k128-retry1.csv) | short-remaining | 1 | 4.0 | 128 | 500 | 300/300 |
| [short-remaining-prefix-r4-s1-k32.csv](short-remaining-prefix-r4-s1-k32.csv) | short-remaining | 1 | 4.0 | 32 | 500 | 300/300 |
| [short-remaining-prefix-r4-s1.csv](short-remaining-prefix-r4-s1.csv) | short-remaining | 1 | 4.0 | 64 | 500 | 300/300 |
| [short-remaining-prefix-r4-s2.csv](short-remaining-prefix-r4-s2.csv) | short-remaining | 2 | 4.0 | 64 | 500 | 300/300 |
| [short-remaining-prefix-r4-s3.csv](short-remaining-prefix-r4-s3.csv) | short-remaining | 3 | 4.0 | 64 | 500 | 300/300 |

## 本批次结论

short-remaining K=64 在 prefix 三种子下相对 FCFS 的短请求 P99 降低约 52%–54%，但都不如 HRRN。K=128/0 在 seed=1 有更明显收益；seed=2/3 的同条件补充见 [results/20260911](../20260911/)。aging 三档接近 FCFS；成本模型留出 MAE 较小，但 Spearman 与仅按 R 排序相同，在线收益尚未建立。不能据此宣称最终最优策略或大样本稳定 P99。
