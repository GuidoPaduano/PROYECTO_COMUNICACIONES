# Benchmark local de API

Script: [benchmark_api.py](/c:/Users/Guido%20Paduano/Documents/UI2/PROYECTO_COMUNICACIONES/benchmark_api.py)

## 1) Levantar backend

```powershell
cd C:\Users\Guido Paduano\Documents\UI2\PROYECTO_COMUNICACIONES
python manage.py runserver
```

## 2) Correr benchmark autenticado (recomendado)

```powershell
cd C:\Users\Guido Paduano\Documents\UI2\PROYECTO_COMUNICACIONES
python benchmark_api.py `
  --base-url http://127.0.0.1:8000 `
  --username qa_preceptor `
  --password QaLocal123! `
  --school qa-local `
  --warmup 30 `
  --requests 500 `
  --concurrency 25 `
  --max-errors 0 `
  --max-p95-ms 1500 `
  --max-p99-ms 3000 `
  --json-output benchmark-results.json
```

## 3) Endpoints por default que mide

- `GET /api/mensajes/unread_count/`
- `GET /api/notificaciones/unread_count/`
- `GET /api/preceptor/alertas-academicas/?limit=12`
- `GET /api/preceptor/alertas-inasistencias/?limit=12`
- `GET /api/alumnos/cursos/`

## 4) Definir tus propios endpoints

Formato: `METHOD:/ruta`, separados por coma.

```powershell
python benchmark_api.py `
  --base-url http://127.0.0.1:8000 `
  --username PRECEPTOR_TEST `
  --password TU_PASSWORD `
  --endpoints "GET:/api/mensajes/unread_count/,GET:/api/notificaciones/unread_count/,GET:/api/preceptor/alertas-inasistencias/?limit=12" `
  --requests 400 `
  --concurrency 20
```

## 5) Usar token JWT ya emitido (opcional)

```powershell
python benchmark_api.py `
  --base-url http://127.0.0.1:8000 `
  --token TU_ACCESS_TOKEN `
  --requests 400 `
  --concurrency 20
```

## 6) Cómo leer el resultado

- `mean`: promedio de latencia.
- `p95` y `p99`: cola de latencia (lo importante para UX bajo carga).
- `Status counts`: revisar si hay `401/403/500`.
- Comparar corrida A/B con los mismos parámetros.

El comando termina con error si supera `max-errors`, `max-p95-ms` o
`max-p99-ms`.

## 7) Última medición QA

Fecha: 13 de junio de 2026.

- Solicitudes medidas: 10.000.
- Concurrencia: 40.
- Respuestas correctas: 10.000.
- Errores: 0.
- Rendimiento: 158,29 solicitudes por segundo.
- Latencia promedio: 251,10 ms.
- p95: 716,26 ms.
- p99: 1.214,42 ms.
- Máximo: 2.321,48 ms.
- Duración medida: 63,18 segundos.
- Memoria residente: 86,19 MB antes y 87,87 MB después; variación de
  1,68 MB.
- Memoria privada: 77,90 MB antes y 78,84 MB después; variación de
  0,94 MB.

Evidencia:

- `docs/benchmark-soak-results-2026-06-13.json`
- `docs/benchmark-soak-process-before-2026-06-13.json`
- `docs/benchmark-soak-process-after-2026-06-13.json`

También se ejecutó una corrida intermedia de 2.000 solicitudes con 40
trabajadores: 2.000 respuestas correctas, cero errores, p95 de 723,77 ms y p99
de 1.205,64 ms. Evidencia: `docs/benchmark-results-2026-06-13.json`.

Esta medición corresponde al servidor de desarrollo local y sirve como línea
base de regresión, no como capacidad estimada de producción.
