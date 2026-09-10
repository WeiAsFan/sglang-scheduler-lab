"""独立单请求标定与非负成本模型拟合。"""

import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path

from common import read_jsonl, write_json, write_jsonl
from replay import request


async def collect(session, url, directory, samples):
    rng = random.Random(17)
    rows, clients = [], []
    try:
        for hi, hit in enumerate((0, 1024, 8192, 12288)):
            for ri, remaining in enumerate((128, 512, 1024, 4096)):
                for sample in range(-2, samples):
                    # 每次清缓存和重建前缀都位于被测请求之外。
                    async with session.post(
                        url + "/flush_cache?timeout=60"
                    ) as response:
                        response.raise_for_status()
                    prefix = [rng.randrange(1000, 30000) for _ in range(hit)]
                    if hit:
                        warm = dict(
                            rid=f"cal-warm-{hi}-{ri}-{sample}",
                            input_ids=prefix,
                            max_new_tokens=1,
                        )
                        result = await request(
                            session, url, warm, time.perf_counter(), 600
                        )
                        if not result["success"]:
                            raise RuntimeError("标定前缀预热失败")
                    rid = f"cal-{hi}-{ri}-{sample}"
                    row = dict(
                        rid=rid,
                        input_ids=prefix
                        + [rng.randrange(1000, 30000) for _ in range(remaining)],
                        max_new_tokens=1,
                        target_hit=hit,
                        target_remaining=remaining,
                        sample=sample,
                        split="holdout" if (hi + ri) % 4 == 0 else "train",
                    )
                    rows.append(row)
                    result = await request(session, url, row, time.perf_counter(), 600)
                    clients.append(result)
                    if not result["success"]:
                        raise RuntimeError(f"标定请求失败：{rid}")
    finally:
        write_jsonl(directory / "calibration-input.jsonl", rows)
        write_jsonl(directory / "calibration-client.jsonl", clients)


def fit(directory, output):
    import numpy as np
    from scipy.optimize import nnls
    from scipy.stats import spearmanr

    chunks = defaultdict(list)
    for row in read_jsonl(directory / "gpu.jsonl"):
        chunks[row["rid"]].append(row)
    data = []
    for row in read_jsonl(directory / "calibration-input.jsonl"):
        if row["sample"] < 0:
            continue
        parts = chunks[row["rid"]]
        if not parts:
            raise ValueError(f"缺少 GPU 记录：{row['rid']}")
        hit = parts[0]["hit"]
        remaining = sum(p["remaining"] for p in parts)
        if hit + remaining != len(row["input_ids"]):
            raise ValueError(f"分块记录未覆盖完整输入：{row['rid']}")
        data.append(
            dict(
                rid=row["rid"],
                hit=hit,
                remaining=remaining,
                gpu_ms=sum(p["gpu_ms"] for p in parts),
                split=row["split"],
            )
        )
    train = [r for r in data if r["split"] == "train"]
    holdout = [r for r in data if r["split"] == "holdout"]
    if not train or not holdout:
        raise ValueError("需要训练组合与独立留出组合")
    features = lambda rows: np.array(
        [
            [
                1,
                r["remaining"],
                r["hit"] * r["remaining"] + r["remaining"] * (r["remaining"] + 1) / 2,
            ]
            for r in rows
        ],
        dtype=float,
    )
    x = features(train)
    scale = np.maximum(np.linalg.norm(x, axis=0), 1)
    beta_scaled, _ = nnls(x / scale, np.array([r["gpu_ms"] for r in train]))
    beta = beta_scaled / scale
    predicted = features(holdout) @ beta
    actual = np.array([r["gpu_ms"] for r in holdout])
    rho = float(spearmanr(predicted, actual).statistic)
    record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    model = dict(
        beta=beta.tolist(),
        unit="ms",
        formula="b0+b1*R+b2*(H*R+R*(R+1)/2)",
        config=record["config"],
        source_run=str(directory),
        train_samples=len(train),
        holdout_samples=len(holdout),
        holdout_mae_ms=float(np.mean(np.abs(predicted - actual))),
        holdout_spearman=rho if np.isfinite(rho) else None,
        timing="CUDA events around ModelRunner.forward; isolated; overlap disabled",
    )
    write_json(output, model)
    write_jsonl(output.with_suffix(".samples.jsonl"), data)
    print(json.dumps(model, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    fit(args.run, args.output)


if __name__ == "__main__":
    main()
