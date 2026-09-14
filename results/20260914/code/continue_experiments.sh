#!/usr/bin/env bash

set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DAY=${DAY:-20260911}
WAIT_PID=${WAIT_PID:-3912034}
OUT="$ROOT/results/$DAY"
RUNS="$ROOT/runs"
LOG="$RUNS/continue-experiments-$DAY.log"

mkdir -p "$OUT/raw" "$RUNS"
exec 9>"$RUNS/.continue-experiments.lock"
if ! flock -n 9; then
    echo "another continuation script is already running"
    exit 0
fi

exec >>"$LOG" 2>&1
cd "$ROOT"
source .venv/bin/activate
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

log() {
    echo "[$(date -Is)] $*" >&2
}

wait_for_existing_batch() {
    if ! [[ "$WAIT_PID" =~ ^[0-9]+$ ]] || ! kill -0 "$WAIT_PID" 2>/dev/null; then
        return
    fi
    log "waiting for existing batch pid=$WAIT_PID"
    while kill -0 "$WAIT_PID" 2>/dev/null; do
        sleep 60
    done
    log "existing batch exited"
}

wait_gpu() {
    while nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null \
        | awk 'NF {found=1} END {exit !found}'; do
        log "GPU is busy; waiting"
        sleep 30
    done
}

next_output() {
    local base="$1"
    local candidate="$base"
    local n=1
    while [[ -e "$RUNS/$candidate" ]]; do
        if [[ -f "$OUT/$candidate.csv" ]]; then
            echo "SKIP:$candidate"
            return
        fi
        candidate="${base}-retry${n}"
        n=$((n + 1))
    done
    echo "RUN:$candidate"
}

archive_run() {
    local run="$1"
    local archive="$OUT/raw/$run.tar.gz"
    if [[ -d "$RUNS/$run" && ! -e "$archive" ]]; then
        tar -czf "$archive" -C "$RUNS" "$run"
        log "ARCHIVE $archive"
    fi
}

