# Linux 操作手册

本手册用于 Linux 登录设备和单卡 A6000 实验服务器。四种候选策略及实验工具已实现；本地验证覆盖排序、流式回放和统计逻辑，**没有远程 GPU 性能结果，也没有已验证的 A6000 安装包组合**。

## 1. 文件与执行位置

| 文件／目录 | 用途 |
| --- | --- |
| `patches/upstream-base.txt` | 上游源码固定提交 |
| `patches/scheduler.patch` | 完整源码补丁，包含排序与记录模块 |
| `configs/a6000.json` | 单卡起始配置 |
| `experiments/generate_workload.py` | 生成五类固定 token 轨迹 |
| `experiments/run_case.py` | 启动服务、预热、回放、导出和结束本轮进程 |
| `experiments/calibrate.py` | 对真实 GPU 样本拟合成本模型 |
| `experiments/analyze.py` | 逐轮指标、比较表和图 |
| `runs/` | 每轮原始产物，通常压缩回传 |

以下命令均从项目根目录运行，除非明确写出 `cd`。登录设备与服务器都把项目放到 `$HOME/sglang-scheduler-lab`；模型目录示例为 `/data/models/Qwen2.5-7B-Instruct`。把 `SERVER=user@your-server` 改成实际 SSH 地址。代码不要求 GitHub 推送。

## 2. 登录设备：确认安装包目标

先通过 SSH 读取实际系统与 Python 信息，它们决定离线 wheel 能否使用。这是安装所需信息，不增加单独的审批流程。

```bash
SERVER=user@your-server
ssh "$SERVER" 'uname -m; cat /etc/os-release; python3 --version; ldd --version | head -n 1; nvidia-smi; nvcc --version'
```

已知驱动为 `580.173.02`、CUDA 为 `12.9`。`nvidia-smi` 中的 CUDA 数字表示驱动支持能力，`nvcc` 表示本地 toolkit；分别保留。联网准备环境与服务器使用相同 CPU 架构、Python 小版本和兼容的 glibc；本手册以 Python 3.11 为例。登录设备不需要 GPU 来下载 wheel，但不能替服务器验证 CUDA kernel。

把 Windows 项目文件复制到登录设备后，在登录设备运行：

```bash
cd "$HOME/sglang-scheduler-lab"
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

只应用一次补丁。再次运行 `git apply` 报“already exists”或上下文不符时先看 `git diff`，不要反复叠加补丁。上游源码压缩包的实际版本由 `upstream-base.txt` 指定；本地初始化产生的 Git 提交号不等于上游提交号。

## 3. 登录设备：准备 Python 依赖和模型

固定上游的安装文档默认采用 CUDA 13；CUDA 12.9 需要其专门索引，不能把 Windows wheel 或默认 CUDA 13 环境直接搬到服务器。下面采用其 CUDA 12 安装路径，并在联网设备完成解析，再导出确切版本。

```bash
python3.11 -m venv .prepare-venv
source .prepare-venv/bin/activate
python -m pip install --upgrade pip uv setuptools setuptools-rust setuptools-scm wheel
export SGLANG_BUILD_RUST_EXTS=none
uv pip install --prerelease=allow -e upstream/sglang/python
uv pip install --force-reinstall torch==2.13.0 torchaudio==2.11.0 torchvision --index-url https://download.pytorch.org/whl/cu129
uv pip install --force-reinstall sglang-kernel --index-url https://docs.sglang.ai/whl/cu129/
uv pip install --force-reinstall sgl-deep-gemm --index-url https://docs.sglang.ai/whl/cu129/ --no-deps
python -m pip install -r experiments/requirements.txt
python -m pip list --format=freeze --exclude-editable > offline/runtime.txt
python -m pip freeze > offline/preparation-environment.txt
python -m pip download --pre --no-deps --only-binary=:all: \
  --extra-index-url https://download.pytorch.org/whl/cu129 \
  --extra-index-url https://docs.sglang.ai/whl/cu129/ \
  -r offline/runtime.txt -d offline/wheels
