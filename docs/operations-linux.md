# Linux 操作手册

更新日期：2026-09-15。当前环境、四种候选和测量工具已在 A6000 实际运行。已有 30 轮每轮 300 请求的历史性能汇总、成本标定、两档速率的 600 请求主比较、三类补充 workload 和正常文本观察；现有汇总已分析，完整记录仍在服务器；下一步先按第 8、9 节补轻量证据。先阅读 [实验进度](experiment-status.md) 与 [服务器环境](environment.md)，已有服务器从第 1 节恢复，不重装环境或重复应用补丁。

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

## 4. 当前优先事项：导出现有证据

先执行第 8、9 节，导出已有运行目录中的逐请求标量、调度摘要和错误片段。覆盖 20260910 历史轮次及标定、20260911 主比较与 aging 对照、20260914 五次性能重试及两次正常文本观察；失败和启动失败目录也保留导出结果。

K=128/0 的 seed=2/3、300 请求、4 req/s 重复已经完成，不再重跑。K=64 的 trace/no-trace 单轮对照也已完成，短请求 P99 差约 0.12%；该结论不外推到 K=0。FCFS 原始轮及三次同条件重试各有断开，先分析错误请求及相邻发送时间、服务端关联与日志，不继续重复同一命令等待成功。

先补证据，再决定纯成本排序、公平性压力和第二种 workload 正式重复的具体参数。第 3、5、6 节是后续运行方法，不表示现在需要把已做矩阵重新执行。

## 5. 后续负载、样本与 aging

五个生成器名称为 `mixed-low-reuse`、`prefix-conflict`、`hot-prefix`、`long-wait`、`burst-decode`。五类轨迹均已生成；`hot-prefix`、`long-wait`、`burst-decode` 的代表性结果在 `results/20260911/`，用于观察热点复用、长请求等待、突发与长 decode 干扰。实际 long-wait 的长等待最大值只有 0.33/0.45 ms，未形成公平性压力；三类各仅一个 seed、两个策略。

已在相同 `prefix-conflict` 负载上选择 0.5 和 1.0 req/s 两个水平，并完成每个水平 600 请求、3 个 seed 的主比较。4 req/s 的历史轮次仍是严重积压条件，不能当作线上正常工作点。结果解释继续关注成功短请求数；前缀负载每 600 个请求只有约 209–213 个成功短请求，整体请求数不等于短请求样本数。

大样本比较保留 `fcfs/lpm/dfs-weight/hrrn` 四个原生基线、一个选定候选和三个种子。相同 seed 内复用输入、预热与配置；跨 seed 分行报告，不平均 P99 冒充总体 P99。

aging=100/500/1000 ms 已完成单种子探索，三档均接近 FCFS。此前尝试分离成本排序，在 1.0 req/s、K=64 下使用 300000 ms 阈值；`aged-remaining` 候选扫描最大 aged 数为 80，`aged-cost` 为 79，均有大量调用出现 aged。但最大长等待约 427 秒，高于 300 秒阈值，约 41.6% 候选扫描出现 aged（服务器报告，待导出核对）。因此它是成本与 aging 混合对照，既非纯成本排序，也不能证明等待上界。后续同 K、同输入、同阈值比较，须查看实际 aged=0 才能作纯排序解释；不凭阈值看起来很大就认定已关闭 aging。

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

正常文本观察已完成，结果在 `results/20260914/`。生成轨迹时若本地 tokenizer 返回 `BatchEncoding`，应取其 `input_ids` 字段并转换为普通 `list` 后写入 JSON；本项目的最终 `workloads/text-check.jsonl` 已按此格式生成。服务器报告人工阅读两个 `client.jsonl` 后每轮 3 个请求均成功、有文本和完成原因、无错误；本地尚缺正文，按第 8 节保留 text 导出即可，无需重跑。它不混入合成性能主表，不把逐字相同设成性能实验条件。

