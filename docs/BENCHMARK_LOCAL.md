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
  --username PRECEPTOR_TEST `
  --password TU_PASSWORD `
  --warmup 30 `
  --requests 500 `
  --concurrency 25
```

## 3) Endpoints por default que mide

- `GET /api/mensajes/unread_count/`
- `GET /api/notificaciones/unread_count/`
- `GET /api/preceptor/alertas-academicas/?limit=12`
- `GET /api/preceptor/alertas-inasistencias/?limit=12`
- `GET /api/reportes/curso/1A/?cuatrimestre=1`

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