```

`SGLANG_BUILD_RUST_EXTS=none` 是此基线 `python/setup.py` 支持的选项，跳过本项目纯文本 HTTP 路径不需要的 Rust 扩展。离线安装也使用同一选项。下载发生在 Linux，wheel 应对应服务器 Python。这里不改上游依赖声明；CUDA 12 包替换来自上游安装指引。[固定版本安装文档](https://github.com/sgl-project/sglang/blob/0027af2eace5ccc2116c8c993ce71aebf1535264/docs/docs/get-started/install.mdx)、[构建选项](https://github.com/sgl-project/sglang/blob/0027af2eace5ccc2116c8c993ce71aebf1535264/python/setup.py)。

这组上游命令尚未在实验服务器验证。若固定版本在索引中不可用或依赖解析失败，保留报错和已经解析出的版本，不把它描述成“离线已就绪”。先在联网设备解决包组合，再重新导出 `runtime.txt`；若更换上游版本，需要重新检查补丁和原生 HRRN。某个包只有源码分发时，可在兼容的联网 Linux 上用 `pip wheel --no-deps 包名==版本 -w offline/wheels` 构建它，保存实际构建工具版本。服务器不承担临时联网补包。

如果服务器本来已有 Docker 和 NVIDIA Container Toolkit，也可在登录设备准备上游 `-cu129` 镜像并 `docker save`，服务器 `docker load` 后挂载项目和模型运行。本手册默认使用 venv，不把 Docker 权限或安装 Docker 作为前提；镜像环境同样需要记录实际包版本并安装补丁源码。

下载模型：

```bash
mkdir -p models
hf download Qwen/Qwen2.5-7B-Instruct --local-dir models/Qwen2.5-7B-Instruct
```

保留模型配置、tokenizer 和权重的完整目录。合成轨迹使用 `[1000, 29999]` 范围的 token ID，按默认 Qwen tokenizer 设计；换模型时应同步检查有效 ID 范围和显存配置。合成 token 仅用于性能，不能用于回答质量结论。

## 4. 登录设备：传输到服务器

```bash
tar --exclude=.git --exclude=.venv --exclude=.prepare-venv \
    --exclude=upstream --exclude=models --exclude=runs \
    -czf /tmp/sglang-scheduler-lab.tar.gz .
scp /tmp/sglang-scheduler-lab.tar.gz "$SERVER:/tmp/"
ssh "$SERVER" 'mkdir -p "$HOME/sglang-scheduler-lab"; tar -xzf /tmp/sglang-scheduler-lab.tar.gz -C "$HOME/sglang-scheduler-lab"'
rsync -a --info=progress2 models/Qwen2.5-7B-Instruct/ "$SERVER:/data/models/Qwen2.5-7B-Instruct/"
```

先确保 `/data/models` 是可写目录；没有权限就用用户目录，并在运行时传 `--model`。没有 `rsync` 时改用 `scp -r`。依赖和模型较大，可以分开传输；不需要发布 GitHub 后才能实验。

## 5. 服务器：离线安装

```bash
cd "$HOME/sglang-scheduler-lab"
mkdir -p upstream
BASE=$(cat patches/upstream-base.txt)
tar -xzf offline/sglang-source.tar.gz -C upstream
mv "upstream/sglang-$BASE" upstream/sglang
git -C upstream/sglang init
git -C upstream/sglang add .
git -C upstream/sglang -c user.name=Lab -c user.email=lab@localhost commit -m "记录上游源码基线"
git -C upstream/sglang apply "$PWD/patches/scheduler.patch"
git -C upstream/sglang add python/sglang/srt
git -C upstream/sglang -c user.name=Lab -c user.email=lab@localhost commit -m "实现剩余 prefill 调度与实验记录"

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --no-index --find-links offline/wheels -r offline/runtime.txt
SGLANG_BUILD_RUST_EXTS=none python -m pip install --no-index --no-deps --no-build-isolation -e upstream/sglang/python
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
python -m sglang.launch_server --help | grep schedule-
```

wheel 中包括构建依赖；`--no-build-isolation --no-deps` 避免源码 editable 安装重建一个联网依赖环境。实际 CUDA 库是否可加载、FlashInfer 是否需要 JIT 产物，只能在服务器真实运行时确认。如果日志显示需要下载 kernel，回到联网设备准备对应版本的缓存／包再传入；如果需要本地编译，使用服务器已有的 CUDA 12.9 toolkit 和编译器。不要把 SSH 可连通当作 GPU 验证完成。

源码接入的 CPU 检查可执行：

```bash
python -m unittest discover -s tests -v
```

这些检查没有模型推理，不替代下节的真实实验。

## 6. 服务器：先运行一轮真实基线

```bash
mkdir -p workloads
python experiments/generate_workload.py --workload mixed-low-reuse \
  --count 300 --rate 1 --seed 1 --output workloads/mixed-r1-s1.jsonl
