# 服务器环境记录

记录日期：2026-09-10。

本文记录 `sglang-scheduler-lab-v1.0` 在远程服务器上的环境和实验状态。环境准备已完成，首轮探索、两类负载的策略比较以及 `prefix-conflict` 三种子正式重复对照均已执行。

## 服务器实况

| 项目 | 实际值 |
| --- | --- |
| 主机 | `66` |
| 工作区 | `/mnt_d/huangxiaoyuan/sglang-scheduler-lab-v1.0` |
| 操作系统 | Ubuntu 22.04.5 LTS |
| CPU 架构 | `x86_64` |
| glibc | 2.35 |
| 选用 Python | 3.12.8 |
| Python 3.11 | 3.11.9，可用但未用于本项目环境 |
| GPU | NVIDIA RTX A6000，49140 MiB |
| NVIDIA 驱动 | `580.173.02` |
| `nvidia-smi` CUDA 能力 | 13.0 |
| `torch.version.cuda` | 12.9 |
| 本地 `nvcc` | CUDA 12.1.105 |
| `/mnt_d` 可用空间 | 约 4.0 TB |
| 根分区可用空间 | 约 231 GB |

GPU 检查结果为 `torch.cuda.is_available() == True`，设备名称为 `NVIDIA RTX A6000`。`nvidia-smi` 报告的是驱动支持能力，`torch.version.cuda` 是 PyTorch 构建版本，两者分别保留。

## 源码与模型

- 上游源码固定提交：`0027af2eace5ccc2116c8c993ce71aebf1535264`。
- 上游本地基线提交：`b1f4b44`。
- 项目补丁本地提交：`c3f7c49`。
- 源码补丁已应用，`upstream/sglang` 工作树干净。
- 上游源码压缩包 SHA-256：`a73f5c72595aa616edd12d6c411b44f040af28539b178982c8c7beed937ca9d1`。
- 模型路径：`/mnt_d/huangxiaoyuan/sglang-scheduler-lab-v1.0/models/Qwen2.5-7B-Instruct`。
- 模型约占 15 GB，包含 4 个 `safetensors` 权重分片、权重索引、配置和 tokenizer 文件。

模型由服务器已有的 `/mnt_d/huangxiaoyuan/vllm/models/Qwen2.5-7B-Instruct` 复制得到，没有重复下载。实验命令从项目配置直接使用项目内模型路径；合成 token 轨迹仍需按照操作手册的性能边界解释。

## Python 环境

项目使用独立环境：`.venv`。环境中的通用包尽量复用服务器已有的 `/mnt_d/huangxiaoyuan/vllm/.venv-cu129`，以硬链接方式放入项目环境；原环境未被修改。项目专用包和后续替换包安装在项目环境中。

已验证的关键版本如下：

| 包 | 版本 |
| --- | --- |
| `torch` | `2.13.0+cu129` |
| `torchaudio` | `2.11.0+cu129` |
| `torchvision` | `0.28.0+cu129` |
| `triton` | `3.7.1` |
| `sglang-kernel` | `0.4.6.post1+cu129` |
| `sgl-deep-gemm` | `0.1.7+cu129` |
| `flashinfer-python` | `0.6.18`，满足固定源码版本门槛；当前 backend 不使用其 JIT |
| `transformers` | `5.15.0`，复用版本 |
| `aiohttp` | `3.14.3` |
| `numpy` | `2.3.5` |
| `scipy` | `1.18.1` |
| `matplotlib` | `3.11.1` |
| `orjson` | `3.12.0` |
| `gguf` | `0.19.0` |
| `soundfile` | `0.13.1` |

安装时设置了 `SGLANG_BUILD_RUST_EXTS=none`，因为本项目使用纯文本 HTTP 回放，不需要构建 Rust 扩展。

首轮启动尝试发现服务器实际 `/usr/local/cuda` 指向 CUDA 12.1，而 FlashInfer 0.6.18 的 JIT 编译命令使用了该 `nvcc` 不支持的 `--compress-mode=size` 参数。根据操作手册的兼容性处理，统一将 `configs/a6000.json` 的 `attention_backend` 切换为 `triton`，并设置 `sampling_backend` 为 `pytorch`。后续所有策略必须共用这一配置；FlashInfer 启动失败目录仍保留在 `runs/` 中，不作为正常实验结果。

固定上游源码的项目元数据默认列出了部分 CUDA 13 依赖和其他模型扩展。当前环境按照操作手册采用 CUDA 12.9 wheel，并复用了已有可用包；因此 `pip check` 仍会报告若干元数据版本差异或非本实验路径的可选包缺失。当前已通过的接入检查包括 SGLang 导入、CLI 参数解析、项目 CPU 单元测试、完整模型启动、缓存预热、真实 GPU 前向和服务端记录导出；依赖声明差异仍需在发布环境说明中保留。

## 已执行检查

在服务器项目根目录执行：

```bash
source .venv/bin/activate
python -c 'import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))'
SGLANG_BUILD_RUST_EXTS=none python -m sglang.launch_server --help | grep schedule-
python -m unittest discover -s tests -v
```

结果：

- PyTorch 能识别 A6000，CUDA 可用。
- `launch_server --help` 成功，并显示 `short-input`、`short-remaining`、`aged-remaining`、`aged-cost` 以及候选、老化、成本模型和 trace 参数。
- 项目 11 项单元测试全部通过。
- 已执行 `experiments/run_case.py`。`mixed-low-reuse` 完成 7 个策略的探索，`prefix-conflict` 完成 7 个策略的探索，并以 `fcfs`、`lpm`、`dfs-weight`、`hrrn`、`short-remaining` 五个策略完成 3 个随机种子的正式重复对照。
- 已生成客户端明细、服务端请求记录、调度 trace、环境快照和逐轮分析 CSV。GPU 成本标定、候选数四档和 aging 三档消融均已完成；更大样本主比较仍未执行。
- `K=32` 已完成；此前 `K=128` 启动时因服务器已有 Ollama 进程占用约 35.7 GiB 显存而 OOM，失败日志已保留。待 GPU 空闲后已用独立目录成功完成 `K=128`，没有覆盖该失败记录。

## 下一步

现有环境直接按 [运行手册](operations-linux.md)第 1 节恢复。先回传原始请求与调度记录解释四个失败，再补 K=128/0 重复、记录开关和更大样本对照；不要重新执行已经完成的安装流程。当前成本模型并未证明相比仅按 R 排序的留出排序优势，在线对照也尚无明确收益，见 [实验进度](experiment-status.md)。

后续产物统一整理并回传至 `results/YYYYMMDD/`。当前 CSV 与标定产物在 `results/20260910/`；原始 `runs/` 据服务器报告已保留，但未完整上传到仓库。首次 K=128 OOM 和 FlashInfer 启动失败日志与正常运行分开保留，不作为成功性能结果。
