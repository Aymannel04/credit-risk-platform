# Live API latency (measured, not estimated)

Measured 2026-10-13 18:06 against the Lambda function in `eu-north-1` (512 MB, 10 s timeout, x86_64, image tag `ac13c6b`, model `b3069001d62e`). Nothing here is a benchmark of AWS: it is one small function measured a few times.

## Client side: from the owner's computer (includes the internet trip and the TLS handshake)

Measured from the owner's computer; it depends on the distance to Stockholm and on the local network.

- `POST /score`, 30 sequential signed calls after one warm-up: n=30, min 353.4, median 681.4, p95 1505.0, max 2277.5 ms; non-200 answers: 0
- `GET /health`, 30 calls: n=30, min 246.4, median 366.1, p95 677.7, max 1257.3 ms; non-200 answers: 0

## Server side: what Lambda reports in its own logs (independent of the client's location)

Window: the last 240 minutes, 71 invocations, of which 2 cold starts.

- Cold start, init duration (a new container is prepared): n=2, min 1188.2, median 1251.8, p95 1315.4, max 1315.4 ms
- Duration of the request itself, warm: n=69, min 2.2, median 2.7, p95 3.0, max 3.3 ms
- Duration of the request itself, on a cold start: n=2, min 2.8, median 3.1, p95 3.4, max 3.4 ms
- Billed duration: n=71, min 3.0, median 3.0, p95 4.0, max 1319.0 ms
- Max memory used: n=71, min 78.0, median 78.0, p95 78.0, max 78.0 MB of 512 MB configured
- Billed compute in this window: 1.3615 GB-seconds (the free tier is 400,000 GB-seconds a month)

## How to read it

A cold start happens once, when no prepared container is waiting (first call after a quiet period, or after a deploy): the user pays the init duration once. A warm call reuses a running container and only pays the request duration. Quoting one number hides this, so both are reported.