python experiments/run_case.py --policy fcfs \
  --input workloads/mixed-r1-s1.jsonl --output runs/fcfs-mixed-r1-s1
python experiments/analyze.py runs/fcfs-mixed-r1-s1 --output results/first-run.csv
```

这是首轮实际实验，不是额外门禁；300 条仅供观察可运行性、容量与大致延迟，不能支持稳健的短请求 P99。`--model /实际模型路径` 可覆盖配置路径。`run_case` 会启动自己的子进程，只绑定 localhost；客户端也在服务器运行，登录设备只操作 SSH。可以在已有 `tmux` 会话中运行以保留终端。

正常过程：启动服务 → 非计时预热 → 清空 radix cache → 按轨迹预热前缀 → 开放到达回放 → 等待所有客户端请求结束 → 查询 `/server_info` 导出记录 → 结束本轮子进程。`/server_info` 的导出钩子在 scheduler 进程中执行，不依赖 `atexit`；测量期间不逐请求写服务端日志文件。

`server-trace.json` 记录 scheduler 导出快照时刻，未准入等待下界使用该时刻计算；客户端 `run.json` 记录测量窗口。两个文件都应随原始结果回传。

如果发生 OOM，先根据 `server.log` 和 `server-info.json` 里的容量判断，再统一调整 `configs/a6000.json`。若 FlashInfer 不兼容，可把 `attention_backend` 设为 `triton`，同时增加 `sampling_backend: "pytorch"`；所有对照和成本标定使用同一最终 backend。不要只给表现较差的策略降低并发。

`--request-timeout` 默认 600 秒，`--startup-timeout` 默认 1800 秒。超时会留下失败记录；若实验确实需要更长排空时间，应增大请求超时后重新运行。强制终止、导出失败或缺失客户端记录会保留在产物中，不能作为正常完成的一轮隐藏掉。

## 7. 服务器：策略比较和消融

先从低速基线逐步提高速率，选出有排队但还能排空的两个负载水平。下面的 `RATE=4` 只是命令示例，不是 A6000 的已测容量。

```bash
RATE=4
python experiments/generate_workload.py --workload prefix-conflict \
  --count 3000 --rate "$RATE" --seed 1 --output workloads/conflict-r4-s1.jsonl
for POLICY in fcfs lpm dfs-weight hrrn short-input short-remaining aged-remaining; do
  python experiments/run_case.py --policy "$POLICY" \
    --input workloads/conflict-r4-s1.jsonl --output "runs/$POLICY-conflict-r4-s1"
