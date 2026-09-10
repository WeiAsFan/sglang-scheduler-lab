"""CPU 上验证排序边界、真实 SSE 解析及统计分母，不模拟 GPU 性能。"""

import importlib.util
import ast
from enum import Enum
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from common import write_json, write_jsonl
from generate_workload import generate
from analyze import summarize
from replay import replay

BASE = (ROOT / "patches/upstream-base.txt").read_text().strip()
MODULE = (
    ROOT / "upstream" / f"sglang-{BASE}" / "python/sglang/srt/managers/scheduler_lab.py"
)
if not MODULE.exists():
    MODULE = ROOT / "upstream/sglang/python/sglang/srt/managers/scheduler_lab.py"
spec = importlib.util.spec_from_file_location("scheduler_lab", MODULE)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def req(seq, length, hit=0, entered=10, output=0):
    return SimpleNamespace(
        rid=str(seq),
        lab_arrival_seq=seq,
        time_stats=SimpleNamespace(wait_queue_entry_time=entered),
        origin_input_ids=[0] * length,
        output_ids=[0] * output,
        hit=hit,
        _compute_max_prefix_len=lambda n: max(0, n - 1),
    )


class PolicyTests(unittest.TestCase):
    def test_actual_upstream_dispatch_preserves_native_fallback(self):
        source = MODULE.with_name("schedule_policy.py").read_text(encoding="utf-8")
        nodes = [
            n
            for n in ast.parse(source).body
            if isinstance(n, ast.ClassDef)
            and n.name in ("CacheAwarePolicy", "CacheAgnosticPolicy", "SchedulePolicy")
        ]
        config = SimpleNamespace(
            schedule_trace_dir=None,
            schedule_candidate_limit=1,
            schedule_aging_threshold_ms=500,
            schedule_cost_model=None,
        )
        matches = []

        def match(cache, r, **kwargs):
            matches.append(r.rid)
            r.prefix_indices = [0] * r.hit

        ns = dict(
            Enum=Enum,
            Union=__import__("typing").Union,
            POLICIES=lab.POLICIES,
            RemainingPolicy=lab.RemainingPolicy,
            trace=lab.trace,
            measured=lab.measured,
            get_schedule=lambda: config,
            match_prefix_for_req=match,
            get_disagg=lambda: SimpleNamespace(disaggregation_mode="null"),
            RadixCache=SimpleNamespace(create_simulated=lambda: None),
        )
        exec(
            "from __future__ import annotations\n"
            + "\n".join(ast.unparse(n) for n in nodes),
            ns,
        )
        cache = SimpleNamespace(disable=False, supports_fast_match_prefix=lambda: True)
        make = lambda name: ns["SchedulePolicy"](name, cache, False, False, False)
        queue = [req(1, 20), req(0, 10)]
        policy = make("short-remaining")
        policy.calc_priority(queue)
        self.assertEqual(matches, ["0"])
        self.assertFalse(policy.waiting_queue_prefix_matched(queue))
        cache.disable = True
        policy = make("short-remaining")
        matches.clear()
        policy.calc_priority(queue)
        self.assertEqual(matches, [])
        self.assertEqual(policy.policy.value, "short-remaining")
        cache.disable = False
        queue = [req(i, 10) for i in range(129)]
        for name in ("lpm", "hrrn"):
            policy = make(name)
            policy.calc_priority(queue)
            self.assertEqual(policy._determine_active_policy(queue).value, "fcfs")
            self.assertEqual([r.rid for r in queue], [str(i) for i in range(129)])

    def test_input_and_remaining_diverge(self):
        a, b, c = req(0, 16000, 12000), req(1, 2000, 1000), req(2, 16000, 15500)
        q = [a, b, c]
        lab.RemainingPolicy("short-input", 0).order(
            q, lambda r: self.fail("输入排序不应匹配"), 10
        )
        self.assertEqual([r.rid for r in q], ["1", "0", "2"])
        lab.RemainingPolicy("short-remaining", 0).order(q, lambda r: r.hit, 10)
        self.assertEqual([r.rid for r in q], ["2", "1", "0"])

    def test_bounded_candidates_use_arrival_not_current_position(self):
        q = [req(3, 1), req(2, 1), req(1, 20), req(0, 10)]
        seen = []
        lab.RemainingPolicy("short-remaining", 2).order(
            q, lambda r: seen.append(r.rid) or 0, 10
        )
        self.assertEqual(seen, ["0", "1"])
        self.assertEqual([r.rid for r in q], ["0", "1", "3", "2"])

    def test_all_aged_escape_candidate_limit_and_no_scoring(self):
        q = [
            req(3, 1),
            req(2, 10, entered=9),
            req(1, 10, entered=9.5),
            req(0, 10, entered=9),
        ]
        seen = []
        lab.RemainingPolicy("aged-remaining", 1, 500).order(
            q, lambda r: seen.append(r.rid) or 0, 10
        )
        self.assertEqual([r.rid for r in q], ["0", "1", "2", "3"])
        self.assertEqual(seen, ["3"])

    def test_last_token_and_retracted_output_are_work(self):
        q = [req(0, 10, hit=10), req(1, 10, hit=10, output=5)]
        lab.RemainingPolicy("short-remaining", 0).order(q, lambda r: r.hit, 10)
        self.assertEqual([r.rid for r in q], ["0", "1"])

    def test_cost_model_changes_order_and_requires_file(self):
        with self.assertRaises(ValueError):
            lab.RemainingPolicy("aged-cost")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "model.json"
            write_json(path, dict(beta=[0, 0, 1], unit="ms"))
            q = [req(0, 110, 100), req(1, 20, 0)]
            lab.RemainingPolicy("aged-cost", 0, 500, path).order(q, lambda r: r.hit, 10)
            self.assertEqual([r.rid for r in q], ["1", "0"])

    def test_reentry_preserves_first_wait(self):
        t = lab.Trace()
        t.directory = "unused"
        r = req(0, 10)
        t.enqueue(r, False)
        t.admit([r])
        first = t.requests[r.rid].copy()
        sequence = r.lab_arrival_seq
        t.enqueue(r, True)
        t.admit([r])
        self.assertGreater(r.lab_arrival_seq, sequence)
        self.assertEqual(t.requests[r.rid]["first_enqueue_s"], first["first_enqueue_s"])
        self.assertEqual(t.requests[r.rid]["first_admit_s"], first["first_admit_s"])
        self.assertEqual(t.requests[r.rid]["retractions"], 1)

    def test_workload_reproducible_and_conflicting(self):
        rows, warm = generate("prefix-conflict", 30, 5, 8)
        self.assertEqual((rows, warm), generate("prefix-conflict", 30, 5, 8))
        self.assertEqual({r["group"] for r in rows}, {"a", "b", "c"})
        self.assertEqual(len({r["rid"] for r in rows}), 30)


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_event_does_not_count_as_first_token_and_abort_fails(self):
        from aiohttp import web

        async def serve(request):
            payload = await request.json()
            response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            events = [
                dict(meta_info=dict(completion_tokens=0)),
                dict(
                    text="ok",
                    meta_info=dict(
                        completion_tokens=1,
                        cached_tokens=3,
                        finish_reason=dict(
                            type="abort" if payload["rid"] == "bad" else "length"
                        ),
                    ),
                ),
            ]
            for event in events:
                raw = ("data: " + json.dumps(event) + "\n\n").encode()
                await response.write(raw[:7])
                await response.write(raw[7:])
            await response.write(b"data: [DONE]\n\n")
            await response.write_eof()
            return response

        app = web.Application()
        app.router.add_post("/generate", serve)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            with tempfile.TemporaryDirectory() as d:
                rows = [
                    dict(rid=rid, input_ids=[1000] * 4, max_new_tokens=1, arrival_s=0)
                    for rid in ("ok", "bad")
                ]
                results = await replay(
                    rows, f"http://127.0.0.1:{port}", Path(d) / "client.jsonl"
                )
                self.assertTrue(results[0]["success"])
                self.assertFalse(results[1]["success"])
                self.assertEqual(results[0]["cached_tokens"], 3)
                self.assertGreater(results[0]["ttft_ms"], 0)
        finally:
            await runner.cleanup()