```bash
python - <<'PY'
import json
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained('models/Qwen2.5-7B-Instruct', local_files_only=True)
questions = ['解释 prefill 与 decode 的区别。', '计算 17 乘以 23，并给出过程。', '用三句话说明前缀缓存的作用。']
with open('workloads/text-check.jsonl', 'w', encoding='utf-8') as f:
    for i, question in enumerate(questions):
        ids = tokenizer.apply_chat_template([{'role': 'user', 'content': question}], add_generation_prompt=True)
        if hasattr(ids, 'keys'):
            ids = ids['input_ids']
        ids = list(ids)
        f.write(json.dumps(dict(rid=f'text-{i}', arrival_s=i, input_ids=ids,
                                max_new_tokens=256, ignore_eos=False), ensure_ascii=False) + '\n')
PY
python experiments/run_case.py --policy fcfs --input workloads/text-check.jsonl --output "runs/${DAY}-text-fcfs"
python experiments/run_case.py --policy short-remaining --candidates 0 --input workloads/text-check.jsonl --output "runs/${DAY}-text-short-remaining"
```

上述命令供需要新增文本观察时使用；已有两轮仅需导出正文。它不混入合成性能主表，不把逐字相同设成性能实验条件。

## 8. 服务器补轻量证据：results/当天日期/

**服务器整理、Linux 登录设备接收、Windows 分析与 GitHub 上传，都保留 `results/YYYYMMDD/` 层级。** 日期取本次整理当天北京时间；旧运行的 run_id 不变，原始实验时间仍读各轮记录。完整 token 输入、预热轨迹和完整日志保留服务器 `runs/<run_id>/`，本次只传轻量证据。

先在联网 Linux 登录设备下载仓库最新版本，从项目根目录把导出工具传到已有服务器工作区。设置实际服务器地址：

```bash
SERVER=user@your-server
REMOTE=/mnt_d/huangxiaoyuan/sglang-scheduler-lab-v1.0
scp experiments/export_evidence.py "$SERVER:$REMOTE/experiments/"
```

工具使用 Python 标准库和服务器已有的 `experiments/common.py`，不安装依赖、不改 SGLang 补丁、不启动 GPU 实验。进入服务器后，恢复第 1 节环境；在实验结束后导出现有运行目录：

```bash
cd /mnt_d/huangxiaoyuan/sglang-scheduler-lab-v1.0
source .venv/bin/activate
DAY=$(TZ=Asia/Shanghai date +%Y%m%d)
OUT="results/$DAY"
mkdir -p "$OUT/evidence"
# 每个一级运行目录分别导出；包括失败、启动失败和标定目录。
for RUN_DIR in runs/*/; do
  python experiments/export_evidence.py "$RUN_DIR" --output "$OUT/evidence" || break
done
# 两轮文本观察另保留回答正文，更新对应的轻量文件。
python experiments/export_evidence.py \
  runs/20260914-text-fcfs runs/20260914-text-short-remaining \
  --output "$OUT/evidence" --include-text
```

`runs/*/` 只匹配一级目录。也可把上述循环换成一条具体目录命令，例如 `python experiments/export_evidence.py runs/20260914-main-prefix-r05-s2-fcfs-n600-retry1 --output "$OUT/evidence"`。若读到损坏记录而报错，保留报错与目录名，处理该目录后继续其余目录，不把未导出轮次写成已完成。

每轮输出如下，不包含 token 数组：

```text
results/YYYYMMDD/
  README.md
  evidence/<run_id>/
    export-info.json             # 来源、存在／缺失文件、请求数、日志截断情况
    requests.jsonl               # rid、原始长度、发送/首 token/入队/准入时间等标量
    failed-requests.jsonl        # 失败或缺失客户端的请求；成功轮可为空
    scheduling-summary.json     # 按 kind 分别统计 CPU/耗时/队列/候选/aged
    scheduling-timeline.jsonl   # 每 10 秒、按 kind 分开的时间桶
    log-excerpts.txt             # 错误及失败 rid 周边片段，最多 300 行
    run.json                    # 以下文件仅在源目录实际存在时复制
    summary.json
    server-info.json
    server-trace.json
    input.meta.json
    cost-model.json
    gpu.jsonl
    environment-gpu.txt
    environment-packages.txt
  config-used.json
  environment-packages.txt
  server-source-commit.txt
  upstream-working.diff
```

