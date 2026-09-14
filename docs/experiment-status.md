# 实验进度与结论边界

更新日期：2026-09-14。依据服务器环境报告、`results/20260910/` 的历史逐轮 CSV、成本模型、320 条正式标定样本及已回传的原始归档，`results/20260911/` 的候选范围与 trace/no-trace 结果及 30 轮两档速率主比较，以及 `results/20260914/` 的同条件重试和正常文本观察。20260910、20260911 和 20260914 的原始运行目录均已按日期归档；启动失败、OOM、客户端失败和缺失服务端记录仍按原样保留，不能仅凭汇总表把它们解释为成功。

## 已完成的实验

| 实验 | 目的与设置 | 已有结果与限制 |
| --- | --- | --- |
| 环境与测量接入 | A6000、Qwen2.5-7B-Instruct、TP=1、BF16、Triton/PyTorch；固定轨迹、rid 关联、服务端记录导出 | 已完成真实运行；发送偏差 P99 为 2.30–5.69 ms。环境细节见 environment.md |
| mixed-low-reuse 七策略探索 | 300 请求、1 req/s、seed=1；约 80% 短输入，低前缀复用 | FCFS 短请求 P99 5.80 s；HRRN 3.80 s、short-remaining 3.82 s。长请求最大等待约从 3.90 s 增至 4.46–4.72 s，吞吐约 119 output token/s |
| prefix-conflict 七策略探索 | 300 请求、4 req/s、seed=1；16K/12K、2K/1K、16K/1K 输入／目标命中组合 | FCFS 短请求 P99 439.58 s，HRRN 97.47 s，short-input 275.47 s，short-remaining K=64 为 201.42 s；属于严重积压场景 |
| 三种子重复对照 | prefix-conflict，5 策略×3 个 seed，每轮 300 请求 | short-remaining K=64 相比 FCFS 的短请求 P99 降低 51.83%–54.18%，但三个种子都不如 HRRN；不是大样本主比较 |
| 候选范围消融 | short-remaining，prefix，K=32/64/128/0 | seed=1 的 P99 分别为 321.69/201.42/31.91/5.06 s；seed=2 的 K=128/0 为 27.716/5.989 s，seed=3 为 22.946/2.236 s。0 表示全候选；seed=1 的排序累计 CPU 为 2.477/3.734/4.583/4.525 s，20260911 四轮均为 300/300 成功 |
| aging 消融 | aged-remaining，K=64，阈值 100/500/1000 ms | 短请求 P99 都约 439 s，接近 FCFS。大量请求进入超阈值集合是待 trace 确认的解释；阈值不是等待上界 |
| 成本标定 | 16 个 H/R 组合，每组 2 次预热和 20 次正式测量 | 352 个被测请求，其中 320 条正式样本；240 训练、80 留出。额外构建前缀的请求不计入 352；一个请求可能包含多个 GPU 前向 |
| aged-cost 在线对照 | 相同 K=64、阈值 500 ms，把剩余 token 评分换成预测耗时 | P99 438.74 s，对照 aged-remaining 439.30 s，尚无明确在线收益；aging 可能遮蔽了评分差异 |
| 两档速率大样本主比较 | `prefix-conflict`，0.5/1.0 req/s，各 600 请求，3 个 seed，`fcfs/lpm/dfs-weight/hrrn/short-remaining K=0` | 30 轮均完成；27 轮 600/600，3 轮各有 1 个 `ServerDisconnectedError`。服务器 trace 在主比较轮次可用；失败请求和缺失服务端记录没有被填成成功。结果见 `results/20260911/comparison.csv` |
| aging 成本纯排序对照 | `prefix-conflict`，1.0 req/s，600 请求，seed=2，K=64，阈值 300000 ms，`aged-remaining` 与 `aged-cost` | 两轮均 600/600。`aged-remaining` 候选扫描中最大 aged 数为 80、出现 aged 的调用 862/2070；`aged-cost` 最大为 79、出现 aged 的调用 861/2069。该阈值高于观察等待尺度，本轮不验证 aging 公平性；结果见 `results/20260911/` |
| 补充 workload | `hot-prefix`、`long-wait`、`burst-decode`，各 300 请求、1.0 req/s、seed=1，FCFS 与 short-remaining K=0 | 6 轮均 300/300；只用于负载现象观察，不并入 prefix-conflict 主比较表 |
| 正常文本观察 | 同一 `workloads/text-check.jsonl`，FCFS 与 short-remaining K=0 | 两轮均 3/3，回答文本、完成原因和错误字段已人工检查；不计入合成性能主表 |

