# 20260910 实验产物

本目录保存已报告的 30 轮性能汇总，以及成本模型和 320 条正式标定样本。每轮计划发送 300 个请求。日期表示整理／回传批次；真实运行时间以各轮 run.json 为准。

完整结论与下一步见 [实验进度](../../docs/experiment-status.md)，回传格式见 [Linux 手册](../../docs/operations-linux.md)。

## 已收到与尚缺文件

- 已收到：下表逐轮 CSV、calibration 下的模型及正式样本。
- 据服务器报告已保留，但本目录尚未收到：各轮完整 runs 目录、输入与预热副本、客户端与服务端请求记录、调度 trace、server.log、环境快照；标定原始分块 gpu.jsonl 和输入也需回传。
- 请按手册放入 raw/<run_id>.tar.gz，包内保留 runs/<run_id>/。本轮未完成原始记录审查，不把汇总 CSV 当作原始证据齐全。
- 四轮各失败 1 个请求；这些轮次也各有一个长请求缺少服务端记录。原因待 rid 与日志核对。
- K=128 首次 OOM、FlashInfer 启动失败的原始目录也应保留和回传，当前成功重试不覆盖失败。

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

short-remaining K=64 在 prefix 三种子下相对 FCFS 的短请求 P99 降低约 52%–54%，但都不如 HRRN。K=128/0 在 seed=1 有更明显收益，尚缺同等重复。aging 三档接近 FCFS；成本模型留出 MAE 较小，但 Spearman 与仅按 R 排序相同，在线收益尚未建立。不能据此宣称最终最优策略或大样本稳定 P99。
