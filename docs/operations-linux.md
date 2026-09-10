# Linux 操作手册

更新日期：2026-09-10。当前环境、四种候选和测量工具已在 A6000 实际运行。已有 30 轮每轮 300 请求的性能汇总与成本标定；尚未完成大样本、多负载水平主比较。先阅读 [实验进度](experiment-status.md) 与 [服务器环境](environment.md)，已有服务器从第 1 节恢复，不重装环境或重复应用补丁。

## 1. 服务器：恢复现有环境

当前服务器工作区是 `/mnt_d/huangxiaoyuan/sglang-scheduler-lab-v1.0`，不是此前示例的用户主目录。通过登录设备 SSH 进入服务器后：

```bash
cd /mnt_d/huangxiaoyuan/sglang-scheduler-lab-v1.0
source .venv/bin/activate
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
DAY=$(TZ=Asia/Shanghai date +%Y%m%d)
OUT="results/$DAY"
mkdir -p "$OUT" workloads
nvidia-smi
```

`DAY` 使用当天北京时间，格式统一为 `YYYYMMDD`，例如 `20260910`；此变量在本次回传批次开始时设定，跨午夜的同一批次继续使用该值。日期表示本次整理／回传日期，真实运行时间仍以每轮记录为准。不要改写已归档的历史日期目录来伪装成当天实验。

当前 Python 为 3.12.8，PyTorch 为 2.13.0+cu129；模型路径已经写入 `configs/a6000.json`，使用 TP=1、BF16、Triton attention 和 PyTorch sampling。驱动 580.173.02，`nvidia-smi` 显示 CUDA 能力 13.0，PyTorch 构建为 12.9，本地 nvcc 为 12.1.105。不要把它们统称为“已安装 CUDA 12.9 toolkit”。

模型、源码和原有结果无需重新下载。保留当前后端：此前 FlashInfer 的 JIT 使用了 nvcc 12.1 不支持的参数，切回 FlashInfer 会引入新环境变量。K=128 的一次 OOM 则来自其他进程占用显存；卡被占用时等待空闲，不结束不属于本实验的进程。

## 2. 登录设备：新建或迁移环境时才使用

登录设备负责联网下载和传输，服务器无外网。实际 SSH 用户与地址未在手册中给定，设置为自己的值：

```bash
SERVER=user@your-server
REMOTE=/mnt_d/huangxiaoyuan/sglang-scheduler-lab-v1.0
ssh "$SERVER" 'uname -m; python3 --version; ldd --version | head -n 1; nvidia-smi; nvcc --version'
```

新环境的 wheel 应匹配 Linux x86_64、Python 3.12 和目标 glibc。已有环境通过复用服务器原有 cu129 环境并补包建立；`environment.md` 是已报告版本清单，不是经过全新安装验证的依赖锁文件。部分元数据版本差异仍存在，不应承诺下面的重新安装已经完整验证。

首次获取固定源码，在登录设备项目根目录执行：

```bash
mkdir -p upstream offline/wheels
BASE=$(cat patches/upstream-base.txt)
curl -L "https://codeload.github.com/sgl-project/sglang/tar.gz/$BASE" -o offline/sglang-source.tar.gz
tar -xzf offline/sglang-source.tar.gz -C upstream
mv "upstream/sglang-$BASE" upstream/sglang
git -C upstream/sglang init
git -C upstream/sglang add .
git -C upstream/sglang -c user.name=Lab -c user.email=lab@localhost commit -m "记录上游源码基线"
git -C upstream/sglang apply "$PWD/patches/scheduler.patch"
```

只对新建、未应用补丁的工作副本执行上述命令。服务器已完成这一过程，上游基线本地提交为 `b1f4b44`，项目补丁提交为 `c3f7c49`；这些本地提交号与上游固定提交含义不同。

迁移时优先从现有服务器环境导出确切版本，再在兼容的联网 Linux 准备 wheel：

```bash
# 服务器，已经激活本项目 .venv
python -m pip list --format=freeze --exclude-editable > "$OUT/runtime.txt"
python -m pip freeze > "$OUT/environment-packages.txt"
```

登录设备收到该 `runtime.txt` 后，在 Python 3.12 准备环境中下载：

```bash
python -m pip download --pre --no-deps --only-binary=:all: \
  --extra-index-url https://download.pytorch.org/whl/cu129 \
  --extra-index-url https://docs.sglang.ai/whl/cu129/ \
  -r offline/runtime.txt -d offline/wheels
python -m pip download setuptools setuptools-rust setuptools-scm wheel -d offline/wheels
```