七策略为 `fcfs/lpm/dfs-weight/hrrn/short-input/short-remaining/aged-remaining`。20260910 的 30 轮按不重复计数为 7+7+10+3+2+1；20260911 新增的是同一 `short-remaining` 策略的候选范围补充重复，不重复计入原有策略探索。三个种子的 seed=1、K=64、aging=500 ms 已包含在探索中，不能重复累计。

## 必须保留的解释

- 短请求按原始输入不超过 2048 token 分组，长请求至少 8192 token。prefix 每轮只有 99–108 个成功短请求；P99 易受最慢几个样本影响，不平均各轮 P99 来冒充总体 P99。
- 当前全部汇总标为 `finished`，但 `first-run`、`short-input-mixed-r1-s1`、`short-remaining-mixed-r1-s1`、`hrrn-prefix-r4-s1` 各有 1 个失败，同时各有 1 个长请求缺少服务端记录。需原始 rid 和错误信息解释，不能把它们称作全部请求成功。
- 原生 LPM/HRRN 在长队列下回退到 FCFS；prefix seed=1 的回退次数分别为 486/171。策略回退与请求因资源原因回到队列是两个指标。
- K 上限限制普通候选的额外评分，不限制所有排队扫描或准入匹配。总调度、排序、评分、准入准备属于嵌套计时，不能相加；准入准备包含输入处理，不是纯缓存查找。
- 两档 600 请求主比较中，`status=finished` 仍需结合 `failed`、`no_client_record` 和 `long_missing_server_record` 判断。`r05/seed=2/fcfs`、`r05/seed=3/lpm`、`r05/seed=3/dfs-weight` 原始轮各有一个失败；LPM 和 DFS-weight 的同条件重试成功，FCFS 的原始轮及三次同条件重试仍各有一个不同请求断开。所有失败目录和原始包均保留。
- 成本标定关闭 overlap，正常性能实验保持默认 overlap。模型是独占 prefill 成本代理，不能直接解释混合批次服务时间。
- 留出 MAE 为 3.165 ms、Spearman 为 0.9683。对上传样本补算发现，仅按 R 排序的留出 Spearman 也为 0.9683，不能用此数证明成本模型的排序优势。同训练集拟合仅含常数与 R 的非负线性模型，留出 MAE 约 76.47 ms；这是已有数据补算，不是新增 GPU 实验。
- FlashInfer 启动失败来自本地 nvcc 12.1 不支持 JIT 参数；K=128 首次 OOM 来自其他 Ollama 进程占用显存。K=128 已在空闲后成功重试，失败日志继续保留，不能算成策略性能样本。

## 已完成的手册任务

| 顺序 | 工作 | 要回答的问题 |
| --- | --- | --- |
| 1 | 回传现有完整运行记录，核对失败和超阈值集合 | 已完成；主比较原始包已回传，aging 对照的实际 aged 数量已记录 |
| 2 | 已完成：在原有 300 请求、4 req/s 的 seed=2/3 上补 K=128/0，并保留独立原始包 | 两个 seed 中 K=0 的短请求 P95/P99 都低于 K=128；仍需更大样本和更多负载确认，不能据此确定最终候选上限 |
| 3 | 已完成：同一 prefix seed=2、short-remaining K=64 的 trace/no-trace 对照 | 客户端短请求 TTFT P95/P99 接近；no-trace 不提供调度 CPU 和长请求服务端等待证据 |
| 4 | 在相同负载下从较低速率探索，选定两个实际负载水平，再扩大样本 | 已完成：选用 0.5 和 1.0 req/s，各 600 请求、3 个 seed |
| 5 | 两种负载、四个原生基线和选定候选、三个种子的大样本对照 | 已完成；跨 seed 保持分行，未平均 P99 冒充总体 P99 |
| 6 | 用高于本轮等待尺度的有限阈值，在相同 K/阈值下比较 aged-cost 与 aged-remaining，并检查 aged 数量 | 已完成；阈值 300000 ms，明确不验证本轮 aging 公平性 |
| 7 | 补 hot-prefix、long-wait、burst-decode 和正常文本观察 | 已完成；补充 workload 不混入主表，文本结果只作功能观察 |

本手册规定的实验任务已执行完毕，但不意味着所有请求零失败，也不意味着已经选定最终最优 K、aging 阈值或跨负载最优策略。FCFS 同条件轮次的瞬时断开和缺失服务端记录是保留的数据缺口；它们不应被隐藏或填成零。执行命令与按日期回传格式见 [Linux 操作手册](operations-linux.md)。
