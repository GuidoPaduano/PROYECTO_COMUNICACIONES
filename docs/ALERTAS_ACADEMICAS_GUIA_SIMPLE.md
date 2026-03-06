# Alertas Academicas: Guia Simple

## Para que sirve
Este sistema ayuda a detectar cuando un alumno empieza a tener dificultades en una materia.

Cuando se detecta una situacion de riesgo:
- se avisa al padre/tutor,
- se avisa al preceptor del curso,
- y queda registrado en el sistema.

La idea es intervenir temprano, no esperar al cierre del cuatrimestre.

---

## Como decide el sistema si hay riesgo
Cada nota nueva suma informacion sobre el estado del alumno en esa materia.

En palabras simples:
- notas buenas -> riesgo bajo,
- notas regulares -> riesgo medio,
- notas malas o aplazos -> riesgo alto.

El sistema mira especialmente lo mas reciente (ultimas semanas), porque es lo que mejor refleja la situacion actual.

---

## Que situaciones generan una alerta
Se genera alerta cuando pasa alguna de estas cosas:

1. **Aplazo (TED)**
- Si entra un TED, se considera caso critico y se alerta de inmediato.

2. **Racha negativa**
- Si las ultimas 2 notas de esa materia son malas (TEP o TED), se alerta.

3. **Riesgo sostenido**
- Si varias notas recientes muestran bajo rendimiento, aunque no haya un solo evento extremo, se alerta.

4. **Empeoramiento brusco**
- Si el rendimiento cae fuerte de una tanda de notas a la siguiente, se alerta.

---

## Estado de alerta
Ahora el sistema usa solo 2 estados:

- **Sin alerta**
- **En alerta**

Si se cumple algun trigger, pasa a **En alerta**.

---

## A quien le llega
Cada alerta se envia a:
- padre/tutor vinculado al alumno,
- preceptor(es) asignado(s) al curso.

Si esta habilitado el envio por email, tambien puede llegar por correo.

---

## Como evitamos “spam” de alertas
Para no saturar con avisos repetidos:
- si ya hubo alerta reciente de la misma materia, no se manda otra enseguida;
- solo se vuelve a alertar si pasa tiempo y la situacion empeora.

Esto permite foco en lo importante y evita ruido.

---

## Que hacer cuando llega una alerta
Sugerencia de accion rapida:

1. Revisar detalle de notas del alumno en esa materia.
2. Contactar a la familia con un mensaje claro y breve.
3. Definir una accion concreta (apoyo, seguimiento, instancia de recuperacion).
4. Hacer control en las siguientes evaluaciones para ver mejora o escalado.

---

## En resumen
El sistema no reemplaza el criterio pedagogico: lo complementa.

Su funcion principal es:
- detectar temprano,
- avisar a las personas correctas,
- y facilitar una intervencion a tiempo.
