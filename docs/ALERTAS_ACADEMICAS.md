# Alertas Académicas: Algoritmo de detección

## Objetivo
Detectar de forma temprana situaciones de riesgo académico por alumno y materia, y notificar a:
- padre o tutor del alumno;
- preceptor(es) del curso del alumno.

La implementación principal está en:
- `calificaciones/alerts.py`
- Integración en carga de notas: `calificaciones/api_nueva_nota.py`

---

## 1. Normalización de riesgo por nota (0..1)
Para cada `Nota`, se calcula un riesgo numérico:

### 1.1 Prioridad de campos
1. Si existe `resultado` válido (`TEA`, `TEP`, `TED`), se usa ese valor.
2. Si no, se intenta con `calificacion` textual (`TEA`, `TEP`, `TED`, `NO ENTREGADO`).
3. Si no, se usa `nota_numerica` (o parseo numérico de `calificacion`).

### 1.2 Mapeo
- `TEA` -> `0.0`
- `TEP` -> `0.6`
- `TED` -> `1.0`
- `NO ENTREGADO` -> `0.8`

Si es nota numérica:
- `8..10` -> `0.0`
- `6..7.99` -> `0.25`
- `4..5.99` -> `0.6`
- `1..3.99` -> `1.0`

Si no se puede inferir riesgo, la nota no participa del promedio ponderado.

---

## 2. Ventana de análisis
Se analizan notas del mismo:
- `alumno`
- `materia`
- ventana temporal (por defecto `45` días)
- y, si aplica, mismo `cuatrimestre`

Configuración en `settings.py`:
- `ALERTAS_ACADEMICAS_VENTANA_DIAS` (default `45`)

### 2.1 Peso por recencia
Según antigüedad de la nota:
- `0..7` días -> peso `1.0`
- `8..21` días -> peso `0.7`
- `22..45` días -> peso `0.4`

### 2.2 Riesgo ponderado
Fórmula:

`R = sum(riesgo_nota * peso_recencia) / sum(peso_recencia)`

Solo con notas que tengan riesgo válido.

---

## 3. Triggers de alerta
Se evalúa sobre la nota recién cargada y su ventana histórica.

### Trigger A: TED crítico
Se activa si la nota nueva es `TED`.

### Trigger B: Racha
Se activa si las últimas 2 notas (por fecha/id) del alumno+materia son malas:
- cada una en `{TEP, TED}`
- y al menos una es la nota recién cargada (evita disparos retroactivos)

### Trigger C: Riesgo sostenido
Se activa si:
- `R >= 0.65`
- y hay al menos `3` notas válidas en la ventana.

### Trigger D: Caída brusca
Se activa si hay al menos 4 riesgos válidos y:
- promedio(últimas 2) - promedio(2 anteriores) >= `0.35`

---

## 4. Estado de alerta (binario)
El sistema ahora trabaja en modo binario:
- `0`: sin alerta
- `1`: en alerta

Si se activa cualquiera de los triggers A/B/C/D, se crea una alerta con `severidad=1`.
Si no se activa ninguno, no se crea una alerta.

---

## 5. Anti-spam y escalado
Antes de crear una nueva alerta para el mismo `alumno+materia`:

1. **Cooldown corto** (`7` días por defecto):
   - Si hubo una alerta reciente, no se crea una nueva.

2. **Reapertura** (`14` días por defecto):
   - Antes de ese plazo, no se re-alerta.
   - Luego de ese plazo, si la condición persiste, se puede crear una nueva alerta.

Configuración:
- `ALERTAS_ACADEMICAS_COOLDOWN_DIAS` (default `7`)
- `ALERTAS_ACADEMICAS_ESCALADO_DIAS` (default `14`)

---

## 6. Persistencia y notificaciones

### 6.1 Registro de evento
Si dispara, se crea un registro en `AlertaAcademica` con:
- alumno, materia, cuatrimestre;
- severidad;
- riesgo ponderado;
- triggers activados;
- ventana usada;
- nota disparadora;
- usuario actor (quien cargó la nota).

### 6.2 Destinatarios
- `Alumno.padre`
- `PreceptorCurso.preceptor` para el `curso` del alumno

### 6.3 Canal de aviso
- Siempre se crea `Notificacion` in-app (`tipo="otro"`, `meta.es_alerta_academica=true`).
- Email opcional vía Resend:
  - `ALERTAS_ACADEMICAS_EMAIL_ENABLED=True`

---

## 7. Respuesta API

### Alta individual de nota
`POST /api/calificaciones/notas/`

Incluye en la respuesta:
- `alerta.created` (bool)
- `alerta.severidad`
- `alerta.riesgo`
- `alerta.triggers`
- `alerta.reason` si no creó alerta (ej. cooldown)

### Alta masiva de notas
`POST /api/calificaciones/notas/masivo/`

Incluye:
- `alertas`: cantidad de alertas creadas en la tanda

---

## 8. Ejemplos rápidos

### Ejemplo A
Nota nueva `TED`:
- Trigger A = true
- Estado = en alerta (`severidad=1`)
- Crea alerta inmediata (salvo cooldown)

### Ejemplo B (racha)
Últimas dos notas: `TEP`, `TEP`:
- Trigger B = true
- Estado = en alerta (`severidad=1`)

### Ejemplo C (riesgo sostenido)
Riesgos recientes ponderados: `0.6`, `0.6`, `0.8`:
- `R` alto con 3 notas
- Trigger C = true
- Estado = en alerta (`severidad=1`)

---

## 9. Consideraciones operativas
- El algoritmo está pensado para ejecutarse en el momento de carga de nota.
- Si se re-procesan históricos, conviene desactivar temporalmente las alertas o usar una bandera de migración para evitar ruido.
- Para auditoría, usar `AlertaAcademica` como fuente de verdad; `Notificacion` es canal de entrega.
