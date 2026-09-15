"""验证轻量导出保留失败与缺失语义，并正确处理计时窗口。"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
from common import read_jsonl, write_json, write_jsonl
from export_evidence import export


class EvidenceTests(unittest.TestCase):
    def test_request_join_keeps_failures_and_missing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            run.mkdir()
            write_jsonl(
                run / "input.jsonl",
                [
                    {"rid": rid, "input_ids": [1, 2], "arrival_s": i}
                    for i, rid in enumerate(("ok", "bad", "missing"))
                ],
            )
            write_jsonl(
                run / "client.jsonl",
                [
                    {"rid": "ok", "success": True, "ttft_ms": 25, "text": "正常回答"},
                    {
                        "rid": "bad",
                        "success": False,
                        "error": "ServerDisconnectedError",
                    },
                    {"rid": "warmup", "success": True},
                ],
            )
            write_jsonl(
                run / "server-requests.jsonl",
                [
                    {"rid": "ok", "first_enqueue_s": 10, "first_admit_s": 10.5},
                ],
            )
            (run / "server.log").write_text(
                "before\nerror bad\nafter\n", encoding="utf-8"
            )
            before = (run / "input.jsonl").read_bytes()
            out = export(run, root / "out")
            rows = read_jsonl(out / "requests.jsonl")
            self.assertEqual([r["rid"] for r in rows], ["ok", "bad", "missing"])
            self.assertEqual(rows[0]["first_wait_ms"], 500)
            self.assertEqual(rows[0]["input_tokens"], 2)
            self.assertNotIn("input_ids", rows[0])
            self.assertNotIn("text", rows[0])
            self.assertFalse(rows[1]["server_record_present"])
            self.assertIsNone(rows[1]["first_admit_s"])
            self.assertFalse(rows[2]["client_record_present"])
            self.assertIsNone(rows[2]["success"])
            self.assertEqual(len(read_jsonl(out / "failed-requests.jsonl")), 2)
            self.assertIn(
                "error bad", (out / "log-excerpts.txt").read_text(encoding="utf-8")
            )
            export(run, root / "out", include_text=True)
            self.assertEqual(read_jsonl(out / "requests.jsonl")[0]["text"], "正常回答")
            self.assertEqual((run / "input.jsonl").read_bytes(), before)

    def test_window_and_nested_timing_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            run.mkdir()
            write_json(
                run / "run.json", {"measurement_start_s": 10, "measurement_end_s": 20}
            )
            rows = [
                {"kind": "candidates", "start_s": 9, "aged": 99},
                {"kind": "candidates", "start_s": 10, "aged": 0, "candidates": 32},
                {"kind": "candidates", "start_s": 15, "aged": 2, "candidates": 32},
                {
                    "kind": "priority",
                    "start_s": 15,
                    "cpu_ms": 2,
                    "policy": "hrrn",
                    "effective_policy": "fcfs",
                },
                {"kind": "prefill_total", "start_s": 15, "cpu_ms": 5},
                {"kind": "candidates", "start_s": 21, "aged": 99},
            ]
            with (run / "scheduling.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=sorted({k for r in rows for k in r})
                )
                writer.writeheader()
                writer.writerows(rows)
            out = export(run, root / "out")
            result = json.loads((out / "scheduling-summary.json").read_text())
            self.assertEqual(result["aged_call_fraction"], 0.5)
            self.assertEqual(result["metrics"]["candidates"]["aged"]["max"], 2)
            self.assertEqual(result["metrics"]["candidates"]["aged"]["p99"], 1.98)
            self.assertEqual(result["calls"]["policy_fallback_calls"], 1)
            self.assertEqual(result["metrics"]["priority"]["cpu_ms"]["sum"], 2)
            self.assertEqual(result["metrics"]["prefill_total"]["cpu_ms"]["sum"], 5)
            timeline = read_jsonl(out / "scheduling-timeline.jsonl")
            self.assertIsNone(
                next(r for r in timeline if r["kind"] == "candidates")["cpu_ms_sum"]
            )

    def test_startup_failure_and_calibration_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "startup-failure"
            run.mkdir()
            out = export(run, root / "out")
            info = json.loads((out / "export-info.json").read_text(encoding="utf-8"))
            schedule = json.loads((out / "scheduling-summary.json").read_text())
            self.assertFalse(info["input_present"])
            self.assertFalse(info["client_present"])
            self.assertFalse(schedule["available"])
            self.assertIsNone(schedule["aged_call_fraction"])
            self.assertEqual(read_jsonl(out / "requests.jsonl"), [])
            write_jsonl(
                run / "calibration-input.jsonl", [{"rid": "cal", "input_ids": [3]}]
            )
            write_jsonl(
                run / "calibration-client.jsonl", [{"rid": "cal", "success": True}]
            )
            export(run, root / "out")
            self.assertEqual(read_jsonl(out / "requests.jsonl")[0]["rid"], "cal")


if __name__ == "__main__":
    unittest.main()
