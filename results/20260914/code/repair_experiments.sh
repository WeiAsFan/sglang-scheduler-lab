#!/usr/bin/env bash

set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DAY=${DAY:-20260914}
OUT="$ROOT/results/$DAY"
RUNS="$ROOT/runs"
LOG="$RUNS/repair-experiments-$DAY.log"
PORT=${PORT:-30130}

mkdir -p "$OUT/raw" "$RUNS"
exec 9>"$RUNS/.repair-experiments.lock"
if ! flock -n 9; then
    echo "another repair script is already running"
    exit 0
fi

exec >>"$LOG" 2>&1
cd "$ROOT"
source .venv/bin/activate
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

log() {
    echo "[$(date -Is)] $*"
}

wait_gpu() {
    while nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null \
        | awk 'NF {found=1} END {exit !found}'; do
        log "GPU is busy; waiting"
        sleep 30
    done
}

run_one() {
    local run="$1"
    local policy="$2"
    local candidates="$3"
    local input="$4"
    local aging_ms="$5"

    if [[ -e "$RUNS/$run" ]]; then
        log "SKIP_EXISTS $run"
        return 0
    fi
    wait_gpu
    log "START $run policy=$policy candidates=$candidates input=$input aging_ms=$aging_ms port=$PORT"
    if python -u experiments/run_case.py \
        --policy "$policy" --candidates "$candidates" --aging-ms "$aging_ms" \
        --port "$PORT" --input "$input" --output "$RUNS/$run" \
        --request-timeout 3600; then
        rc=0
    else
        rc=$?
    fi
    log "RUN_EXIT=$rc $run"
    if [[ -f "$RUNS/$run/run.json" ]]; then
        python -u experiments/analyze.py "$RUNS/$run" \
            --output "$OUT/$run.csv" --plot
        log "ANALYZE_EXIT=$? $run"
        tar -czf "$OUT/raw/$run.tar.gz" -C "$RUNS" "$run"
        log "ARCHIVE $OUT/raw/$run.tar.gz"
    else
        log "NO_RUN_JSON $run"
    fi
    PORT=$((PORT + 1))
    return 0
}

# These are retries of the three already recorded failed main-comparison rounds.
run_one "$DAY-main-prefix-r05-s2-fcfs-n600-retry1" \
    fcfs 64 workloads/prefix-r05-s2-n600.jsonl 500
run_one "$DAY-main-prefix-r05-s3-lpm-n600-retry1" \
    lpm 64 workloads/prefix-r05-s3-n600.jsonl 500
run_one "$DAY-main-prefix-r05-s3-dfs-weight-n600-retry1" \
    dfs-weight 64 workloads/prefix-r05-s3-n600.jsonl 500

# The first FCFS retry retained one transient disconnected request. Retry the
# same documented case once more without changing its input or parameters.
run_one "$DAY-main-prefix-r05-s2-fcfs-n600-retry2" \
    fcfs 64 workloads/prefix-r05-s2-n600.jsonl 500

run_one "$DAY-main-prefix-r05-s2-fcfs-n600-retry3" \
    fcfs 64 workloads/prefix-r05-s2-n600.jsonl 500

# This follows the manual's normal-text observation. The environment returns a
# BatchEncoding here, so convert its input_ids field to a JSON list.
TEXT_INPUT="$ROOT/workloads/text-check.jsonl"
if [[ ! -s "$TEXT_INPUT" ]]; then
    python - <<'PY'
import json
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained(
    'models/Qwen2.5-7B-Instruct', local_files_only=True
)
questions = [
    '解释 prefill 与 decode 的区别。',
    '计算 17 乘以 23，并给出过程。',
    '用三句话说明前缀缓存的作用。',
]
with open('workloads/text-check.jsonl', 'w', encoding='utf-8') as f:
    for i, question in enumerate(questions):
        ids = tokenizer.apply_chat_template(
            [{'role': 'user', 'content': question}],
            add_generation_prompt=True,
        )
        if hasattr(ids, 'keys'):
            ids = ids['input_ids']
        ids = list(ids)
        f.write(json.dumps(
            dict(rid=f'text-{i}', arrival_s=i, input_ids=ids,
                 max_new_tokens=256, ignore_eos=False),
            ensure_ascii=False,
        ) + '\n')
PY
    log "GENERATED $TEXT_INPUT"
fi
run_one "$DAY-text-fcfs" fcfs 64 "$TEXT_INPUT" 500
run_one "$DAY-text-short-remaining" short-remaining 0 "$TEXT_INPUT" 500

cp configs/a6000.json "$OUT/config-used.json"
python -m pip freeze > "$OUT/environment-packages.txt"
if [[ -d upstream/sglang/.git ]]; then
    git -C upstream/sglang log -1 --oneline > "$OUT/server-source-commit.txt"
    git -C upstream/sglang diff > "$OUT/upstream-working.diff"
fi
git diff > "$OUT/project-working.diff"
log "BATCH_COMPLETE"