done
```

五种 workload 名称是 `mixed-low-reuse`、`prefix-conflict`、`hot-prefix`、`long-wait`、`burst-decode`。生成器同时写出 `.warmup.jsonl` 与 `.meta.json`；同一比较组重复使用同一组文件。`prefix-conflict` 包含同为 16K 输入却分别目标命中 12K／1K 的请求，实际命中可能受缓存驱逐和 page 对齐影响。热门负载大多属于中间长度群体，短请求 P99 缺失时不能补成 0。

`burst-decode` 每组 160 个同时计划到达，跨越原生 LPM／HRRN 的 128 队列阈值；实际服务端队列是否越过阈值看记录，不能从客户端批量数直接推定。到达任务不等待前一请求完成，也不设置连接池并发上限。若 `send_lag_p99_ms` 很大，先判断客户端是否成为瓶颈。

以相同文件运行 `--candidates 32`、`64`、`128`、`0`，以及 `--aging-ms 100`、`500`、`1000`。使用不同输出目录；`0` 表示全部普通候选。所有超阈值请求都排到候选之前，不受 K 限制，但不能保证在阈值内准入。保留三次独立 seed，主比较选四个原生基线和一个最终候选；不必跑所有参数的笛卡尔积。

正式对照默认全部启用记录。选一个代表案例增加 `--no-trace`，量化记录开关对客户端指标的影响；关闭记录时服务端等待和调度耗时缺失属于预期，不应填零。

## 8. 服务器：真实成本标定与 aged-cost

```bash
python experiments/run_case.py --calibrate --samples 20 --output runs/calibration-a6000
python experiments/calibrate.py --run runs/calibration-a6000 \
  --output results/calibration/a6000-cost.json
python experiments/run_case.py --policy aged-cost --cost-model results/calibration/a6000-cost.json \
  --input workloads/conflict-r4-s1.jsonl --output runs/aged-cost-conflict-r4-s1
```

标定包含 16 个 H/R 组合，各两次不计入拟合的预热、20 次正式样本。每次测量之前清缓存并重新构建随机前缀；被测请求输出 1 token。GPU event 在 `ModelRunner.forward` 所在的当前 CUDA stream 记录，计时截止 event 同步；累计同一个请求的全部 extend 块，排除独立预热请求和 decode。会记录模型前向相关 GPU 工作，不含客户端排队，也不是单独 attention kernel 时间。

为让计时归属明确，标定固定关闭 overlap；正式性能实验保持默认 overlap。因此拟合是独占前向成本代理，需要靠 `aged-cost` 与 `aged-remaining` 的实际比较确认在线排序收益，不能声称已经建模混合批次运行时间。模型、backend、chunk size 变更后重新标定。

`calibration-input.jsonl` 保存输入和按组合划分的 train/holdout；`gpu.jsonl` 保存分块实际 H、R 和 GPU 毫秒。拟合用非负最小二乘，保存系数、单位、留出误差、排序相关性及配置。不提供虚构的预置系数。留出相关性低或性能没有改善，也属于有效项目结论。

## 9. 分析指标和读数边界

```bash
python experiments/analyze.py \
  runs/fcfs-conflict-r4-s1 runs/lpm-conflict-r4-s1 \
  runs/dfs-weight-conflict-r4-s1 runs/hrrn-conflict-r4-s1 \
  runs/aged-remaining-conflict-r4-s1 \
  --output results/conflict-r4-s1.csv --plot
