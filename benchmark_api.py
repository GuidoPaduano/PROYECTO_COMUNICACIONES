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
from typing import Any


@dataclass
class EndpointSpec:
    method: str
    path: str
    body: dict[str, Any] | None = None


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
    "GET:/api/reportes/curso/1A/?cuatrimestre=1",
]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if p <= 0:
        return min(values)
    if p >= 100:
        return max(values)
    sorted_vals = sorted(values)
    rank = (len(sorted_vals) - 1) * (p / 100.0)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return sorted_vals[low]
    weight = rank - low
    return sorted_vals[low] * (1.0 - weight) + sorted_vals[high] * weight


def _build_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _parse_endpoint(raw: str) -> EndpointSpec:
    txt = (raw or "").strip()
    if not txt:
        raise ValueError("Endpoint vacio.")
    if ":" not in txt:
        return EndpointSpec(method="GET", path=txt)
    method, path = txt.split(":", 1)
    m = method.strip().upper()
    p = path.strip()
    if not p:
        raise ValueError(f"Endpoint invalido: {raw}")
    if m not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError(f"Metodo no soportado: {m}")
    return EndpointSpec(method=m, path=p)


def _request_json(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout_s: float = 20.0,
) -> tuple[int, Any]:
    data = None
    req_headers = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url=url, data=data, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        status = int(resp.getcode())
        raw = resp.read().decode("utf-8", errors="replace")
        if not raw:
            return status, None
        try:
            return status, json.loads(raw)
        except Exception:
            return status, raw


def _obtain_jwt(base_url: str, username: str, password: str, timeout_s: float) -> str:
    url = _build_url(base_url, "/api/token/")
    status, payload = _request_json(
        method="POST",
        url=url,
        body={"username": username, "password": password},
        timeout_s=timeout_s,
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"Fallo login JWT ({status}) en {url}: {payload}")
    token = None
    if isinstance(payload, dict):
        token = payload.get("access")
    if not token:
        raise RuntimeError(f"No se recibio access token en {url}: {payload}")
    return str(token)


def _hit(
    base_url: str,
    spec: EndpointSpec,
    auth_header: str | None,
    timeout_s: float,
) -> HitResult:
    url = _build_url(base_url, spec.path)
    headers: dict[str, str] = {}
    if auth_header:
        headers["Authorization"] = auth_header

    start = time.perf_counter()
    try:
        req = urllib.request.Request(url=url, headers=headers, method=spec.method)
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = int(resp.getcode())
            _ = resp.read()
        elapsed = (time.perf_counter() - start) * 1000.0
        ok = 200 <= status < 300
        return HitResult(ok=ok, status=status, elapsed_ms=elapsed, endpoint=f"{spec.method} {spec.path}")
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000.0
        return HitResult(
            ok=False,
            status=int(getattr(e, "code", 0) or 0),
            elapsed_ms=elapsed,
            endpoint=f"{spec.method} {spec.path}",
            error=f"HTTPError: {e}",
        )
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000.0
        return HitResult(
            ok=False,
            status=0,
            elapsed_ms=elapsed,
            endpoint=f"{spec.method} {spec.path}",
            error=str(e),
        )


def _run_phase(
    *,
    phase_name: str,
    base_url: str,
    endpoints: list[EndpointSpec],
    auth_header: str | None,
    total_requests: int,
    concurrency: int,
    timeout_s: float,
) -> list[HitResult]:
    print(f"\n[{phase_name}] requests={total_requests} concurrency={concurrency}")
    if total_requests <= 0:
        return []

    jobs: list[EndpointSpec] = []
    for _ in range(total_requests):
        jobs.append(random.choice(endpoints))

    results: list[HitResult] = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futures = [
            ex.submit(_hit, base_url, spec, auth_header, timeout_s)
            for spec in jobs
        ]
        for fut in as_completed(futures):
            results.append(fut.result())
    elapsed = time.perf_counter() - started
    rps = (len(results) / elapsed) if elapsed > 0 else 0.0
    print(f"[{phase_name}] done in {elapsed:.2f}s ({rps:.2f} req/s)")
    return results


