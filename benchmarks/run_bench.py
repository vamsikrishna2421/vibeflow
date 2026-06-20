"""Benchmark local LLMs on dictation cleanup + structuring.

Runs every case in cases.py through every available model in MODELS, recording
latency and the produced output. Writes results.json (machine-readable) and
results.md (human-readable, side-by-side) into this folder.

    python benchmarks/run_bench.py
"""

import json
import os
import time
import urllib.request

from cases import CASES

ENDPOINT = "http://127.0.0.1:11434"

SYSTEM = (
    "You are a dictation cleanup assistant. Rewrite the user's raw dictated text "
    "into clean, correct written English. Fix grammar, punctuation, "
    "capitalization, and remove filler words and false starts. Preserve the "
    "original meaning and intent. If the text expresses multiple distinct points "
    "or steps, format them as a bulleted or numbered list; otherwise return clean "
    "prose. Output ONLY the cleaned text - no preamble, commentary, or quotes."
)

# Candidate small, CPU-friendly models. Only those actually pulled are run.
MODELS = [
    "llama3.2:1b",
    "qwen2.5:1.5b",
    "gemma2:2b",
    "llama3.2:3b",
    "qwen2.5:3b",
    "phi3.5",
    "phi3:latest",
]
# Excluded: qwen3.6 (36B, far too slow on CPU) and qwen2.5-coder:7b (a coding
# model, not suited to prose formatting).

# On-disk sizes (from `ollama list`) for the comparison table.
SIZES = {
    "llama3.2:1b": "1.3 GB",
    "qwen2.5:1.5b": "1.0 GB",
    "gemma2:2b": "1.6 GB",
    "llama3.2:3b": "2.0 GB",
    "qwen2.5:3b": "1.9 GB",
    "phi3.5:latest": "2.2 GB",
    "phi3:latest": "2.2 GB",
}

HERE = os.path.dirname(os.path.abspath(__file__))


def _post(path, payload, timeout=240):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _available():
    with urllib.request.urlopen(ENDPOINT + "/api/tags", timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return [m["name"] for m in body.get("models", [])]


def run_model(model):
    rows = []
    for case in CASES:
        prompt = f"{SYSTEM}\n\nRaw text:\n{case['raw']}\n\nCleaned text:"
        t0 = time.time()
        try:
            resp = _post(
                "/api/generate",
                {"model": model, "prompt": prompt, "stream": False,
                 "options": {"temperature": 0.2}},
            )
            secs = time.time() - t0
            eval_count = resp.get("eval_count") or 0
            eval_dur = (resp.get("eval_duration") or 1) / 1e9
            rows.append({
                "id": case["id"], "expect": case["expect"], "raw": case["raw"],
                "output": (resp.get("response") or "").strip(),
                "seconds": round(secs, 2),
                "tokens": eval_count,
                "tok_per_s": round(eval_count / eval_dur, 1) if eval_dur else 0,
            })
            print(f"  [{model}] case {case['id']:>2}: {secs:5.1f}s", flush=True)
        except Exception as exc:
            rows.append({"id": case["id"], "error": str(exc)})
            print(f"  [{model}] case {case['id']:>2}: ERROR {exc}", flush=True)
    return rows


def write_markdown(results):
    lines = ["# VibeFlow local-LLM benchmark results\n"]
    # latency summary
    lines.append("## Latency summary\n")
    lines.append("| Model | Size | cases | avg s | median s | max s | avg tok/s |")
    lines.append("|---|---|---|---|---|---|---|")
    for model, rows in results.items():
        times = sorted(r["seconds"] for r in rows if "seconds" in r)
        toks = [r["tok_per_s"] for r in rows if r.get("tok_per_s")]
        size = SIZES.get(model, "?")
        if not times:
            lines.append(f"| {model} | {size} | 0 | - | - | - | - |")
            continue
        avg = sum(times) / len(times)
        med = times[len(times) // 2]
        lines.append(
            f"| {model} | {size} | {len(times)} | {avg:.1f} | {med:.1f} | "
            f"{max(times):.1f} | {(sum(toks)/len(toks) if toks else 0):.0f} |"
        )
    lines.append("")
    # per-case outputs
    lines.append("## Outputs by case\n")
    for case in CASES:
        lines.append(f"### Case {case['id']} — _expect: {case['expect']}_\n")
        lines.append(f"**Raw:** {case['raw']}\n")
        for model, rows in results.items():
            row = next((r for r in rows if r["id"] == case["id"]), None)
            if not row:
                continue
            if "error" in row:
                lines.append(f"**{model}** — ERROR: {row['error']}\n")
            else:
                out = row["output"].replace("\n", "\n> ")
                lines.append(f"**{model}** ({row['seconds']}s):\n> {out}\n")
        lines.append("---\n")
    with open(os.path.join(HERE, "results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    avail = _available()
    print("available models:", avail)
    models = []
    for m in MODELS:
        if m in avail:
            models.append(m)
        elif m + ":latest" in avail:  # e.g. "phi3.5" -> "phi3.5:latest"
            models.append(m + ":latest")
    print("benchmarking:", models)
    results = {}
    for model in models:
        print(f"=== {model} ===", flush=True)
        try:  # warm-up / load into memory
            _post("/api/generate", {"model": model, "prompt": "ok", "stream": False})
        except Exception:
            pass
        results[model] = run_model(model)
        # incremental save so partial results survive an interruption
        with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        write_markdown(results)
    print("DONE -> benchmarks/results.json + results.md")


if __name__ == "__main__":
    main()
