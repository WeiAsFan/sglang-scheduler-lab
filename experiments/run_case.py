"""在 Linux 服务器启动一个 SGLang 子进程，运行一轮并导出记录。"""

import argparse
import asyncio
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import aiohttp

from common import read_jsonl, write_json
from replay import replay, request


async def get_json(session, url, method="GET"):
    async with session.request(method, url) as response:
        response.raise_for_status()
        if "/flush_cache" in url:
            return await response.text()
        return await response.json(content_type=None)


async def run(args):
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.model:
        config["model_path"] = str(args.model.resolve())
    config.update(
        host="127.0.0.1",
        port=args.port,
        schedule_policy=args.policy,
        schedule_candidate_limit=args.candidates,
        schedule_aging_threshold_ms=args.aging_ms,
    )
    if not args.no_trace:
        config["schedule_trace_dir"] = str(directory)
    if args.cost_model:
        shutil.copyfile(args.cost_model, directory / "cost-model.json")
        config["schedule_cost_model"] = str(directory / "cost-model.json")
    if args.calibrate:
        config["disable_overlap_schedule"] = True
    command = [sys.executable, "-m", "sglang.launch_server"]
    for key, value in config.items():
        if value is None or value is False:
            continue
        command.append("--" + key.replace("_", "-"))
        if value is not True:
            command.append(str(value))
    # 避免把已有服务的健康响应误认为本轮启动成功。
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", args.port))
    env = os.environ.copy()
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    if args.calibrate:
        env["SGLANG_LAB_CALIBRATE"] = "1"
    else:
        env.pop("SGLANG_LAB_CALIBRATE", None)
    record = dict(
        config=config,
        command=command,
        status="starting",
        platform=platform.platform(),
        python=sys.version,
        calibration=args.calibrate,
        started_unix_s=time.time(),
    )
    for name, cmd in (
        ("gpu", ["nvidia-smi"]),
        ("packages", [sys.executable, "-m", "pip", "freeze"]),
    ):
        result = subprocess.run(cmd, text=True, capture_output=True)
        (directory / f"environment-{name}.txt").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
    if args.input:
        shutil.copyfile(args.input, directory / "input.jsonl")
        meta = args.input.with_suffix(".meta.json")
        if meta.exists():
            shutil.copyfile(meta, directory / "input.meta.json")
    write_json(directory / "run.json", record)
    url = f"http://127.0.0.1:{args.port}"
    with (directory / "server.log").open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        ) as session:
            try:
                deadline = time.monotonic() + args.startup_timeout
                while True:
                    if proc.poll() is not None:
                        raise RuntimeError("SGLang 启动退出，查看 server.log")
                    try:
                        async with session.get(url + "/health") as response:
                            if response.status == 200:
                                break
                    except (aiohttp.ClientError, asyncio.TimeoutError):
                        pass
                    if time.monotonic() >= deadline:
                        raise TimeoutError("SGLang 启动超时")
                    await asyncio.sleep(1)
                # 非计时预热后清缓存，随后构建轨迹指定的前缀状态。
                warm = dict(rid="engine-warm", input_ids=[1000] * 512, max_new_tokens=8)
                result = await request(session, url, warm, time.perf_counter(), 600)
                if not result["success"]:
                    raise RuntimeError(f"预热请求失败：{result.get('error')}")
                await get_json(session, url + "/flush_cache?timeout=60", "POST")
                if args.calibrate:
                    from calibrate import collect

                    await collect(session, url, directory, args.samples)
                else:
                    warm_path = args.warmup or args.input.with_suffix(".warmup.jsonl")
                    if warm_path.exists():
                        shutil.copyfile(warm_path, directory / "warmup.jsonl")
                        for row in read_jsonl(warm_path):
                            result = await request(
                                session, url, row, time.perf_counter(), 600
                            )
                            if not result["success"]:
                                raise RuntimeError(f"前缀预热失败：{row['rid']}")
                    record["measurement_start_s"] = time.perf_counter()
                    write_json(directory / "run.json", record)
                    await replay(
                        read_jsonl(args.input),
                        url,
                        directory / "client.jsonl",
                        args.request_timeout,
                    )
                    record["measurement_end_s"] = time.perf_counter()
                record["status"] = "finished"
            except BaseException as e:
                record.update(
                    status="interrupted"
                    if isinstance(e, (KeyboardInterrupt, asyncio.CancelledError))
                    else "failed",
                    error=f"{type(e).__name__}: {e}",
                )
                raise
            finally:
                record["snapshot_s"] = time.perf_counter()
                if proc.poll() is None:
                    try:
                        # 此查询触发 scheduler 内存记录导出；在结束进程之前执行。
                        info = await get_json(session, url + "/server_info")
                        write_json(directory / "server-info.json", info)
                    except Exception as e:
                        record["export_error"] = str(e)
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        await asyncio.to_thread(proc.wait, timeout=30)
                    except subprocess.TimeoutExpired:
                        record["forced_stop"] = True
                        os.killpg(proc.pid, signal.SIGKILL)
                        await asyncio.to_thread(proc.wait)
                else:
                    record["export_error"] = "服务进程在导出记录前已退出"
                    if record["status"] == "finished":
                        record["status"] = "failed"
                record["server_returncode"] = proc.returncode
                write_json(directory / "run.json", record)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path("configs/a6000.json"))
    p.add_argument("--model", type=Path)
    p.add_argument("--input", type=Path)
    p.add_argument("--warmup", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--policy",
        default="fcfs",
        choices=(
            "fcfs",
            "lpm",
            "dfs-weight",
            "hrrn",
            "short-input",
            "short-remaining",
            "aged-remaining",
            "aged-cost",
        ),
    )
    p.add_argument("--candidates", type=int, default=64)
    p.add_argument("--aging-ms", type=float, default=500)
    p.add_argument("--cost-model", type=Path)
    p.add_argument("--port", type=int, default=30000)
    p.add_argument("--startup-timeout", type=float, default=1800)
    p.add_argument("--request-timeout", type=float, default=600)
    p.add_argument("--no-trace", action="store_true")
    p.add_argument("--calibrate", action="store_true")
    p.add_argument("--samples", type=int, default=20)
    args = p.parse_args()
    if sys.platform != "linux":
        p.error("run_case 在 Linux GPU 服务器运行")
    if not args.calibrate and args.input is None:
        p.error("性能回放需要 --input")
    if args.calibrate and args.no_trace:
        p.error("标定需要记录 GPU 样本")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
