"""逐轮统计；不混合不同负载、速率或种子的尾延迟。"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from common import read_jsonl, write_json


def percentile(values, q):
    return float(np.percentile(values, q)) if values else None


def summarize(directory):
    run = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    inputs = {r["rid"]: r for r in read_jsonl(directory / "input.jsonl")}
    clients = (
        read_jsonl(directory / "client.jsonl")
        if (directory / "client.jsonl").exists()
        else []
    )
    clients = [r for r in clients if r["rid"] in inputs]
    successful = [r for r in clients if r["success"]]
    servers = (
        read_jsonl(directory / "server-requests.jsonl")
        if (directory / "server-requests.jsonl").exists()
        else []
    )
    server = {r["rid"]: r for r in servers if r["rid"] in inputs}
    trace_available = (directory / "server-requests.jsonl").exists()
    trace_meta = directory / "server-trace.json"
    snapshot_s = (
        json.loads(trace_meta.read_text(encoding="utf-8"))["snapshot_s"]
        if trace_meta.exists()
        else run["snapshot_s"]
    )
    short = [
        r["ttft_ms"] for r in successful if len(inputs[r["rid"]]["input_ids"]) <= 2048
    ]
    long_ids = [rid for rid, r in inputs.items() if len(r["input_ids"]) >= 8192]
    waits, lower_bounds = [], []
    for rid in long_ids:
        row = server.get(rid)
        if row:
            if row["first_admit_s"] is not None:
                waits.append((row["first_admit_s"] - row["first_enqueue_s"]) * 1000)
            else:
                lower_bounds.append((snapshot_s - row["first_enqueue_s"]) * 1000)
    duration = (
        max(r["end_s"] for r in clients) - min(r["send_s"] for r in clients)
        if clients
        else 0
    )
    cache_available = bool(successful) and all(
        r["cached_tokens"] is not None for r in successful
    )
    result = dict(
        run=str(directory),
        policy=run["config"]["schedule_policy"],
        status=run["status"],
        candidate_limit=run["config"].get("schedule_candidate_limit"),
        aging_ms=run["config"].get("schedule_aging_threshold_ms"),
        planned=len(inputs),
        sent=len(clients),
        succeeded=len(successful),
        failed=len(clients) - len(successful),
        no_client_record=len(inputs) - len(clients),
        short_successes=len(short),
        short_ttft_p95_ms=percentile(short, 95),
        short_ttft_p99_ms=percentile(short, 99),
        long_wait_max_ms=max(waits, default=None),
        server_trace_available=trace_available,
        long_not_admitted=len(lower_bounds) if trace_available else None,
        long_missing_server_record=sum(r not in server for r in long_ids),
        long_wait_lower_bound_max_ms=max(lower_bounds, default=None),
        duration_s=duration,
        requests_per_s=len(successful) / duration if duration else None,
        output_tokens_per_s=sum(r["output_tokens"] for r in successful) / duration
        if duration
        else None,
        cache_hit_rate=sum(r["cached_tokens"] for r in successful)
        / sum(len(inputs[r["rid"]]["input_ids"]) for r in successful)
        if cache_available
        else None,
        send_lag_p99_ms=percentile([r["send_lag_ms"] for r in clients], 99),
        request_retractions=sum(r["retractions"] for r in server.values())
        if trace_available
        else None,
        export_error=run.get("export_error"),
        forced_stop=run.get("forced_stop", False),
    )
    meta_path = directory / "input.meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        result.update({key: meta[key] for key in ("workload", "rate", "seed")})
    scheduling = directory / "scheduling.csv"
    if scheduling.exists():
        with scheduling.open(encoding="utf-8", newline="") as f:
            rows = [
                r
                for r in csv.DictReader(f)
                if run.get("measurement_start_s", 0)
                <= float(r["start_s"])
                <= run.get("measurement_end_s", run["snapshot_s"])
            ]
        for kind in ("priority", "prefill_total"):
            group = [r for r in rows if r["kind"] == kind]
            result[kind + "_calls"] = len(group)
            for field in ("wall_ms", "cpu_ms", "scoring_wall_ms", "admission_wall_ms"):
                values = [float(r[field]) for r in group if r.get(field)]
                result[f"{kind}_{field}_p99"] = percentile(values, 99)
                result[f"{kind}_{field}_sum"] = sum(values)
        result["policy_fallback_calls"] = sum(
            r["kind"] == "priority" and r["policy"] != r["effective_policy"]
            for r in rows
        )
    write_json(directory / "summary.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("runs", type=Path, nargs="+")
    p.add_argument("--output", type=Path, default=Path("results/comparison.csv"))
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()
    rows = [summarize(d) for d in args.runs]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
        writer.writeheader()
        writer.writerows(rows)
    if args.plot:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        for ax, metric, label in zip(
            axes,
            ("short_ttft_p99_ms", "long_wait_max_ms", "output_tokens_per_s"),
            ("Short P99 TTFT (ms)", "Long max wait (ms)", "Output tokens/s"),
        ):
            ax.bar(
                range(len(rows)),
                [r[metric] if r[metric] is not None else np.nan for r in rows],
            )
            ax.set_xticks(
                range(len(rows)),
                [Path(r["run"]).name for r in rows],
                rotation=60,
                ha="right",
            )
            ax.set_ylabel(label)
        fig.tight_layout()
        fig.savefig(args.output.with_suffix(".png"), dpi=160)
        plt.close(fig)
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        for row in rows:
            if (
                row["long_wait_max_ms"] is not None
                and row["output_tokens_per_s"] is not None
            ):
                axes[0].scatter(row["long_wait_max_ms"], row["output_tokens_per_s"])
                axes[0].annotate(
                    Path(row["run"]).name,
                    (row["long_wait_max_ms"], row["output_tokens_per_s"]),
                    fontsize=7,
                )
            source = Path(row["run"]) / "scheduling.csv"
            if source.exists():
                run = json.loads(
                    (source.parent / "run.json").read_text(encoding="utf-8")
                )
                with source.open(encoding="utf-8", newline="") as f:
                    calls = [
                        r
                        for r in csv.DictReader(f)
                        if r["kind"] == "priority"
                        and run.get("measurement_start_s", 0)
                        <= float(r["start_s"])
                        <= run.get("measurement_end_s", run["snapshot_s"])
                    ]
                # 按队列长度区间聚合，避免把大量散点遮成一块。
                bins = {}
                for call in calls:
                    bucket = int(call["queue_len"]) // 16 * 16
                    bins.setdefault(bucket, []).append(float(call["cpu_ms"]))
                xs = sorted(bins)
                axes[1].plot(
                    xs,
                    [percentile(bins[x], 99) for x in xs],
                    marker=".",
                    label=f"{Path(row['run']).name} K={row['candidate_limit']}",
                )
        axes[0].set(xlabel="Long max wait (ms)", ylabel="Output tokens/s")
        axes[1].set(
            xlabel="Queue length (bin width 16)", ylabel="Priority CPU P99 (ms)"
        )
        if axes[1].lines:
            axes[1].legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(args.output.with_suffix(".tradeoff.png"), dpi=160)
        plt.close(fig)
    print(args.output)


if __name__ == "__main__":
    main()
