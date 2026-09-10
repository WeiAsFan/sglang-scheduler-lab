"""在服务端本机回放固定开放到达轨迹，记录实际发送偏差。"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import aiohttp

from common import read_jsonl, write_jsonl


async def request(session, url, row, epoch, timeout):
    start = time.perf_counter()
    result = dict(
        rid=row["rid"],
        input_tokens=len(row["input_ids"]),
        planned_s=epoch + row.get("arrival_s", 0),
        send_s=start,
        send_lag_ms=(start - epoch - row.get("arrival_s", 0)) * 1000,
        ttft_ms=None,
        success=False,
        output_tokens=0,
        cached_tokens=None,
    )
    payload = dict(
        rid=row["rid"],
        input_ids=row["input_ids"],
        stream=True,
        sampling_params=dict(
            temperature=0,
            max_new_tokens=row["max_new_tokens"],
            ignore_eos=row.get("ignore_eos", True),
        ),
    )
    terminal = False
    try:
        async with session.post(
            url + "/generate",
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            response.raise_for_status()
            # aiohttp 的异步迭代按换行分割，不把 TCP 数据包当作 SSE 事件。
            async for raw in response.content:
                raw = raw.strip()
                if not raw.startswith(b"data:"):
                    continue
                data = raw[5:].strip()
                if data == b"[DONE]":
                    terminal = True
                    continue
                event = json.loads(data)
                if "error" in event:
                    raise RuntimeError(str(event["error"]))
                meta = event.get("meta_info") or {}
                count = meta.get("completion_tokens", result["output_tokens"])
                if count > 0 and result["ttft_ms"] is None:
                    result["ttft_ms"] = (time.perf_counter() - start) * 1000
                result["output_tokens"] = count
                if "cached_tokens" in meta:
                    result["cached_tokens"] = meta["cached_tokens"]
                if "cached_tokens_details" in meta:
                    result["cached_tokens_details"] = meta["cached_tokens_details"]
                if "text" in event:
                    result["text"] = event["text"]
                if meta.get("finish_reason"):
                    result["finish_reason"] = meta["finish_reason"]
                    terminal = True
            finish = result.get("finish_reason", {})
            aborted = isinstance(finish, dict) and finish.get("type") == "abort"
            result["success"] = (
                terminal and result["ttft_ms"] is not None and not aborted
            )
            if not result["success"]:
                result["error"] = "流未正常完成或服务端中止"
    except (Exception, asyncio.CancelledError) as e:
        result["error"] = f"{type(e).__name__}: {e}"
    result["end_s"] = time.perf_counter()
    return result


async def replay(rows, url, output, timeout=600):
    epoch = time.perf_counter()
    tasks = []
    # limit=0 不以客户端连接池限制服务器负载。
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=0)
    ) as session:
        try:
            for row in rows:
                await asyncio.sleep(
                    max(0, epoch + row.get("arrival_s", 0) - time.perf_counter())
                )
                tasks.append(
                    asyncio.create_task(request(session, url, row, epoch, timeout))
                )
            results = await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            settled = await asyncio.gather(*tasks, return_exceptions=True)
            results = [x for x in settled if isinstance(x, dict)]
            write_jsonl(output, results)
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--url", default="http://127.0.0.1:30000")
    p.add_argument("--timeout", type=float, default=600)
    args = p.parse_args()
    asyncio.run(replay(read_jsonl(args.input), args.url, args.output, args.timeout))


if __name__ == "__main__":
    main()
