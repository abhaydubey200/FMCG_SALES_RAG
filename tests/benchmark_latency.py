import requests, time, statistics

queries = [
    ("What is total revenue?", "analytical"),
    ("Show revenue by region", "analytical"),
    ("What is total marketing spend?", "analytical"),
    ("Show revenue trend", "analytical"),
    ("What is the trade promotion discount limit?", "knowledge"),
    ("What percentage of packaging should be recyclable?", "knowledge"),
    ("How is the product doing?", "ambiguous"),
    ("Compare performance across datasets", "analytical"),
    ("What are our top products by revenue?", "analytical"),
    ("Show revenue by category", "analytical"),
]

results = []
cache_results = []
print("=" * 70)
print("QUERYBRIDGE LATENCY BENCHMARK — 10 QUERIES")
print("TARGET: p50 < 5s, p95 < 10s (Groq + caching)")
print("=" * 70)

# First pass: cold cache
print("\n--- COLD CACHE (first query for each) ---\n")
for i, (q, expected_type) in enumerate(queries, 1):
    start = time.time()
    try:
        r = requests.post("http://localhost:8000/api/ai/query",
            json={"question": q}, timeout=60)
        elapsed = time.time() - start
        data = r.json()
        status = "OK" if r.status_code == 200 else str(r.status_code)
        answer_len = len(data.get("answer", ""))
        has_numbers = any(c.isdigit() for c in data.get("answer", ""))
        cache_hit = data.get("metrics", {}).get("cache_hit", False)
        results.append(elapsed)
        label = "COLD" if not cache_hit else "WARM"
        print("{:<3} {:<12} {:>7.1f}s {:>6} {:>5}  {}".format(
            i, expected_type, elapsed, status, label, q[:50]))
        print("    {} chars, numbers={}, answer: {}...".format(
            answer_len, has_numbers, data.get("answer", "")[:100]))
    except Exception as e:
        elapsed = time.time() - start
        results.append(elapsed)
        print("{:<3} {:<12} {:>7.1f}s  ERROR  {}".format(
            i, expected_type, elapsed, q[:50]))
        print("    {}".format(str(e)[:100]))
    print()

# Second pass: warm cache (same queries)
print("\n--- WARM CACHE (cached results) ---\n")
for i, (q, expected_type) in enumerate(queries, 1):
    start = time.time()
    try:
        r = requests.post("http://localhost:8000/api/ai/query",
            json={"question": q}, timeout=60)
        elapsed = time.time() - start
        data = r.json()
        cache_hit = data.get("metrics", {}).get("cache_hit", False)
        cache_results.append(elapsed)
        label = "CACHE" if cache_hit else "MISS"
        print("{:<3} {:<12} {:>7.3f}s {:>5}  {}".format(
            i, expected_type, elapsed, label, q[:50]))
    except Exception as e:
        elapsed = time.time() - start
        cache_results.append(elapsed)
        print("{:<3} {:<12} {:>7.3f}s  ERROR  {}".format(
            i, expected_type, elapsed, q[:50]))
    print()

# Statistics
print("=" * 70)
print("LATENCY STATISTICS")
print("=" * 70)
results.sort()
n = len(results)
p50_idx = int(n * 0.5)
p95_idx = int(n * 0.95)
print("\n  COLD CACHE (first query):")
print("  Queries:  {}".format(n))
print("  Min:      {:.1f}s".format(min(results)))
print("  p50:      {:.1f}s".format(results[p50_idx]))
print("  p95:      {:.1f}s".format(results[min(p95_idx, n-1)]))
print("  Max:      {:.1f}s".format(max(results)))
print("  Mean:     {:.1f}s".format(statistics.mean(results)))

if cache_results:
    cache_results.sort()
    nc = len(cache_results)
    cp50_idx = int(nc * 0.5)
    cp95_idx = int(nc * 0.95)
    print("\n  WARM CACHE (cached queries):")
    print("  Queries:  {}".format(nc))
    print("  Min:      {:.3f}s".format(min(cache_results)))
    print("  p50:      {:.3f}s".format(cache_results[cp50_idx]))
    print("  p95:      {:.3f}s".format(cache_results[min(cp95_idx, nc-1)]))
    print("  Max:      {:.3f}s".format(max(cache_results)))
    print("  Mean:     {:.3f}s".format(statistics.mean(cache_results)))

print()
print("  PREVIOUS:  p50 ~46.8s, p95 ~103.9s (NVIDIA API)")
print("  TARGET:    p50 < 5s, p95 < 10s (Groq + cache)")
if results:
    print("  COLD:      p50 ~{:.1f}s, p95 ~{:.1f}s".format(
        results[p50_idx], results[min(p95_idx, n-1)]))
if cache_results:
    print("  WARM:      p50 ~{:.3f}s, p95 ~{:.3f}s".format(
        cache_results[int(len(cache_results)*0.5)],
        cache_results[min(int(len(cache_results)*0.95), len(cache_results)-1)]))
    print("  CACHE SPEEDUP: ~{:.0f}x faster".format(
        statistics.mean(results) / max(0.001, statistics.mean(cache_results))))