`requests.jsonl` 以实际输入的 rid 关联客户端与服务端记录，保留失败和缺失标记、完成原因、cached tokens、生成 token 数与首次等待。普通运行不保留回答正文；`--include-text` 仅用于上述正常文本观察。输入缺失时使用已有客户端／服务端 rid，并在 `export-info.json` 明示，不能声称已经知道完整计划集合。

`scheduling-summary.json` 优先使用 `run.json` 中计时窗口，否则统计现有记录并标为 `available_record`；按 `kind` 分开报告，嵌套 CPU 不能相加。`aged_call_fraction` 是出现 aged 的候选扫描调用占比，不是超阈值请求比例，也不是延迟上界。no-trace 或启动失败缺少调度数据时 `available=false`，不能解读为零开销。10 秒桶只用于观察时间变化，不是逐次调度回放。

日志仅保留错误及失败 rid 前后 3 行，每行最多 1000 字符，并标明截断。片段不足以定位原因时，在服务器继续查看完整日志，将相关时段另存小型文本说明。没有匹配到片段不代表服务没有错误。导出工具不会重新计算主比较表；现有 CSV 继续使用，新实验在完整运行目录上调用 `analyze.py`。

补本次环境信息：

```bash
cp configs/a6000.json "$OUT/config-used.json"
python -m pip freeze > "$OUT/environment-packages.txt"
git -C upstream/sglang log -1 --oneline > "$OUT/server-source-commit.txt"
git -C upstream/sglang diff > "$OUT/upstream-working.diff"
```

这些是导出当天的环境快照；历史参数以各轮 `run.json` 为准。历史日期目录已有的成本模型、320 条标定样本和逐轮 CSV 不用重复复制。若运行使用了未跟踪的新脚本，把实际文件副本放入当天目录的 `code/`。

在当天 `README.md` 写明本次导出的 run_id、对应历史日期、完整目录所在服务器路径、未导出或缺失的文件、导出报错与需要解释的问题。优先说明四次 FCFS 的失败 rid 和日志片段、两个 300 秒 aging 对照、K=0 主比较、启动失败、标定和两轮文本观察。不得把轻量摘要写成完整调度轨迹已回传；它能支持请求分位数与 aged 计数核对，不能恢复完整 token 输入或每次候选顺序。

## 9. 登录设备接收并通过 GitHub 网页提交

在登录设备项目根目录执行。`DAY` 填服务器刚才实际选定的日期；以下 20260915 是示例，后续操作替换为当天值：

```bash
SERVER=user@your-server
REMOTE=/mnt_d/huangxiaoyuan/sglang-scheduler-lab-v1.0
DAY=20260915
mkdir -p "results/$DAY/evidence"
rsync -a --info=progress2 "$SERVER:$REMOTE/results/$DAY/evidence/" "results/$DAY/evidence/"
scp "$SERVER:$REMOTE/results/$DAY/README.md" \
  "$SERVER:$REMOTE/results/$DAY/config-used.json" \
  "$SERVER:$REMOTE/results/$DAY/environment-packages.txt" \
  "$SERVER:$REMOTE/results/$DAY/server-source-commit.txt" \
  "$SERVER:$REMOTE/results/$DAY/upstream-working.diff" "results/$DAY/"
```

没有 rsync 时，用 `scp -r "$SERVER:$REMOTE/results/$DAY/evidence" "results/$DAY/"` 替换 rsync 行。有本次新增 CSV、图、标定模型或 `code/` 时，按文件名另行复制到同一天目录；保留原来的 run_id，不覆盖历史失败轮。完整运行数据继续留在服务器。

GitHub 网页端进入 `results/$DAY/` 后，用 Add file → Upload files 上传该目录中的轻量文件及 `evidence/` 文件夹。数量较多时按运行目录分批上传，每批仍保持 `results/$DAY/evidence/<run_id>/` 层级；README 记录已上传与待补轮次。Windows 接收副本时保留相同层级。

服务器与登录设备不承担 GitHub push；本地 Windows 可提交推送项目代码与文档。发布不是启动实验的前置条件。