def _print_summary(results: list[HitResult]) -> None:
    if not results:
        print("\nSin resultados.")
        return

    lat = [r.elapsed_ms for r in results]
    ok_count = sum(1 for r in results if r.ok)
    err_count = len(results) - ok_count
    by_status: dict[int, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    print("\n=== RESUMEN GLOBAL ===")
    print(f"Total: {len(results)}")
    print(f"OK: {ok_count}")
    print(f"Errores: {err_count}")
    print(f"Latencia ms: min={min(lat):.2f} mean={statistics.mean(lat):.2f} p50={_percentile(lat, 50):.2f} p95={_percentile(lat, 95):.2f} p99={_percentile(lat, 99):.2f} max={max(lat):.2f}")
    print("Status counts:", ", ".join(f"{k}:{v}" for k, v in sorted(by_status.items())))

    by_endpoint: dict[str, list[HitResult]] = {}
    for r in results:
        by_endpoint.setdefault(r.endpoint, []).append(r)

    print("\n=== RESUMEN POR ENDPOINT ===")
    for ep in sorted(by_endpoint.keys()):
        vals = by_endpoint[ep]
        e_lat = [x.elapsed_ms for x in vals]
        e_ok = sum(1 for x in vals if x.ok)
        print(
            f"{ep} | n={len(vals)} ok={e_ok} err={len(vals)-e_ok} "
            f"mean={statistics.mean(e_lat):.2f} p95={_percentile(e_lat, 95):.2f} p99={_percentile(e_lat, 99):.2f}"
        )

    errors = [r for r in results if not r.ok]
    if errors:
        print("\n=== EJEMPLOS DE ERROR (max 10) ===")
        for r in errors[:10]:
            print(f"{r.endpoint} status={r.status} err={r.error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark simple para endpoints API (con JWT opcional).")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL, ej: http://127.0.0.1:8000")
    parser.add_argument("--username", default="", help="Usuario para obtener JWT en /api/token/")
    parser.add_argument("--password", default="", help="Password para obtener JWT")
    parser.add_argument("--token", default="", help="JWT ya emitido (si se setea, no usa username/password)")
    parser.add_argument("--endpoints", default=",".join(DEFAULT_ENDPOINTS), help="Lista separada por coma, formato METHOD:/path")
    parser.add_argument("--warmup", type=int, default=20, help="Requests de warmup")
    parser.add_argument("--requests", type=int, default=300, help="Requests medidos")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrencia")
    parser.add_argument("--timeout", type=float, default=20.0, help="Timeout por request en segundos")
    parser.add_argument("--seed", type=int, default=42, help="Seed RNG")
    args = parser.parse_args()

    random.seed(args.seed)

    endpoint_specs = []
    for raw in (args.endpoints or "").split(","):
        txt = raw.strip()
        if not txt:
            continue
        endpoint_specs.append(_parse_endpoint(txt))
    if not endpoint_specs:
        print("No hay endpoints validos para testear.", file=sys.stderr)
        return 2

    auth_header = None
    token = (args.token or "").strip()
    if token:
        auth_header = f"Bearer {token}"
    elif args.username and args.password:
        try:
            token = _obtain_jwt(args.base_url, args.username, args.password, args.timeout)
            auth_header = f"Bearer {token}"
            print("JWT obtenido correctamente.")
        except Exception as e:
            print(f"Error obteniendo JWT: {e}", file=sys.stderr)
            return 3
    else:
        print("Sin auth JWT: se ejecuta en modo anonimo (puede devolver 401/403 en endpoints protegidos).")

    _ = _run_phase(
        phase_name="warmup",
        base_url=args.base_url,
        endpoints=endpoint_specs,
        auth_header=auth_header,
        total_requests=max(0, args.warmup),
        concurrency=max(1, args.concurrency),
        timeout_s=max(1.0, args.timeout),
    )

    results = _run_phase(
        phase_name="measure",
        base_url=args.base_url,
        endpoints=endpoint_specs,
        auth_header=auth_header,
        total_requests=max(1, args.requests),
        concurrency=max(1, args.concurrency),
        timeout_s=max(1.0, args.timeout),
    )
    _print_summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
