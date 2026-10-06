from __future__ import annotations
import argparse
import concurrent.futures
import statistics
import time
import urllib.request


def hit(url: str, timeout: float) -> tuple[float, int]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            return (time.perf_counter() - started) * 1000, response.status
    except Exception:
        return (time.perf_counter() - started) * 1000, 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--max-p95-ms", type=float, required=True)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    args = parser.parse_args()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda _: hit(args.url, args.timeout), range(args.requests)))
    latencies = sorted(ms for ms, _ in results)
    errors = sum(1 for _, status in results if not 200 <= status < 400)
    p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)]
    error_rate = errors / len(results)
    print(f"requests={len(results)} p50_ms={statistics.median(latencies):.2f} p95_ms={p95:.2f} error_rate={error_rate:.4f}")
    return 0 if p95 <= args.max_p95_ms and error_rate <= args.max_error_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