class AnalysisTests(unittest.TestCase):
    def test_calibration_fit_uses_context_interaction(self):
        import contextlib
        import io
        from calibrate import fit

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            inputs = []
            gpu = []
            for hi, h in enumerate((0, 1024, 8192, 12288)):
                for ri, r in enumerate((128, 512, 1024, 4096)):
                    rid = f"{hi}-{ri}"
                    inputs.append(
                        dict(
                            rid=rid,
                            input_ids=[1] * (h + r),
                            sample=0,
                            split="holdout" if (hi + ri) % 4 == 0 else "train",
                        )
                    )
                    gpu.append(
                        dict(
                            rid=rid,
                            hit=h,
                            remaining=r,
                            gpu_ms=0.5 + 0.001 * r + 1e-7 * (h * r + r * (r + 1) / 2),
                        )
                    )
            write_jsonl(d / "calibration-input.jsonl", inputs)
            write_jsonl(d / "gpu.jsonl", gpu)
            write_json(d / "run.json", dict(config={}))
            with contextlib.redirect_stdout(io.StringIO()):
                fit(d, d / "model.json")
            model = json.loads((d / "model.json").read_text(encoding="utf-8"))
            self.assertEqual(model["train_samples"], 12)
            self.assertEqual(model["holdout_samples"], 4)
            for a, b in zip(model["beta"], (0.5, 0.001, 1e-7)):
                self.assertAlmostEqual(a, b, places=9)

    def test_failed_and_unadmitted_are_not_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_json(
                d / "run.json",
                dict(
                    config=dict(schedule_policy="fcfs"), status="failed", snapshot_s=20
                ),
            )
            write_jsonl(
                d / "input.jsonl",
                [
                    dict(rid="a", input_ids=[1] * 100),
                    dict(rid="b", input_ids=[1] * 8192),
                ],
            )
            write_jsonl(
                d / "client.jsonl",
                [
                    dict(
                        rid="a",
                        success=True,
                        ttft_ms=5,
                        cached_tokens=50,
                        output_tokens=2,
                        send_s=10,
                        end_s=12,
                        send_lag_ms=0,
                    ),
                    dict(rid="b", success=False, send_s=10, end_s=15, send_lag_ms=1),
                ],
            )
            write_jsonl(
                d / "server-requests.jsonl",
                [dict(rid="b", first_enqueue_s=11, first_admit_s=None, retractions=0)],
            )
            write_json(d / "server-trace.json", dict(snapshot_s=21))
            result = summarize(d)
            self.assertEqual(result["cache_hit_rate"], 0.5)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(result["long_not_admitted"], 1)
            self.assertEqual(result["long_wait_lower_bound_max_ms"], 10000)
            self.assertEqual(result["requests_per_s"], 0.2)


if __name__ == "__main__":
    unittest.main()
