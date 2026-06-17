#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Any


@dataclass
class EndpointSpec:
    method: str
    path: str


@dataclass
class HitResult:
    ok: bool
    status: int
    elapsed_ms: float
    endpoint: str
    error: str | None = None


DEFAULT_ENDPOINTS = [
    "GET:/api/mensajes/unread_count/",
    "GET:/api/notificaciones/unread_count/",
    "GET:/api/preceptor/alertas-academicas/?limit=12",
    "GET:/api/preceptor/alertas-inasistencias/?limit=12",
    "GET:/api/alumnos/cursos/",
]


def percentile(values: list[float], value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = (len(ordered) - 1) * value / 100
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - rank) + ordered[high] * (rank - low)


def build_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def parse_endpoint(raw: str) -> EndpointSpec:
    method, separator, path = raw.strip().partition(":")
    if not separator:
        return EndpointSpec("GET", method)
    method = method.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"} or not path:
        raise ValueError(f"Endpoint invalido: {raw}")
    return EndpointSpec(method, path)


def login(base_url: str, username: str, password: str, school: str, timeout: float):
    cookie_jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    request = urllib.request.Request(
        build_url(base_url, "/api/token/"),
        data=json.dumps(
            {"username": username, "password": password, "school": school}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with opener.open(request, timeout=timeout) as response:
        response.read()
    if not any(cookie.name == "access_token" for cookie in cookie_jar):
        raise RuntimeError("El login no devolvio la cookie access_token.")
    return opener


def hit(opener, base_url, endpoint, auth_header, school, timeout):
    headers = {"Accept": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    if school:
        headers["X-School"] = school
    request = urllib.request.Request(
        build_url(base_url, endpoint.path), headers=headers, method=endpoint.method
    )
    started = time.perf_counter()
    try:
        with opener.open(request, timeout=timeout) as response:
            response.read()
            status = int(response.status)
        elapsed = (time.perf_counter() - started) * 1000
        return HitResult(200 <= status < 300, status, elapsed, f"{endpoint.method} {endpoint.path}")
    except urllib.error.HTTPError as error:
        elapsed = (time.perf_counter() - started) * 1000
        return HitResult(False, int(error.code), elapsed, f"{endpoint.method} {endpoint.path}", str(error))
    except Exception as error:
        elapsed = (time.perf_counter() - started) * 1000
        return HitResult(False, 0, elapsed, f"{endpoint.method} {endpoint.path}", str(error))


def run_phase(name, opener, base_url, endpoints, auth_header, school, requests, concurrency, timeout):
    print(f"\n[{name}] requests={requests} concurrency={concurrency}")
    jobs = [random.choice(endpoints) for _ in range(requests)]
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(hit, opener, base_url, endpoint, auth_header, school, timeout)
            for endpoint in jobs
        ]
        results = [future.result() for future in as_completed(futures)]
    elapsed = time.perf_counter() - started
    print(f"[{name}] done in {elapsed:.2f}s ({len(results) / elapsed:.2f} req/s)")
    return results


def summarize(results: list[HitResult]) -> dict[str, Any]:
    latencies = [result.elapsed_ms for result in results]
    statuses: dict[str, int] = {}
    for result in results:
        key = str(result.status)
        statuses[key] = statuses.get(key, 0) + 1
    return {
        "total": len(results),
        "ok": sum(result.ok for result in results),
        "errors": sum(not result.ok for result in results),
        "latency_ms": {
            "min": min(latencies, default=0.0),
            "mean": statistics.mean(latencies) if latencies else 0.0,
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "max": max(latencies, default=0.0),
        },
        "status_counts": statuses,
    }


def print_summary(results):
    summary = summarize(results)
    latency = summary["latency_ms"]
    print("\n=== RESUMEN GLOBAL ===")
    print(f"Total: {summary['total']}")
    print(f"OK: {summary['ok']}")
    print(f"Errores: {summary['errors']}")
    print(
        "Latencia ms: "
        f"min={latency['min']:.2f} mean={latency['mean']:.2f} "
        f"p50={latency['p50']:.2f} p95={latency['p95']:.2f} "
        f"p99={latency['p99']:.2f} max={latency['max']:.2f}"
    )
    print("Status counts:", ", ".join(f"{key}:{value}" for key, value in summary["status_counts"].items()))

    by_endpoint: dict[str, list[HitResult]] = {}
    for result in results:
        by_endpoint.setdefault(result.endpoint, []).append(result)
    print("\n=== RESUMEN POR ENDPOINT ===")
    for endpoint, values in sorted(by_endpoint.items()):
        latencies = [value.elapsed_ms for value in values]
        print(
            f"{endpoint} | n={len(values)} ok={sum(value.ok for value in values)} "
            f"err={sum(not value.ok for value in values)} "
            f"mean={statistics.mean(latencies):.2f} p95={percentile(latencies, 95):.2f} "
            f"p99={percentile(latencies, 99):.2f}"
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark concurrente para la API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--school", default="qa-local")
    parser.add_argument("--token", default="")
    parser.add_argument("--endpoints", default=",".join(DEFAULT_ENDPOINTS))
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-errors", type=int, default=0)
    parser.add_argument("--max-p95-ms", type=float, default=1500.0)
    parser.add_argument("--max-p99-ms", type=float, default=3000.0)
    parser.add_argument("--json-output", default="")
    args = parser.parse_args()

    random.seed(args.seed)
    endpoints = [parse_endpoint(raw) for raw in args.endpoints.split(",") if raw.strip()]
    if not endpoints:
        print("No hay endpoints para medir.", file=sys.stderr)
        return 2

    opener = urllib.request.build_opener()
    auth_header = f"Bearer {args.token.strip()}" if args.token.strip() else ""
    if not auth_header and args.username and args.password:
        try:
            opener = login(args.base_url, args.username, args.password, args.school, args.timeout)
            print("Sesion autenticada correctamente.")
        except Exception as error:
            print(f"Error obteniendo sesion: {error}", file=sys.stderr)
            return 3

    run_phase("warmup", opener, args.base_url, endpoints, auth_header, args.school, max(0, args.warmup), max(1, args.concurrency), max(1.0, args.timeout))
    results = run_phase("measure", opener, args.base_url, endpoints, auth_header, args.school, max(1, args.requests), max(1, args.concurrency), max(1.0, args.timeout))
    summary = print_summary(results)
    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as output:
            json.dump(summary, output, ensure_ascii=False, indent=2)

    failures = []
    if summary["errors"] > max(0, args.max_errors):
        failures.append(f"errores={summary['errors']}")
    if summary["latency_ms"]["p95"] > args.max_p95_ms:
        failures.append(f"p95={summary['latency_ms']['p95']:.2f}ms")
    if summary["latency_ms"]["p99"] > args.max_p99_ms:
        failures.append(f"p99={summary['latency_ms']['p99']:.2f}ms")
    if failures:
        print("\nBenchmark rechazado: " + ", ".join(failures), file=sys.stderr)
        return 4
    print("\nBenchmark aprobado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
