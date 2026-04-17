# Alertas Académicas: Guía simple

## Para qué sirve
Este sistema ayuda a detectar cuando un alumno empieza a tener dificultades en una materia.

Cuando se detecta una situación de riesgo:
- se avisa al padre o tutor;
- se avisa al preceptor del curso;
- y queda registrado en el sistema.

La idea es intervenir temprano, no esperar al cierre del cuatrimestre.

---

## Cómo decide el sistema si hay riesgo
Cada nota nueva suma información sobre el estado del alumno en esa materia.

En palabras simples:
- notas buenas -> riesgo bajo;
- notas regulares -> riesgo medio;
- notas malas o aplazos -> riesgo alto.

El sistema mira especialmente lo más reciente (últimas semanas), porque es lo que mejor refleja la situación actual.

---

## Qué situaciones generan una alerta
Se genera una alerta cuando pasa alguna de estas cosas:

1. **Aplazo (TED)**
- Si entra un TED, se considera un caso crítico y se alerta de inmediato.

2. **Racha negativa**
- Si las últimas 2 notas de esa materia son malas (TEP o TED), se alerta.

3. **Riesgo sostenido**
- Si varias notas recientes muestran bajo rendimiento, aunque no haya un solo evento extremo, se alerta.

4. **Empeoramiento brusco**
- Si el rendimiento cae fuerte de una tanda de notas a la siguiente, se alerta.

---

## Estado de alerta
Ahora el sistema usa solo 2 estados:

- **Sin alerta**
- **En alerta**

Si se cumple algún trigger, pasa a **En alerta**.

---

## A quién le llega
Cada alerta se envía a:
- padre o tutor vinculado al alumno;
- preceptor(es) asignado(s) al curso.

Si está habilitado el envío por email, también puede llegar por correo.

---

## Cómo evitamos el "spam" de alertas
Para no saturar con avisos repetidos:
- si ya hubo una alerta reciente de la misma materia, no se manda otra enseguida;
- solo se vuelve a alertar si pasa tiempo y la situación empeora.

Esto permite poner el foco en lo importante y evita ruido.

---

## Qué hacer cuando llega una alerta
Sugerencia de acción rápida:

1. Revisar el detalle de notas del alumno en esa materia.
2. Contactar a la familia con un mensaje claro y breve.
3. Definir una acción concreta (apoyo, seguimiento, instancia de recuperación).
4. Hacer un control en las siguientes evaluaciones para ver mejora o escalado.

---

## En resumen
El sistema no reemplaza el criterio pedagógico: lo complementa.

Su función principal es:
- detectar temprano;
- avisar a las personas correctas;
- y facilitar una intervención a tiempo.