```

每轮生成 `summary.json`，比较表一行一轮，图横坐标保留运行目录名。不要把不同速率或种子的 P99 平均后称为总体 P99。展示 P99 时一起展示 `short_successes`，失败与缺失数量始终保留。

| 字段 | 解释 |
| --- | --- |
| `short_ttft_p95_ms` / `short_ttft_p99_ms` | 成功且原始输入不超过 2048 token 的客户端 TTFT |
| `long_wait_max_ms` | 已首次准入、输入至少 8192 token 的最大首次排队等待 |
| `long_not_admitted` / `long_wait_lower_bound_max_ms` | 已入队但未准入的数量与快照时等待下界 |
| `long_missing_server_record` | 没有服务端排队记录的长请求，不能假设其已准入 |
| `requests_per_s` / `output_tokens_per_s` | 成功请求及其输出 token，除以首个实际发送到最后客户端结束的时间窗口 |
| `cache_hit_rate` | 成功集合实际 `cached_tokens` 总和除以输入总 token；缺字段则留空 |
| `policy_fallback_calls` | 配置与有效排序策略不同的调用次数 |
| `request_retractions` | 请求回退重新入队次数 |
| `priority_*` | `calc_priority` 整体排序调用；包含评分匹配 |
| `prefill_total_*` | `_get_new_batch_prefill_raw` 总调用；包含排序与准入准备 |
| `scoring_*` | `match_prefix_for_req` 经过时间／线程 CPU 时间与次数 |
| `admission_*` | `init_next_round_input` 准入准备调用，包含匹配和输入准备 |

这些计时是嵌套的，**不能把 prefill_total、priority、scoring、admission 相加**。`admission` 并非纯 radix 查找耗时。`scheduling.csv` 保留调用队列长度、候选数、超阈值数量和计时；只在存在等待请求或分块续算时记录 prefill 总调用，避免记录空闲自旋。`cpu_ms` 为当前线程 CPU 时间，`wall_ms` 为调用经过时间。

新策略额外评分匹配不超过 K；FCFS 也可能匹配全队列。`waiting_queue_prefix_matched()` 对新策略返回 False，原生 load 查询走既有估算分支，该估算不用于这里的命中率。首次准入不是 GPU 真正开始时刻。

另做少量正常文本、`ignore_eos=false` 的回答观察。可用模型 tokenizer 把人工问题编码为轨迹的 `input_ids`，设置 `ignore_eos: false`，再用 `replay.py` 或 `run_case.py` 回放；结果 `text` 留在 `client.jsonl`。不把随机 token 的回答、逐字完全相同或速度提升当成质量结论。

例如在服务器生成三个人工问题，并分别用原生策略与最终候选运行：

```bash
python - <<'PY'
import json
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained('/data/models/Qwen2.5-7B-Instruct', local_files_only=True)
questions = ['解释 prefill 与 decode 的区别。', '计算 17 乘以 23，并给出过程。', '用三句话说明前缀缓存的作用。']
with open('workloads/text-check.jsonl', 'w', encoding='utf-8') as f:
    for i, question in enumerate(questions):
        ids = tokenizer.apply_chat_template([{'role': 'user', 'content': question}], add_generation_prompt=True)
        f.write(json.dumps(dict(rid=f'text-{i}', arrival_s=i, input_ids=ids,
                                max_new_tokens=256, ignore_eos=False), ensure_ascii=False) + '\n')
PY
python experiments/run_case.py --policy fcfs --input workloads/text-check.jsonl --output runs/text-fcfs
python experiments/run_case.py --policy aged-remaining --input workloads/text-check.jsonl --output runs/text-aged-remaining
```

人工阅读这两份 `client.jsonl` 的 `text`、完成原因和错误字段。这是小范围回答观察，不是通用质量基准，也不混入性能主表。

## 10. 回传、分析与面试材料

服务器：

```bash
cd "$HOME/sglang-scheduler-lab"
git diff > results/project-working.diff
git -C upstream/sglang log -1 --oneline > results/server-source-commit.txt
tar -czf /tmp/sglang-results.tar.gz runs results configs patches
```

若项目由压缩包传入尚未启用项目 Git，先 `git init`、设置本地提交身份并提交项目文件；否则略过 `git diff` 一行，直接回传文件。上游 Git 与支持性项目 Git 分开。

登录设备：

```bash
scp "$SERVER:/tmp/sglang-results.tar.gz" .
mkdir -p received
tar -xzf sglang-results.tar.gz -C received
```

完整原始包先保存在登录设备，可再复制到 Windows 分析。GitHub 网页端手动上传代码补丁、小型表格、图和说明；大日志与完整输入包另行保留，不上传模型权重。面试叙述从实际表格提炼问题、结果、代价及负结果，填写 `results/interview-notes.md`，不预写尚不存在的性能提升百分比。
