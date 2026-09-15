"""从已有运行目录导出轻量证据，不启动服务、不改写原始记录。"""

import argparse
import csv
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path

from common import write_json, write_jsonl


def records(path):
    if path.exists():
        with path.open(encoding="utf-8-sig") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def stats(values):
    if not values:
        return None
    values = sorted(values)

    def percentile(q):
        pos = (len(values) - 1) * q
        low = int(pos)
        return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (
            pos - low
        )

    return {
        "count": len(values),
        "sum": sum(values),
        "max": values[-1],
        "p50": percentile(0.5),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
    }


def export(run, output, include_text=False):
    destination = output / run.name
    destination.mkdir(parents=True, exist_ok=True)
    input_path = run / "input.jsonl"
    client_path = run / "client.jsonl"
    if not input_path.exists() and (run / "calibration-input.jsonl").exists():
        input_path = run / "calibration-input.jsonl"
        client_path = run / "calibration-client.jsonl"
    inputs = {}
    for row in records(input_path):
        inputs[row["rid"]] = {
            "input_tokens": len(row["input_ids"]),
            "arrival_s": row.get("arrival_s"),
            "max_new_tokens": row.get("max_new_tokens"),
            "group": row.get("group"),
            "sample": row.get("sample"),
            "split": row.get("split"),
            "ignore_eos": row.get("ignore_eos"),
        }
    clients = {r["rid"]: r for r in records(client_path)}
    servers = {r["rid"]: r for r in records(run / "server-requests.jsonl")}
    ids = (
        list(inputs)
        if input_path.exists()
        else list(dict.fromkeys([*clients, *servers]))
    )
    fields = (
        "planned_s",
        "send_s",
        "send_lag_ms",
        "ttft_ms",
        "end_s",
        "success",
        "output_tokens",
        "cached_tokens",
        "cached_tokens_details",
        "error",
        "finish_reason",
    )
    rows, failed = [], []
    for rid in ids:
        c, s = clients.get(rid, {}), servers.get(rid, {})
        row = dict(
            rid=rid,
            **inputs.get(rid, {}),
            client_record_present=rid in clients,
            server_record_present=rid in servers,
        )
        row.update({key: c.get(key) for key in fields})
        row.update(
            {
                key: s.get(key)
                for key in ("first_enqueue_s", "first_admit_s", "retractions")
            }
        )
        if rid not in inputs:
            row["input_tokens"] = c.get("input_tokens", s.get("input_tokens"))
        if row["first_admit_s"] is not None and row["first_enqueue_s"] is not None:
            row["first_wait_ms"] = (
                row["first_admit_s"] - row["first_enqueue_s"]
            ) * 1000
        if include_text:
            row["text"] = c.get("text")
        rows.append(row)
        if rid not in clients or c.get("success") is not True:
            failed.append(row)
    write_jsonl(destination / "requests.jsonl", rows)
    write_jsonl(destination / "failed-requests.jsonl", failed)

    copied, missing = [], []
    for name in (
        "run.json",
        "summary.json",
        "server-info.json",
        "server-trace.json",
        "input.meta.json",
        "cost-model.json",
        "gpu.jsonl",
        "environment-gpu.txt",
        "environment-packages.txt",
    ):
        if (run / name).exists():
            shutil.copyfile(run / name, destination / name)
            copied.append(name)
        else:
            missing.append(name)
    metadata = (
        json.loads((run / "run.json").read_text(encoding="utf-8-sig"))
        if (run / "run.json").exists()
        else {}
    )
    start = metadata.get("measurement_start_s")
    end = metadata.get("measurement_end_s", metadata.get("snapshot_s"))
    groups = defaultdict(lambda: defaultdict(list))
    counts, buckets = defaultdict(int), {}
    schedule = run / "scheduling.csv"
    if schedule.exists():
        with schedule.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                at = float(row["start_s"])
                if (start is not None and at < start) or (end is not None and at > end):
                    continue
                kind = row["kind"]
                counts[kind] += 1
                for key, value in row.items():
                    if value and (
                        key in ("queue_len", "candidates", "aged")
                        or key.endswith(("_ms", "_calls"))
                    ):
                        groups[kind][key].append(float(value))
                if kind == "candidates" and float(row.get("aged") or 0) > 0:
                    counts["candidates_with_aged"] += 1
                if kind == "priority" and row.get("policy") != row.get(
                    "effective_policy"
                ):
                    counts["policy_fallback_calls"] += 1
                # 分 kind 汇总，避免把嵌套计时重复相加。
                bucket = int(at // 10) * 10
                b = buckets.setdefault(
                    (bucket, kind),
                    {
                        "start_s": bucket,
                        "kind": kind,
                        "calls": 0,
                        "queue_max": None,
                        "aged_max": None,
                        "aged_positive_calls": 0,
                        "cpu_ms_sum": None,
                        "wall_ms_sum": None,
                    },
                )
                b["calls"] += 1
                for key in ("queue", "aged"):
                    value = row.get("queue_len" if key == "queue" else "aged")
                    if value:
                        b[key + "_max"] = max(b[key + "_max"] or 0, float(value))
                b["aged_positive_calls"] += int(
                    kind == "candidates" and float(row.get("aged") or 0) > 0
                )
                for key in ("cpu_ms", "wall_ms"):
                    if row.get(key):
                        b[key + "_sum"] = (b[key + "_sum"] or 0) + float(row[key])
    write_json(
        destination / "scheduling-summary.json",
        {
            "available": schedule.exists(),
            "window_start_s": start,
            "window_end_s": end,
            "window": "measurement" if start is not None else "available_record",
            "calls": dict(counts),
            "aged_call_fraction": (
                counts.get("candidates_with_aged", 0) / counts["candidates"]
                if counts.get("candidates")
                else None
            ),
            "metrics": {
                kind: {key: stats(values) for key, values in metrics.items()}
                for kind, metrics in groups.items()
            },
        },
    )
    write_jsonl(
        destination / "scheduling-timeline.jsonl", [buckets[k] for k in sorted(buckets)]
    )

    # 只保留错误及失败 rid 周边片段；限制长行并明确截断，不冒充完整日志。
    log = run / "server.log"
    matched = set()
    lines = (
        log.read_text(encoding="utf-8", errors="replace").splitlines()
        if log.exists()
        else []
    )
    pattern = re.compile(
        "error|exception|traceback|out of memory|disconnected", re.IGNORECASE
    )
    failed_ids = [r["rid"] for r in failed]
    for i, line in enumerate(lines):
        if pattern.search(line) or any(rid in line for rid in failed_ids):
            matched.update(range(max(0, i - 3), min(len(lines), i + 4)))
    selected = sorted(matched)[:300]
    (destination / "log-excerpts.txt").write_text(
        "仅为错误／失败 rid 周边片段，最多 300 行，每行最多 1000 字符。\n"
        + "\n".join(
            f"{i + 1}: {lines[i][:1000]}"
            + (" [行截断]" if len(lines[i]) > 1000 else "")
            for i in selected
        ),
        encoding="utf-8",
    )
    write_json(
        destination / "export-info.json",
        {
            "source": str(run),
            "request_count": len(rows),
            "failed_or_missing_client": len(failed),
            "input_present": input_path.exists(),
            "client_present": client_path.exists(),
            "server_requests_present": (run / "server-requests.jsonl").exists(),
            "copied": copied,
            "absent_optional_files": missing,
            "include_text": include_text,
            "log_present": log.exists(),
            "log_excerpt_truncated": len(matched) > len(selected),
            "note": "原始 token 输入与普通回答正文未导出；缺失文件不表示零失败或零等待。",
        },
    )
    return destination


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("runs", type=Path, nargs="+")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument(
        "--include-text", action="store_true", help="仅正常文本观察使用，保留回答正文"
    )
    args = p.parse_args()
    for run in args.runs:
        if not run.is_dir():
            p.error(f"运行目录不存在：{run}")
        print(export(run, args.output, args.include_text))


if __name__ == "__main__":
    main()
