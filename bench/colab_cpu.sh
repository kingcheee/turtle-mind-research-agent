#!/bin/bash
# Colab CPU 런타임을 「온프레미스 기기」 대역으로 쓰는 실측 (2026-09-27).
# 노트북과 같은 llama.cpp b10809 CPU 빌드 + 같은 Qwen2.5-1.5B Q4 + 같은 벤치(bench/run_bench.py, 정답지 앞 20건).
# ① 사양 ② llama-bench 스레드 스윕(1·2·4·…·nproc) ③ 스레드 수별 파이프라인 벤치(문서당 초·필드 정확도).
# VM에서 백그라운드로 돌린다: LABEL=Colab-CPU THREADS="2" bash /content/colab_cpu.sh  → 로그 /content/cpu.log
# 결과 JSON은 /content/mvp/bench/results/ — 로컬 bench/results/로 내려받으면 /bench 표에 뜬다.
exec > /content/cpu.log 2>&1
cd /content
B=b10809
LABEL="${LABEL:-Colab-CPU}"
N=$(nproc)
THREADS="${THREADS:-$N}"
CASES="${CASES:-20}"
export TZ=Asia/Seoul

echo "== SYSTEM $(date +%FT%T%z)"
lscpu | grep -E '^(Model name|CPU\(s\)|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\)|L3 cache|CPU max MHz)'
echo "flags: $(grep -o -w -E 'avx2|avx512f|avx512_vnni|avx_vnni|amx_int8|amx_tile' /proc/cpuinfo | sort -u | tr '\n' ' ')"
free -h | head -2; df -h /content | tail -1; grep PRETTY /etc/os-release; python3 -V

echo "== SETUP"
t0=$(date +%s)
curl -fsSL --retry 3 -o llama.tgz "https://github.com/ggml-org/llama.cpp/releases/download/$B/llama-$B-bin-ubuntu-x64.tar.gz" || { echo "llama.cpp download FAILED"; exit 1; }
mkdir -p llama && tar xzf llama.tgz -C llama
BIN=$(dirname "$(find /content/llama -name llama-server -type f | head -1)")
[ -f qwen.gguf ] || curl -fsSL --retry 3 -o qwen.gguf https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf || { echo "model download FAILED"; exit 1; }
mkdir -p mvp && tar xzf mvp-bundle.tgz -C mvp
pip -q install httpx
echo "setup: $(( $(date +%s)-t0 ))s  bin=$BIN  model=$(du -h qwen.gguf | cut -f1)"
"$BIN/llama-server" --version 2>&1 | tail -2

SWEEP=1; t=2; while [ $t -lt "$N" ]; do SWEEP="$SWEEP,$t"; t=$((t*2)); done; [ "$N" -gt 1 ] && SWEEP="$SWEEP,$N"
# ⚠ TPU v5e1 호스트는 vCPU 24개로 보이지만 cgroup cpu.max가 4 CPU 분이라 4스레드가 정점이다(09-27 실측) — 할당량을 같이 적는다
echo "cgroup cpu.max: $(cat /sys/fs/cgroup/cpu.max 2>/dev/null)"
if [ -z "${SKIP_SWEEP:-}" ]; then
  echo "== LLAMA-BENCH threads=$SWEEP"
  "$BIN/llama-bench" -m qwen.gguf -p 512 -n 128 -t "$SWEEP" -r 2 -o md
fi

CPU=$(lscpu | sed -n 's/^Model name: *//p' | head -1)
for T in $THREADS; do
  echo "== PIPELINE threads=$T cases=$CASES"
  "$BIN/llama-server" -m qwen.gguf --port 8097 -c 2048 -t "$T" --host 127.0.0.1 > "srv-t$T.log" 2>&1 &
  SRV=$!
  for i in $(seq 1 120); do curl -s localhost:8097/health | grep -q '"ok"' && break; sleep 1; done
  (cd mvp && python3 bench/run_bench.py --host "$LABEL-t$T" --url http://127.0.0.1:8097 --n "$CASES")
  kill $SRV; wait $SRV 2>/dev/null
  # 결과 JSON에 CPU·스레드·vCPU를 덧붙인다(/bench 표는 host 이름만 쓰고, 보고서가 이 필드를 읽는다)
  f=$(ls -t mvp/bench/results/"$LABEL-t$T"-*.json | head -1)
  python3 - "$f" "$CPU" "$T" "$N" <<'PY'
import json, sys
p, cpu, t, n = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
d = json.load(open(p, encoding="utf-8"))
d.update(cpu=cpu, threads=t, vcpu=n, llama_cpp="b10809 CPU")
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY
done
echo "== DONE $(date +%FT%T%z)"
