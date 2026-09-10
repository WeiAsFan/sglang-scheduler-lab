# SGLang 调度实验

`sglang-scheduler-lab` 是面向 **AI 推理系统工程师面试**的小型推理优化项目：比较 SGLang 原生请求排序策略与基于剩余 prefill 工作量、等待时间的候选策略，量化短请求首 token 延迟、长请求等待、吞吐和调度 CPU 开销之间的取舍。

当前已实现四种候选排序策略、上游接入补丁、五类固定轨迹、流式回放、GPU 标定采集与拟合、逐轮分析工具，并完成本地 CPU 正确性检查。远程 A6000 的源码、模型和 Python 环境已准备完成，核心模块导入与 CLI 检查已通过，机制探索、三种子重复、候选范围消融和 GPU 成本标定已执行；其中四轮各有一个失败请求，原因仍需原始记录核对。当前正式对照固定使用 `prefix-conflict`、速率 4、300 条请求、3 个随机种子，比较 `fcfs`、`lpm`、`dfs-weight`、`hrrn` 和 `short-remaining`；原始结果已保留在 `runs/`，逐轮 CSV 和成本标定在 `results/20260910/`；服务器原始 `runs/` 尚未完整回传到仓库。后续产物统一进入 `results/YYYYMMDD/`。样本规模仍属于项目阶段性实验，结论只覆盖当前模型、硬件、后端和负载设置。

## 文档

- [实验进度与结论边界](docs/experiment-status.md)：30 轮结果、失败与证据缺口、下一步顺序。
- [服务器环境](docs/environment.md)：已报告的 Python、CUDA、后端与安装差异。
- [共同语言](CONTEXT.md)：统一项目交付、请求调度、实验指标和运行环境的含义。
- [调度策略调研](docs/scheduling-research.md)：原生策略、源码依据、候选方案、实验设计和面试讲解重点。
- [项目设计](docs/project-design.md)：策略规则、SGLang 接入方式、A6000 初始配置、成本标定和结果记录。
- [实现计划](docs/implementation-plan.md)：工作顺序、各阶段交付物、验证方式和单卡实验预算。
- [Linux 操作手册](docs/operations-linux.md)：登录设备下载与传输、服务器离线安装、策略比较、标定、分析和产物回传。
- [本地验证记录](docs/local-validation.md)：已验证的代码行为和仍需服务器验证的部分。
- [协作约定](AGENTS.md)：中文沟通、开发范围和实验约束。

## 已确认方向

核心原生对照为 `fcfs`、`lpm`、`dfs-weight`、`hrrn`；已实现输入长度排序、剩余 token 排序、等待超阈值提升和经过标定的耗时估计变体；最终参数尚未确定。

实现位于 [scheduler.patch](patches/scheduler.patch)，应用到 [upstream-base.txt](patches/upstream-base.txt) 指定的完整源码。新增模块随补丁进入 SGLang；支持性仓库不另存一份重复调度实现。`aged-cost` 使用 [实测模型](results/20260910/calibration/a6000-cost-r1.json)。留出耗时误差较小，但当前留出排序相关性与仅按 R 排序相同，在线对照尚未体现明确收益。

已有服务器按 [运行手册](docs/operations-linux.md)第 1 节恢复，从失败记录回传和候选范围重复继续。新建环境才执行第 2 节；第 8、9 节规定按当天日期目录整理与回传。

用户已认可上述策略方向。`aged-lpm`、`hrrn-time` 保留为有具体分析需要时再做的补充变体。

`hrrn` 已于 2026-09-08 合入上游，包含未缓存长度和 token 等待量。项目贡献应落在真实系统实现、实际时间与成本估计的适用范围、以及可解释的实验结果上。[上游 HRRN 合入记录](https://github.com/sgl-project/sglang/pull/32911)

## 运行边界

| 环境 | 职责 | 文件流转 |
| --- | --- | --- |
| 当前 Windows 工作区 | 代码、文档、结果分析 | 准备项目文件，接收结果副本 |
| Linux 登录设备 | 下载依赖和输入，通过 `ssh` 操作服务器 | 向服务器传文件，接收实验产物，通过 GitHub 网页端手动发布 |
| 远程实验服务器 | 执行真实 SGLang GPU 实验，使用本地 Git 记录代码 | 无外网，不向 GitHub 推送 |

已报告环境：**单卡 RTX A6000，Python 3.12.8，驱动 `580.173.02`，PyTorch cu129，本地 nvcc 12.1.105**。当前所有正常对照采用 `TP=1`、BF16、Triton attention 和 PyTorch sampling，参数见 `configs/a6000.json`。

发布不是启动实验的前置条件。主要实验引擎按当前题目确定为 SGLang；背景说明中出现的 vLLM 不自动加入实验范围。