run_case() {
    local run_base="$1"
    local policy="$2"
    local candidates="$3"
    local input="$4"
    local aging_ms="$5"
    local cost_model="${6:-}"
    local choice run

    choice=$(next_output "$run_base")
    if [[ "$choice" == SKIP:* ]]; then
        log "$choice"
        return 0
    fi
    run=${choice#RUN:}

    wait_gpu
    log "START $run policy=$policy candidates=$candidates input=$input aging_ms=$aging_ms"
    if [[ -n "$cost_model" ]]; then
        python -u experiments/run_case.py \
            --policy "$policy" --candidates "$candidates" --aging-ms "$aging_ms" \
            --cost-model "$cost_model" --port "$PORT" --input "$input" \
            --output "$RUNS/$run" --request-timeout 3600
    else
        python -u experiments/run_case.py \
            --policy "$policy" --candidates "$candidates" --aging-ms "$aging_ms" \
            --port "$PORT" --input "$input" --output "$RUNS/$run" \
            --request-timeout 3600
    fi
    local rc=$?
    log "RUN_EXIT=$rc $run"
    if [[ -f "$RUNS/$run/run.json" ]]; then
        python -u experiments/analyze.py "$RUNS/$run" \
            --output "$OUT/$run.csv" --plot
        log "ANALYZE_EXIT=$? $run"
        archive_run "$run"
    else
        log "NO_RUN_JSON $run"
    fi
    PORT=$((PORT + 1))
    return "$rc"
}

ensure_generated_workload() {
    local workload="$1"
    local count="$2"
    local rate="$3"
    local seed="$4"
    local input="$ROOT/workloads/${workload}-r${rate}-s${seed}-n${count}.jsonl"
    if [[ ! -f "$input" ]]; then
        log "GENERATE $input"
        python -u experiments/generate_workload.py --workload "$workload" \
            --count "$count" --rate "$rate" --seed "$seed" --output "$input"
    fi
    echo "$input"
}

wait_for_existing_batch

# Reconcile the complete main matrix. Existing successful rounds are skipped.
PORT=30101
MAIN_SPECS=(
    "r05 fcfs 64 1"
    "r05 lpm 64 1"
    "r05 dfs-weight 64 1"
    "r05 hrrn 64 1"
    "r05 short-remaining 0 1"
    "r05 fcfs 64 2"
    "r05 lpm 64 2"
    "r05 dfs-weight 64 2"
    "r05 hrrn 64 2"
    "r05 short-remaining 0 2"
    "r05 fcfs 64 3"
    "r05 lpm 64 3"
    "r05 dfs-weight 64 3"
    "r05 hrrn 64 3"
    "r05 short-remaining 0 3"
    "r1 fcfs 64 1"
    "r1 lpm 64 1"
    "r1 dfs-weight 64 1"
    "r1 hrrn 64 1"
    "r1 short-remaining 0 1"
    "r1 fcfs 64 2"
    "r1 lpm 64 2"
    "r1 dfs-weight 64 2"
    "r1 hrrn 64 2"
    "r1 short-remaining 0 2"
    "r1 fcfs 64 3"
    "r1 lpm 64 3"
    "r1 dfs-weight 64 3"
    "r1 hrrn 64 3"
    "r1 short-remaining 0 3"
)
for spec in "${MAIN_SPECS[@]}"; do
    read -r rate_tag policy candidates seed <<<"$spec"
    name="$policy"
    [[ "$policy" == short-remaining ]] && name=short-remaining-k0
    input="workloads/prefix-${rate_tag}-s${seed}-n600.jsonl"
    run_case "$DAY-main-prefix-${rate_tag}-s${seed}-${name}-n600" \
        "$policy" "$candidates" "$input" 500
done

# Compare cost and remaining-token ordering with a threshold above observed waits.
COST="$ROOT/results/20260910/calibration/a6000-cost-r1.json"
AGED_INPUT="workloads/prefix-r1-s2-n600.jsonl"
run_case "$DAY-aged-remaining-prefix-r1-s2-tau300000-n600" \
    aged-remaining 64  "$AGED_INPUT" 300000
run_case "$DAY-aged-cost-prefix-r1-s2-tau300000-n600" \
    aged-cost 64 "$AGED_INPUT" 300000 "$COST"

# Representative diagnostics for the three workloads not used in the main table.
for workload in hot-prefix long-wait burst-decode; do
    input=$(ensure_generated_workload "$workload" 300 1.0 1)
    run_case "$DAY-extra-${workload}-r1-s1-fcfs-n300" \
        fcfs 64 "$input" 500
    run_case "$DAY-extra-${workload}-r1-s1-short-remaining-k0-n300" \
        short-remaining 0 "$input" 500
done

# Normal-text functionality observation; it is excluded from synthetic metrics.
TEXT_INPUT="$ROOT/workloads/text-check.jsonl"
if [[ ! -f "$TEXT_INPUT" ]]; then
    python - <<'PY'
import json
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(
    "models/Qwen2.5-7B-Instruct", local_files_only=True
)
questions = [
    "Explain the difference between prefill and decode.",
    "Calculate 17 times 23 and show the steps.",
    "In three sentences, explain the purpose of prefix caching.",
]
with open("workloads/text-check.jsonl", "w", encoding="utf-8") as output:
    for index, question in enumerate(questions):
        input_ids = tokenizer.apply_chat_template(
            [{"role": "user", "content": question}],
            add_generation_prompt=True,
        )
        output.write(json.dumps({
            "rid": f"text-{index}",
            "arrival_s": index,
            "input_ids": input_ids,
            "max_new_tokens": 256,
            "ignore_eos": False,
        }) + "\n")
PY
fi
run_case "$DAY-text-fcfs" fcfs 64 "$TEXT_INPUT" 500
run_case "$DAY-text-short-remaining" short-remaining 0 "$TEXT_INPUT" 500

log "BATCH_COMPLETE"
