"""生成固定 token 与开放到达轨迹；token 范围适用于默认 Qwen 模型。"""

import argparse
import random
from pathlib import Path

from common import write_json, write_jsonl

WORKLOADS = (
    "mixed-low-reuse",
    "prefix-conflict",
    "hot-prefix",
    "long-wait",
    "burst-decode",
)


def generate(name, count, rate, seed):
    rng = random.Random(seed)
    tokens = lambda n: [rng.randrange(1000, 30000) for _ in range(n)]
    prefixes = {"a": tokens(12288), "b": tokens(1024), "c": tokens(1024)}
    prefixes.update({f"hot{i}": tokens(4096) for i in range(4)})
    rows, used, arrival = [], set(), 0.0
    identifiers = list(range(count))
    random.Random(seed + 100003).shuffle(identifiers)
    for i in range(count):
        group, output = None, 128
        length = (
            rng.choice((512, 1024, 2048))
            if rng.random() < 0.8
            else rng.choice((8192, 16384))
        )
        if name == "prefix-conflict":
            group, length = rng.choice((("a", 16384), ("b", 2048), ("c", 16384)))
        elif name == "hot-prefix" and rng.random() < 0.8:
            group, length = f"hot{rng.randrange(4)}", rng.choice((4608, 5120, 8192))
        elif name == "long-wait":
            length = 16384 if i % 20 == 0 else rng.choice((512, 1024, 2048))
        elif name == "burst-decode":
            output = rng.choice((128, 128, 512, 1024))
        prefix = prefixes[group] if group else []
        ids = prefix + tokens(length - len(prefix))
        if group:
            used.add(group)
        if i:
            arrival += rng.expovariate(rate)
        planned = (i // 160) * (160 / rate) if name == "burst-decode" else arrival
        rows.append(
            dict(
                rid=f"r{identifiers[i]:07d}",
                arrival_s=planned,
                input_ids=ids,
                max_new_tokens=output,
                group=group or "independent",
            )
        )
    # 完整前缀作为独立请求预热；实际命中依然从引擎测量。
    warm = [
        dict(rid=f"warm-{g}", arrival_s=0, input_ids=prefixes[g], max_new_tokens=1)
        for g in sorted(used)
    ]
    return rows, warm


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workload", choices=WORKLOADS, required=True)
    p.add_argument("--count", type=int, default=3000)
    p.add_argument("--rate", type=float, required=True)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.count <= 0 or args.rate <= 0:
        p.error("count 和 rate 必须大于 0")
    rows, warm = generate(args.workload, args.count, args.rate, args.seed)
    write_jsonl(args.output, rows)
    write_jsonl(args.output.with_suffix(".warmup.jsonl"), warm)
    write_json(
        args.output.with_suffix(".meta.json"),
        dict(
            workload=args.workload,
            count=args.count,
            rate=args.rate,
            seed=args.seed,
            token_range=[1000, 29999],
            model="Qwen/Qwen2.5-7B-Instruct",
        ),
    )


if __name__ == "__main__":
    main()