先把服务器导出的文件复制为登录设备的 `offline/runtime.txt`。缺少指定 wheel 时在联网设备处理对应包，必要时使用兼容 Linux 构建；不能在离线服务器临时联网解析。固定上游默认包含 CUDA 13 依赖，不能用普通 `pip install sglang` 替代 cu129 准备。[固定版本安装说明](https://github.com/sgl-project/sglang/blob/0027af2eace5ccc2116c8c993ce71aebf1535264/docs/docs/get-started/install.mdx)

将项目、`offline/` 和模型分别通过 `scp` 或 `rsync` 传给新服务器。当前模型已从服务器既有 Qwen2.5-7B-Instruct 目录复制，无需重复下载；全新设备可在登录设备执行 `hf download Qwen/Qwen2.5-7B-Instruct --local-dir models/Qwen2.5-7B-Instruct`，再完整传输模型、配置和 tokenizer。

新服务器的源码解包与应用补丁按前面的相同步骤执行；创建环境后离线安装：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --no-index --find-links offline/wheels -r offline/runtime.txt
python -m pip install --no-index --find-links offline/wheels setuptools setuptools-rust setuptools-scm wheel
SGLANG_BUILD_RUST_EXTS=none python -m pip install --no-index --no-deps --no-build-isolation -e upstream/sglang/python
```

Rust 扩展跳过选项由该基线支持，本项目使用普通文本 HTTP 路径。新环境需要真实运行后才能称为可用；已有服务器不执行这套重建流程。

## 3. 服务器：每轮运行与分析

使用已有脚本，不改变数据格式。以新建的一轮为例：

```bash
RUN="${DAY}-mixed-r025-s1-fcfs"
python experiments/generate_workload.py --workload mixed-low-reuse \
  --count 300 --rate 0.25 --seed 1 --output workloads/mixed-r025-s1.jsonl
python experiments/run_case.py --policy fcfs \
  --input workloads/mixed-r025-s1.jsonl --output "runs/$RUN" --request-timeout 1800
python experiments/analyze.py "runs/$RUN" --output "$OUT/$RUN.csv" --plot
```

0.25 req/s 和 1800 s 是下一轮探索的示例值，不是已测容量或最终参数。`run_case` 的默认请求超时仍是 600 s；积压较大时应根据已有完成时间选择更长的超时。不要直接把当前 300 请求扩成 3000、仍以 4 req/s 注入却不考虑排空时间。

脚本默认使用 `configs/a6000.json`，`--model /实际路径` 可覆盖模型位置。每个运行目录必须是新的；重试加 `retry1` 等标识，保留失败目录。

运行过程为：启动 localhost 服务、非计时预热、清缓存、轨迹前缀预热、开放到达回放、等待客户端结束、查询 `/server_info` 导出服务端内存记录、结束本轮子进程。客户端在同一台服务器运行，登录设备只负责 SSH 操作。GPU 案例在同一张卡上顺序执行。

`run_case` 不会自动执行分析和回传。工具不会自动按日期改写默认输出位置，因此分析和标定命令始终显式指定 `--output "$OUT/..."`，不要省略后写到 results 根目录。分析需使用完整运行目录，不能拿两行汇总 CSV 代替请求明细重新计算 P99。`--plot` 生成总览图以及等待／吞吐和队列／CPU 关系图。

## 4. 优先补齐已有实验的证据

先按第 8 节回传现有运行目录，包含四个失败请求所在轮次、K=128 启动 OOM 目录、成功重试和标定目录。核对 `client.jsonl` 的错误、`rid` 与服务端记录，查看 `scheduling.csv` 的 `aged`、候选数和队列长度。

优先补 K=128、全候选在 seed=2/3 的重复；每个 seed 的输入和预热文件必须与相应已有对照相同。若服务器已保留轨迹，直接使用；下面仅演示新生成的文件名，不用新文件替换后再声称复用了旧输入：

```bash
for SEED in 2 3; do
  INPUT="workloads/prefix-r4-s${SEED}.jsonl"
  python experiments/generate_workload.py --workload prefix-conflict \
    --count 300 --rate 4 --seed "$SEED" --output "$INPUT"
  for K in 128 0; do
    RUN="${DAY}-short-remaining-prefix-r4-s${SEED}-k${K}"
    python experiments/run_case.py --policy short-remaining --candidates "$K" \
      --input "$INPUT" --output "runs/$RUN" --request-timeout 1800
    python experiments/analyze.py "runs/$RUN" --output "$OUT/$RUN.csv"
  done
done
```

如果输入生成代码、环境或运行时段发生变化，重新运行对应 HRRN 和 FCFS，形成同条件比较组。K=0 表示全部普通候选；它不等于无限并发。旧 K=64 已有三种子结果，不必无目的重跑全部矩阵。

记录开销对照：同一输入、同一策略分别运行默认 trace 和 `--no-trace`，使用不同目录，比较客户端 TTFT、吞吐与失败数。关闭 trace 后等待／调度 CPU 指标缺失是预期，不填成 0。此对照尚未执行。

## 5. 后续负载、样本与 aging

五个生成器名称为 `mixed-low-reuse`、`prefix-conflict`、`hot-prefix`、`long-wait`、`burst-decode`。当前只有前两个有上传的性能汇总。后面三个分别检验热点复用、持续短流中的长请求等待、突发与长 decode 干扰。

先在相同负载上探索较低速率，选定有意义的两个负载水平，再决定大样本主比较的最终候选和 K。当前 prefix 的 4 req/s 是严重积压条件，不能当作线上正常工作点。扩大样本时关注成功短请求数；前缀负载每 300 个请求只有约 100 个短请求，整体 3000 条也不等于 3000 条短样本。

大样本比较保留 `fcfs/lpm/dfs-weight/hrrn` 四个原生基线、一个选定候选和三个种子。相同 seed 内复用输入、预热与配置；跨 seed 分行报告，不平均 P99 冒充总体 P99。

aging=100/500/1000 ms 已完成单种子探索，三档均接近 FCFS。下一轮应先看实际排队和 `aged` 比例，再选择更有区分度的阈值，不把 500 ms 视为等待承诺。如果为比较纯成本排序而使用高于观察等待尺度的有限阈值，必须说明这轮没有验证 aging 的公平性，并检查是否仍有请求越过阈值。

## 6. 使用已有成本模型及必要的重标定

当前模型在 `results/20260910/calibration/a6000-cost-r1.json`。先把该日期目录同步到服务器，不要根据运行当日日期猜测模型路径：

```bash
COST=results/20260910/calibration/a6000-cost-r1.json
RUN="${DAY}-aged-cost-prefix-r4-s2"
python experiments/run_case.py --policy aged-cost --cost-model "$COST" \
  --input workloads/prefix-r4-s2.jsonl --output "runs/$RUN" --request-timeout 1800
python experiments/analyze.py "runs/$RUN" --output "$OUT/$RUN.csv"
```

默认 K=64、aging=500 ms；它延续已有对照，但不能独立证明成本评分有价值，因为 aging 可能主导顺序。比较成本评分时让 `aged-cost` 与 `aged-remaining` 使用相同 K、相同阈值，并保存实际超阈值数量。

模型、backend 或 chunk 配置变化时重新标定：

```bash
RUN="${DAY}-calibration-a6000"
python experiments/run_case.py --calibrate --samples 20 --output "runs/$RUN"
python experiments/calibrate.py --run "runs/$RUN" --output "$OUT/calibration/a6000-cost.json"
```

16 组×22 次=352 个被测请求，包含 32 次预热，正式 320 样本；额外前缀预热不计在其中。记录实际 H/R 和全部 extend 块的 CUDA event 耗时。标定独占且关闭 overlap，普通性能运行保持默认 overlap。

现有留出 MAE=3.165 ms、Spearman=0.9683；仅按 R 排序也获得同样的留出 Spearman。该留出集不能证明成本模型比 R 更会排序。后续需要包含顺序反转的组合，例如较小 R 配很长 H，并保留未参与拟合的组合；新增标定矩阵需要修改采集脚本，当前脚本没有任意组合 CLI 参数。

## 7. 指标与正常文本观察

详细口径见 [实验进度](experiment-status.md) 和 `experiments/analyze.py`。TTFT 是客户端发出请求到首 token；长等待是服务端首次入队到首次准入。排序、匹配和总 prefill 调度计时嵌套，不能相加。`scoring` 是评分匹配，`admission` 包含输入准备。`cpu_ms` 是线程 CPU 时间，`wall_ms` 是调用经过时间。

`status=finished` 不代表零失败；同时检查 failed、缺失记录和未准入请求。缺失服务端记录不是等待为零。缓存率使用成功集合实际 cached tokens；排序时命中不等于最终复用量。原生策略回退和请求回退分别报告。

正常文本观察尚无上传结果，可在服务器生成独立轨迹：

```bash
python - <<'PY'
import json
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained('models/Qwen2.5-7B-Instruct', local_files_only=True)
questions = ['解释 prefill 与 decode 的区别。', '计算 17 乘以 23，并给出过程。', '用三句话说明前缀缓存的作用。']
with open('workloads/text-check.jsonl', 'w', encoding='utf-8') as f:
    for i, question in enumerate(questions):
        ids = tokenizer.apply_chat_template([{'role': 'user', 'content': question}], add_generation_prompt=True)
        f.write(json.dumps(dict(rid=f'text-{i}', arrival_s=i, input_ids=ids,
                                max_new_tokens=256, ignore_eos=False), ensure_ascii=False) + '\n')
PY
python experiments/run_case.py --policy fcfs --input workloads/text-check.jsonl --output "runs/${DAY}-text-fcfs"
python experiments/run_case.py --policy short-remaining --input workloads/text-check.jsonl --output "runs/${DAY}-text-short-remaining"
```

人工阅读 `client.jsonl` 的 text、完成原因与错误。它不混入合成性能主表，不把逐字相同设成性能实验条件。

## 8. 结果回传格式：统一进入 results/当天日期/

**服务器整理、Linux 登录设备接收、Windows 接收与 GitHub 上传，都保留 `results/YYYYMMDD/` 层级。** 当前已存在 `results/20260909/` 与 `results/20260910/`；历史结果保持原日期，后续产物放入实际回传当天的新目录。运行原始数据仍先生成在服务器 `runs/<run_id>/`，不需要改脚本。

建议每个日期目录包含：

```text
results/YYYYMMDD/
  README.md                         # 本批次运行清单、问题、结论与缺失文件
  <run_id>.csv                      # 每轮汇总，一行一轮
  comparison.csv                    # 可选，同条件比较组
  *.png                             # 分析图，标明对应运行
  calibration/
    a6000-cost*.json                 # 有本次标定时提供
    a6000-cost*.samples.jsonl
  config-used.json                   # 本批次配置副本；每轮 run.json 为实际参数依据
  environment-packages.txt
  project-working.diff
  upstream-working.diff
  server-source-commit.txt
  raw/
    <run_id>.tar.gz                  # 一轮一个包，包含 runs/<run_id>/ 完整目录
```

已有 `20260910/` 的 CSV、标定模型和样本保留现有文件名，不要求为了新格式改名。历史目录里的面试提纲可继续保留。

原始包应包含实际生成的文件：`run.json`、`input.jsonl`、`input.meta.json`（若有）、`warmup.jsonl`（若有）、`client.jsonl`、`server-requests.jsonl`、`server-trace.json`、`scheduling.csv`、`server-info.json`、`server.log`、环境快照和 `summary.json`。标定轮另带 `calibration-input.jsonl`、`calibration-client.jsonl` 与 `gpu.jsonl`。失败轮按现有内容打包，并在日期 README 说明缺失；不造空文件补齐。

只传 CSV 无法定位失败请求、重算分位数或检查 aging 分支；所以原始包与对应输入一并回传。这里是文件组织约定，不增加哈希、门禁或新验证框架。

服务器示例，每完成一轮整理一次：

```bash
mkdir -p "$OUT/raw"
python experiments/analyze.py "runs/$RUN" --output "$OUT/$RUN.csv"
tar -czf "$OUT/raw/$RUN.tar.gz" "runs/$RUN"
cp configs/a6000.json "$OUT/config-used.json"
python -m pip freeze > "$OUT/environment-packages.txt"
git -C upstream/sglang log -1 --oneline > "$OUT/server-source-commit.txt"
git -C upstream/sglang diff > "$OUT/upstream-working.diff"
git diff > "$OUT/project-working.diff"
```

`RUN` 使用本节之前实际运行的目录名。启动失败轮没有请求文件或标定轮没有普通 input.jsonl 时，跳过通用 analyze 命令，直接打包该目录。项目没有 Git 时略过最后一行，并在日期 README 说明；Git diff 不包含未跟踪文件，如有新实验脚本，另将实际文件副本放进日期目录的 `code/`。

为日期目录写一份简短 README：列出 run_id、工作负载、种子、rate、K、阈值、完成／失败状态、用途、原始包名和已知缺失。不要把本轮失败覆盖成成功重试。一天多批回传沿用同一日期目录，但每个运行使用不同 run_id；配置发生变化时另存命名副本，实际值仍以各轮 run.json 为准。

## 9. 登录设备接收与发布

在登录设备的项目根目录执行；`DAY` 填服务器本批次选定的日期，不重新用接收设备日期猜测：

```bash
SERVER=user@your-server
REMOTE=/mnt_d/huangxiaoyuan/sglang-scheduler-lab-v1.0
DAY=20260910
mkdir -p "results/$DAY"
rsync -a --info=progress2 "$SERVER:$REMOTE/results/$DAY/" "results/$DAY/"
```

没有 rsync 时：

```bash
scp -r "$SERVER:$REMOTE/results/$DAY/." "results/$DAY/"
```

已有完整包可以解压到另一个分析目录，再把原始运行目录传给 analyze；不要把多轮 client.jsonl 混在一起覆盖。复制到 Windows 时同样保留 `results/$DAY/`。

GitHub 网页端提交时目标目录也是 `results/$DAY/`。如果原始包超过网页上传限制，在本地日期目录保留完整包，在该日期 README 说明尚未上传哪些文件以及原始副本保存位置；上传汇总表不等于原始证据已收齐。模型权重和离线 wheel 不属于实验结果回传包。

服务器与登录设备不承担 GitHub push；本地 Windows 已能推送，但发布仍不是启动下一轮实验的前提。
