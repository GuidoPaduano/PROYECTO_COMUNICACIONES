# Estado QA actual

Actualizado: 15 de junio de 2026

## Falla conocida: servicio de correo no integrado

- Severidad: Alta
- Estado: Abierta, bloqueada por integracion externa
- Areas afectadas: recuperacion de contrasena y alertas academicas por email

### Descripcion

El sistema contiene los flujos y llamadas necesarios para enviar correos, pero no
hay un proveedor de correo conectado y configurado para el entorno actual.

### Pasos para reproducir

1. Solicitar la recuperacion de contrasena para un usuario con email registrado.
2. Generar una accion que intente enviar una alerta academica por email.
3. Revisar la recepcion del mensaje y los logs del backend.

### Resultado esperado

El proveedor acepta el mensaje y el usuario recibe el correo correspondiente.

### Resultado actual

El correo no se entrega. Cuando se intenta utilizar Resend sin una integracion
operativa, el backend registra un error de conexion o certificado. La operacion
principal puede continuar, pero la notificacion externa no se completa.

### Alcance QA actual

- La construccion de enlaces y el comportamiento de las APIs se prueban con el
  servicio de correo simulado.
- La UI contempla respuestas exitosas y errores del servicio.
- No esta validada la entrega real, el remitente, el dominio, los reintentos, los
  rebotes ni la llegada a spam.

### Condicion de cierre

1. Configurar un proveedor y credenciales validas por ambiente.
2. Verificar el dominio y remitente.
3. Ejecutar una prueba real de recuperacion de contrasena.
4. Ejecutar una prueba real de alerta academica.
5. Validar entrega, contenido, enlaces, expiracion y manejo de errores.

## Pertenencia multi-colegio de Directivos

- Severidad original: Alta
- Estado: Corregida y cubierta
- Se incorporo una membresia institucional usuario-colegio independiente de los
  roles de administrador, profesor y preceptor.
- El alta o cambio de rol a Directivo crea la membresia en el colegio activo.
- Login, `whoami`, resolucion de colegio y listado de colegios disponibles
  validan esa membresia.
- Un Directivo puede pertenecer a varios colegios y cambiar el colegio activo
  desde el selector de la aplicacion.
- Un colegio sin membresia es rechazado y no aparece entre los disponibles.
- Los directorios administrativos solo muestran Directivos del colegio activo.
- La membresia no otorga acceso a Admin colegio ni Admin plataforma.
- El seed `qa-local` crea la membresia del usuario `qa_directivo`.
- Resultados: regresion backend ampliada 112 de 112; Jest 35 de 35; TypeScript
  sin errores; smoke E2E de Directivo aprobado en Chromium.

## Ultima regresion aprobada

- Backend focalizado: 44 de 44 pruebas.
- Frontend Jest: 33 de 33 pruebas.
- Playwright E2E: 49 de 49 pruebas.
- Playwright E2E focalizado en alumnos y mensajes: 20 de 20 pruebas.
- Playwright E2E focalizado en familia, cursos y rutas directas: 15 de 15
  pruebas.
- Playwright E2E focalizado en ficha academica y resiliencia: 4 de 4 pruebas.
- Playwright E2E focalizado en trafico y ficha academica: 5 de 5 pruebas.
- Playwright E2E focalizado en accesibilidad y ficha academica: 7 de 7
  pruebas.
- Playwright E2E de resiliencia administrativa: 10 de 10 pruebas aprobadas en
  Chromium y Firefox.
- Playwright E2E de resiliencia de administracion de plataforma: 10 de 10
  pruebas aprobadas en Chromium y Firefox.
- Playwright E2E de alta de colegios y administradores: 12 de 12 pruebas
  aprobadas en Chromium y Firefox.
- Playwright E2E de accesibilidad administrativa: 8 de 8 pruebas aprobadas en
  Chromium y Firefox.
- Regresion administrativa conjunta posterior: 16 de 16 pruebas aprobadas en
  Chromium.
- Backend focalizado en alumnos, contexto escolar y autenticacion: 70 de 70
  pruebas.
- Playwright E2E focalizado en permisos, sesiones y mensajeria privada: 7 de 7
  pruebas.
- Benchmark concurrente de lectura: 500 de 500 respuestas correctas.
- Backend focalizado en rendimiento masivo: 2 de 2 pruebas.
- Playwright de compatibilidad Chromium/Firefox: 6 de 6 pruebas.
- Playwright de descargas, landscape y tactil: 7 de 7 pruebas ejecutadas;
  1 caso tactil omitido en Firefox por limitacion de emulacion.
- Playwright de recuperacion de contrasena: 9 de 9 pruebas ejecutadas;
  1 integracion real omitida en Firefox para evitar duplicar cambios.
- Playwright de no leidos, notificaciones y rutas directas: 22 de 22 pruebas
  aprobadas en Chromium y Firefox.
- Playwright de administracion escolar: 14 de 14 pruebas aprobadas en Chromium
  y Firefox.
- Backend de administracion de personal escolar: 16 de 16 pruebas.
- Backend de estabilidad del seed QA: 3 de 3 pruebas.
- Backend de recuperacion y cambio de contrasena: 12 de 12 pruebas.
- Build de produccion Next.js: aprobado.

## Branding multi-colegio

- Estado: Cubierto
- La administracion de plataforma muestra una vista previa antes de guardar.
- Se verificaron nombre corto, logo, color principal y color de acento.
- Se verifico persistencia despues de recargar.
- Se verificaron login, recuperacion de contrasena y sesion autenticada.
- Se comprobo el aislamiento visual entre dos colegios.
- Se comprobo el fallback ante un logo roto.
- Se comprobo que un color invalido es rechazado sin alterar el valor guardado.

## Transferencia de alumnos

- Estado: Cubierto
- Se verifico transferencia valida entre cursos asignados.
- La ficha refleja el nuevo curso sin requerir una recarga completa.
- Se verifico persistencia despues de recargar y cambiar de usuario.
- El alumno desaparece del curso anterior y aparece en el nuevo.
- Se conservan notas, asistencias, sanciones y vinculos familiares.
- Se invalida la cache de hijos del padre despues de transferir.
- Se rechazan cursos de otro colegio y destinos no asignados.
- Administrador de colegio y preceptor ven la accion.
- Profesor y padre no ven la accion.

## Resiliencia de cursos y mensajes

- Estado: Cubierto
- La pantalla de cursos diferencia carga, catalogo vacio y error de API.
- Durante la carga ya no se muestra anticipadamente "No hay cursos".
- Los errores de cursos muestran el detalle disponible y permiten reintentar.
- La bandeja de mensajes ya no convierte respuestas HTTP fallidas en una bandeja
  vacia.
- Los errores de mensajes muestran el detalle disponible y permiten reintentar.
- Se verifico que un reintento exitoso recupera ambas pantallas.

## Resiliencia de Mis Hijos y Mis Cursos

- Estado: Cubierto
- Mis Hijos diferencia una cuenta sin alumnos asociados de un error HTTP.
- Los errores conservan el detalle enviado por el backend.
- El reintento de Mis Hijos vuelve a consultar sin recargar toda la aplicacion.
- Mis Cursos prueba sus endpoints alternativos y solo muestra el estado vacio
  cuando alguno respondio correctamente.
- Si todos los catalogos de cursos fallan, se muestra error con reintento.
- Se verifico la recuperacion de ambas pantallas despues de un error 503.

## Resiliencia de la ficha del alumno

- Estado: Cubierto
- Notas, sanciones y asistencias mantienen estados de error independientes.
- Una falla completa de endpoints alternativos ya no se presenta como una lista
  vacia.
- Cada pestaña conserva el detalle de error enviado por el backend.
- Cada sección permite reintentar sin recargar la ficha ni bloquear las otras.
- Se verificaron errores 503 simultaneos y recuperacion posterior de las tres
  secciones.
- Los flujos normales de edicion, filtros y navegacion mobile siguen operativos.

## Rendimiento de la ficha del alumno

- Estado: Cubierto
- Se detecto un bucle de redireccion por incompatibilidad de barra final.
- La carga de detalle paso de 42 eventos HTTP con respuestas 301 a una unica
  respuesta 200.
- Detalle y catalogo esperan a que el contexto de sesion este disponible.
- La resolucion del alumno comparte cache y promesas concurrentes.
- Notas, sanciones y asistencias esperan identificadores resueltos antes de
  consultar, evitando un 404 inicial con el PK usado como legajo.
- La prueba E2E limita detalle, catalogo y cada API academica a una llamada por
  carga de ficha.
- Se agregaron pruebas backend para las rutas de detalle y catalogo sin barra.

## Accesibilidad de la ficha del alumno

- Estado: Cubierto
- Las tarjetas de Notas, Sanciones e Inasistencias son controles semanticos
  asociados a sus paneles.
- Se verifico activacion con teclado y navegacion con flechas, Inicio y Fin.
- Solo la pestana activa participa del orden de tabulacion del grupo.
- La pestana seleccionada expone su estado mediante `aria-selected`.
- Los paneles y controles muestran foco visible en desktop y mobile.
- Los estados de carga se anuncian de forma no intrusiva.
- Los errores academicos se exponen como alertas y conservan los controles de
  reintento.
- La prueba E2E valida teclado en resoluciones desktop y mobile, asociacion entre
  pestanas y paneles, y anuncio de errores.

## Seguridad y permisos extremos

- Estado: Cubierto en el bloque actual
- Severidad del hallazgo: Alta
- Se detecto que un usuario autenticado sin colegio resuelto podia intentar
  vincularse a un legajo de cualquier colegio porque la consulta quedaba sin
  alcance escolar.
- La vinculacion de legajo ahora exige el rol Alumno y un colegio activo
  resuelto.
- Padres, personal y usuarios con contexto escolar ambiguo reciben un rechazo y
  no alteran el vinculo del alumno.
- Se verifico que una sesion valida no expone alumnos de otro colegio aunque se
  manipule el encabezado `X-School`.
- Se verificaron transferencias con IDs de alumno o curso pertenecientes a otro
  colegio y se comprobo que los registros no cambian.
- La regresion mantiene los bloqueos de lectura y escritura entre alumnos,
  cursos y roles, el cierre de sesion, y la privacidad de mensajes.

## Rendimiento, carga y concurrencia

- Estado: Cubierto en el bloque local actual
- Se actualizo el benchmark para autenticarse mediante cookies HttpOnly y
  contexto de colegio, de acuerdo con el contrato vigente.
- El benchmark ahora permite limites automaticos de errores, p95 y p99, y
  salida JSON.
- Se midieron 500 solicitudes con concurrencia 25 sobre contadores, alertas y
  catalogo de cursos.
- Resultado: 500 respuestas correctas, 0 errores y 145.76 solicitudes por
  segundo.
- Latencia global: promedio 168.27 ms, p95 274.06 ms y p99 677.77 ms.
- Se agregaron presupuestos de consultas para crear y actualizar 100
  asistencias masivas sin crecimiento N+1.
- Ambas pruebas masivas usan hasta 8 consultas y completaron correctamente.
- La concurrencia de escrituras no se usa como medida de capacidad sobre
  SQLite; debe repetirse sobre PostgreSQL en un ambiente similar a produccion.

## Compatibilidad de navegadores y dispositivos

- Estado: Chromium y Firefox cubiertos; WebKit bloqueado por el entorno local.
- Se agrego una matriz E2E para desktop 1366x768, tablet 820x1180 y mobile
  390x844.
- Se verificaron login de padre, dashboard, Mis Hijos, ficha academica,
  navegacion por teclado entre pestanas y bandeja de mensajes.
- Chromium y Firefox completaron 6 de 6 casos sin errores HTTP 500, fallas de
  datos ni desbordes horizontales.
- Se detecto en Chromium mobile que `.app-main` conservaba un ancho minimo de
  432 px sobre un viewport de 390 px y cortaba la pantalla de Mensajes.
- El desborde se corrigio permitiendo que el item de grid reduzca su ancho con
  `min-width: 0`; la regresion mobile quedo aprobada en ambos navegadores.
- El boton hamburguesa no tenia nombre accesible y ahora expone
  `aria-label="Abrir menu lateral"`.
- Firefox y WebKit requirieron instalar sus motores. La descarga solo fue
  posible con una anulacion TLS temporal por el certificado local; no se dejo
  una configuracion insegura persistente.
- WebKit abre paginas minimas correctamente, pero en este Windows su proceso de
  red queda bloqueado durante el flujo y Playwright no logra finalizar ni
  aplicar el timeout. No se considera una aprobacion ni una falla funcional del
  producto hasta repetirlo en macOS o un runner CI compatible.

## Descargas, landscape y formularios tactiles

- Estado: Cubierto en Chromium y Firefox, salvo emulacion tactil Firefox.
- Se descargaron los PDF de notas, sanciones e inasistencias desde la ficha del
  padre en ambos navegadores.
- Cada archivo fue validado por nombre, tamano minimo y firma binaria `%PDF-`.
- La ficha academica y Mensajes no presentan desborde horizontal en mobile
  landscape 844x390 ni tablet landscape 1180x820.
- En Chromium se abrio el formulario de comunicado a familias mediante `tap`,
  se seleccionaron curso y alumno, y se completo asunto y contenido sin enviar.
- Se detecto que Mensajes cargaba el catalogo global de cursos para profesores,
  elegia primero un curso no asignado y provocaba un 403 antes de cargar el
  curso permitido.
- Mensajes ahora usa `/notas/catalogos/` para profesores,
  `/preceptor/cursos/` para preceptores y conserva `/alumnos/cursos/` para los
  demas roles.
- La regresion confirma que el formulario del profesor carga directamente su
  curso habilitado y no genera consultas de alumnos con HTTP 403.

## Recuperacion de contrasena

- Estado: Flujo de UI y cambio de contrasena cubiertos; envio real de correo
  pendiente de integracion operativa.
- Se conservaron pruebas simuladas para respuesta generica, error del servicio,
  link incompleto, contrasenas diferentes y payload de confirmacion.
- Se agrego una integracion real con un usuario temporal y un UID/token generado
  por Django, equivalente al enlace que recibiria el usuario por correo.
- Se comprobo cambio real de contrasena, login posterior con la clave nueva y
  rechazo de reutilizacion del mismo token.
- Se detecto un hallazgo de severidad alta: Next elimina la barra final al
  reenviar los POST y Django respondia 500 por `APPEND_SLASH` en solicitud y
  confirmacion de recuperacion.
- Se agregaron rutas equivalentes sin barra para ambos endpoints y cobertura
  backend directa.
- El envio por Resend no se considera aprobado. El sistema sigue dependiendo de
  una configuracion/proveedor externo y el bloque actual simula exclusivamente
  la entrega del enlace.

## Consistencia de no leidos y notificaciones

- Estado: Cubierto en Chromium y Firefox.
- Abrir un hilo por URL directa limpia el contador y conserva el estado tras
  recargar.
- Una respuesta del padre genera exactamente un mensaje no leido para el
  profesor; abrir el hilo lo limpia y el resultado persiste tras recargar.
- Marcar todos los mensajes como leidos limpia el contador, el badge lateral y
  sincroniza otra pestana abierta.
- Abrir una notificacion individual limpia su badge y navega al hilo correcto.
- Marcar todas las notificaciones como leidas sincroniza otra pestana.
- La campana conserva la pagina operativa cuando falla el endpoint de preview.
- Los envios internos responden HTTP 201 aunque Resend responda HTTP 403. Ese
  error externo es esperado porque el servicio de correo no esta integrado y no
  se considera una falla de la mensajeria interna.
- Se estabilizo la preparacion E2E creando mensajes por API; la UI sigue
  verificando lectura, badges, navegacion, actualizacion entre pestanas y
  persistencia.

## Administracion escolar

- Estado: Cubierto en Chromium y Firefox para los flujos disponibles.
- Se verifico el alta de profesores con asignacion inicial a un curso.
- Se verifico el alta de padres con vinculacion inicial a un alumno sin tutor.
- Se verifico la vinculacion posterior de un alumno a un padre desde el
  directorio.
- Las asignaciones de profesores y preceptores se guardan correctamente; la
  seleccion del profesor persiste despues de recargar la pagina.
- La administracion de plataforma permite editar un colegio y confirma su
  eliminacion mediante el trabajo asincronico correspondiente.
- Se detecto un hallazgo de severidad media: un profesor que abria por URL
  directa las pantallas de alta o asignaciones quedaba viendo un estado de carga
  indefinido.
- Las pantallas compartidas ahora separan la carga de sesion del rechazo por
  permisos y muestran explicitamente `Acceso restringido`.
- La edicion de nombre, apellido y email esta disponible para profesores,
  preceptores, directivos y padres desde el directorio.
- La API valida pertenencia al colegio activo, campos obligatorios, nombres sin
  numeros y unicidad del email.
- Un administrador no puede editar por ID a un usuario vinculado solamente con
  otro colegio.
- Resultado focalizado: backend de administracion 21 de 21; E2E de edicion
  aprobado en Chromium; Jest 35 de 35 y TypeScript sin errores.

## Resiliencia administrativa

- Estado: Cubierto en Chromium y Firefox para las herramientas del colegio.
- El directorio muestra el detalle de una falla HTTP 503 y permite recuperar la
  informacion mediante `Actualizar`.
- Las asignaciones muestran el error HTTP 503, permiten reintentar y presentan
  correctamente el estado vacio cuando no hay cursos.
- El alta de usuarios conserva los datos ingresados cuando el backend rechaza
  un nombre de usuario duplicado con HTTP 400.
- Se verifico que alta, directorio, asignaciones y cursos no generen
  desplazamiento horizontal en una pantalla mobile de 390 x 844.
- Se detecto un hallazgo de severidad media: un profesor que accedia
  directamente a cursos o al directorio quedaba en un estado de carga
  indefinido.
- Cursos y directorio ahora separan la carga de sesion del rechazo por permisos
  y muestran explicitamente `Acceso restringido`.

## Resiliencia de administracion de plataforma

- Estado: Cubierto en Chromium y Firefox para los escenarios negativos
  principales.
- Un administrador de colegio recibe `Acceso restringido` al abrir directamente
  colegios, cursos, admins por colegio o importacion de alumnos.
- Se detectaron dos hallazgos de severidad media: admins por colegio e
  importacion de alumnos mantenian una carga indefinida para usuarios sin
  privilegios de plataforma.
- Ambas rutas ahora separan la carga de sesion del rechazo por permisos.
- Admins por colegio muestra una falla HTTP 503 y recupera el listado mediante
  `Actualizar`.
- La edicion conserva el formulario y presenta el detalle del backend ante una
  validacion HTTP 400.
- La importacion invalida muestra el resumen y los errores por fila, y mantiene
  deshabilitada la confirmacion.
- Se detecto un hallazgo de severidad media en el borrado asincronico: el error
  de un trabajo con estado `failed` desaparecia al recargar el listado.
- La pantalla ahora recarga primero los colegios y luego conserva visible el
  error del trabajo, sin retirar el colegio de la tabla.

## Alta de colegios y administradores

- Estado: Cubierto en Chromium y Firefox para validaciones, errores y mobile.
- Se detecto un hallazgo de severidad media: el alta de colegios quedaba en
  carga indefinida cuando un administrador de colegio abria la ruta directa.
- El alta ahora separa la carga de sesion del rechazo por permisos y muestra
  `Acceso restringido`.
- Un rechazo HTTP 400 por colegio duplicado conserva nombre, nombre corto y
  slug, muestra el detalle del backend y vuelve a habilitar el formulario.
- Admins por colegio muestra estados vacios explicitos cuando no existen
  colegios ni usuarios asignables.
- Un error HTTP 400 al guardar administradores conserva todos los checks y el
  contador de seleccion para permitir corregir o reintentar.
- La descarga de plantilla muestra el detalle de una falla HTTP 503 y permite
  descargar correctamente al segundo intento.
- Alta de colegio, admins por colegio, importacion y listado de colegios no
  generan desplazamiento horizontal en mobile de 390 x 844.

## Accesibilidad administrativa

- Estado: Cubierto en Chromium y Firefox para anuncios, teclado y dialogos.
- Se detecto un hallazgo de severidad media: los errores y confirmaciones
  administrativas eran solo visuales y no se anunciaban a lectores de pantalla.
- Los errores ahora usan `role="alert"` y los resultados exitosos usan
  `role="status"` con `aria-live="polite"`.
- Se detecto un hallazgo de severidad media en admins por colegio: seleccionar
  un colegio dependia de hacer clic sobre la fila.
- Cada colegio ahora expone un boton enfocable con `aria-pressed`; la seleccion
  funciona con Enter y los buscadores tienen nombres accesibles.
- Los dialogos para crear o vincular alumnos ahora incluyen una descripcion
  accesible.
- Se detecto un hallazgo de severidad media: los dialogos controlados no
  restauraban de forma consistente el foco al boton que los abria.
- Crear alumno y confirmar borrado restauran el foco explicitamente. El dialogo
  destructivo tambien cierra con Escape sin ejecutar el borrado.

## Estabilidad de datos QA

- Estado: Cubierto para el entorno local `qa-local`.
- Se detecto acumulacion entre corridas: 30 cursos, 35 alumnos, 218 mensajes y
  38 usuarios temporales, cuando la base canonica requiere 2 cursos, 2 alumnos
  y 2 mensajes.
- `seed_qa_data` incorpora `--reset-e2e-data`, limitado por seguridad a slugs
  que comienzan con `qa-`.
- El reinicio elimina los datos del tenant QA y las cuentas con prefijos E2E
  reservados, luego reconstruye usuarios, cursos, relaciones y muestras base.
- La prueba backend confirma que otro colegio, sus cursos y sus alumnos no son
  modificados.
- Playwright ejecuta el reinicio antes y despues de cada corrida mediante
  `globalSetup` y `globalTeardown`; la limpieza final tambien se ejecuta cuando
  una prueba falla.
- Despues de la regresion, la base queda en 2 cursos, 2 alumnos, 2 notas, 2
  asistencias, 1 sancion, 1 evento, 1 comunicado, 2 mensajes, 1 notificacion y
  cero usuarios temporales.
- Se detecto un hallazgo de severidad alta en asignaciones: buscar un profesor
  cargaba una lista parcial y al guardar eliminaba del curso a los profesores
  que no coincidieran con la busqueda.
- La pantalla ahora carga siempre el conjunto completo y aplica la busqueda
  solo como filtro visual. La regresion comprueba que `qa_profesor` conserva su
  asignacion al agregar otro docente.

## Accesibilidad WCAG automatizada y zoom

- Estado: Cubierto en Chromium y Firefox sobre seis rutas representativas de
  padres, profesores, administracion escolar y administracion de plataforma.
- Se incorporo una regresion con axe-core para reglas WCAG 2 A/AA y una prueba
  de reflow equivalente a zoom del 200 %.
- Se detectaron contrastes insuficientes en sidebar, avatares, badges, mensajes
  y vistas previas de branding.
- Se corrigieron los colores compartidos y la vista previa ahora calcula texto
  claro u oscuro segun la luminancia del color configurado.
- Se detectaron controles sin nombre accesible: campana de notificaciones,
  selectores de alumno, curso y colegio, y selectores de color.
- Todos esos controles ahora exponen nombres explicitos.
- Se detecto una fila de mensaje interactiva que contenia el boton de eliminar.
  Las acciones ahora son botones hermanos, evitando controles interactivos
  anidados.
- Resultado final: 7 de 7 pruebas aprobadas por navegador, sin violaciones
  serias o criticas en las rutas auditadas y sin desbordamiento horizontal al
  200 %.
- La auditoria ahora espera que finalicen las transiciones de branding para no
  medir colores intermedios y contempla los tiempos de carga observados en
  Firefox.
- `npm run build` compila, valida tipos y genera correctamente las 40 paginas.

## Regresion critica en Firefox

- Estado: 17 de 17 pruebas aprobadas.
- Se cubrieron home publica, login de profesor y admin de colegio, aislamiento
  academico por rol, bloqueo anonimo, invalidacion de sesion por logout,
  seguridad de lectura y respuesta de mensajes, mensajes grupales por curso,
  alta y asignacion de usuarios, vinculacion padre-alumno, restricciones de URL
  directa y CRUD de colegios.
- Sumando WCAG y zoom, esta ronda ejecuto 24 de 24 pruebas aprobadas en Firefox.
- El helper compartido de login ahora espera la navegacion y el layout final,
  reduciendo carreras entre la redireccion posterior al token y la siguiente
  accion del test.

## Bloqueo WebKit/Safari

- Estado: Bloqueado por infraestructura local, no por una falla confirmada del
  producto.
- WebKit logro aprobar el primer caso WCAG, pero su instalacion local quedo sin
  `Playwright.exe` durante la corrida.
- La reinstalacion limpia fue intentada y fallo porque Node no puede validar el
  certificado TLS del proxy o CA local (`UNABLE_TO_VERIFY_LEAF_SIGNATURE`).
- No se desactivo la validacion SSL.
- Condicion de cierre: instalar la CA correcta para Node o ejecutar WebKit en un
  runner macOS/Linux o CI con descarga de Playwright operativa.

## Preflight de infraestructura externa del 15 de junio de 2026

- PostgreSQL 18 esta instalado, ejecutandose y escuchando en el puerto 5432.
- La autenticacion local exige `scram-sha-256`; no hay `PGPASSFILE`,
  `DATABASE_URL` ni credenciales QA disponibles, por lo que no se modifico la
  configuracion del servidor ni se ejecuto carga sobre ese motor.
- WebKit no esta instalado en el cache de Playwright.
- NVDA no esta instalado ni disponible como comando local.
- Resend conserva valores placeholder y no hay credenciales operativas para
  validar entrega real.
- Estos puntos permanecen bloqueados por infraestructura o secretos externos,
  no por una regresion confirmada del producto.

## Carga concurrente y estabilidad sostenida

- Estado: Cubierto localmente sobre endpoints GET criticos del rol preceptor.
- Las pruebas de rendimiento masivo crean y actualizan 100 asistencias con un
  maximo de 8 consultas SQL; resultado: 2 de 2 pruebas aprobadas.
- Corrida ampliada: 2.000 solicitudes, concurrencia 40, 2.000 respuestas HTTP
  200, cero errores, 155,85 solicitudes por segundo, p95 de 723,77 ms y p99 de
  1.205,64 ms.
- Corrida sostenida: 10.000 solicitudes, concurrencia 40, 10.000 respuestas HTTP
  200, cero errores y 158,29 solicitudes por segundo durante 63,18 segundos.
- En la corrida sostenida la latencia promedio fue 251,10 ms, p95 716,26 ms,
  p99 1.214,42 ms y maximo 2.321,48 ms.
- La memoria residente aumento 1,68 MB y la memoria privada 0,94 MB; no se
  observo crecimiento evidente compatible con una fuga durante esta ventana.
- Endpoints medidos: contadores de mensajes y notificaciones, alertas academicas
  e inasistencias y cursos disponibles.
- Limite: es una linea base del servidor de desarrollo local con lecturas; no
  reemplaza una prueba de capacidad de produccion, escrituras concurrentes ni
  una prueba de varias horas.

## Accesibilidad asistida por teclado

- Estado: Cubierto en Chromium y Firefox para login, navegacion principal,
  notificaciones, mensajes y controles de branding.
- Se detecto un hallazgo de severidad media WCAG 2.4.1: el layout autenticado
  no permitia saltar directamente al contenido principal.
- Se agrego el enlace `Saltar al contenido principal`, visible al recibir foco,
  y un destino programatico en el contenido.
- Se detecto un hallazgo de severidad media: la campana de notificaciones
  eliminaba el indicador de foco del navegador.
- La campana ahora presenta un contorno visible y de alto contraste al navegar
  con teclado.
- Se detecto un hallazgo de severidad media: al cerrar con Escape el dialogo de
  lectura de un mensaje, el foco no regresaba al mensaje que lo habia abierto.
- El dialogo ahora restaura explicitamente el foco al disparador original.
- La nueva regresion valida login completo sin mouse, enlace de salto,
  indicador de foco de notificaciones, apertura y cierre de mensajes con
  restauracion de foco y nombres accesibles de controles de branding.
- Se detecto un hallazgo de severidad media: los errores de login y recuperacion
  de contrasena, y varios estados dinamicos de mensajes e importacion, eran
  visibles pero no se anunciaban semanticamente.
- Los errores ahora usan `role="alert"`, los exitos y cargas usan
  `role="status"` y los campos invalidos quedan asociados mediante
  `aria-invalid` y `aria-describedby`.
- Se detecto un hallazgo de severidad media en administracion: el encabezado
  aportado por el layout se repetia dentro de nuevo usuario, colegios e
  importacion, generando dos `h1` y saltos directos a `h3`.
- Las rutas corregidas ahora conservan un unico `h1` y una secuencia
  `h1`-`h2`-`h3`. La regresion recorre dashboard, mensajes y tres rutas
  administrativas para impedir nuevos saltos.
- Resultado ampliado: 9 de 9 pruebas aprobadas en Chromium y 9 de 9 en Firefox.
- La auditoria WCAG posterior aprobo nuevamente 7 de 7 pruebas en Chromium y 7
  de 7 en Firefox. La regresion unitaria de resiliencia de mensajes tambien
  aprobo.
- `npm run build` compilo, valido tipos y genero las 40 paginas correctamente
  con un limite de memoria explicito para Node.
- Limite: estas pruebas validan teclado, foco y semantica accesible, pero no
  sustituyen una sesion manual con NVDA, JAWS o VoiceOver. NVDA no esta
  instalado en el equipo local actual.

## Cobertura estimada

- Cobertura funcional y tecnica estimada: 93 % a 95 %.
- Resta aproximadamente 5 % a 7 %, concentrado en compatibilidad WebKit/Safari,
  una sesion manual con lector de pantalla, carga de varias horas con
  escrituras concurrentes y servicios externos reales.
- El envio de correos permanece registrado como falla esperada porque el sistema
  esta disenado pero no conectado a un proveedor de email.

## Siguiente bloque recomendado

Completar una regresion integral en WebKit/Safari cuando haya un runner
compatible. Para la pasada manual con lector debe instalarse NVDA o utilizarse
otro equipo que ya lo tenga. Mientras ese recurso no este disponible, el
siguiente bloque ejecutable es ampliar la revision de encabezados, landmarks y
anuncios dinamicos al resto de las rutas protegidas.

## Semantica ampliada de rutas protegidas

- Estado: Cubierto en Chromium y Firefox.
- Se agrego una matriz Playwright para 17 rutas de profesor, preceptor, padre y
  alumno.
- La matriz valida un unico landmark `main`, navegacion principal identificada,
  un solo `h1`, jerarquia de encabezados sin saltos y ausencia de errores
  runtime.
- El shell ya no oculta el encabezado principal para alumnos ni para el perfil
  del padre; las fichas de alumno conservan su encabezado propio.
- Se corrigieron encabezados secundarios en carga de notas, cursos, calendario,
  perfil y reportes.
- Se agregaron anuncios `status` y `alert` a resultados exitosos, cargas y
  errores representativos de perfil, cursos, alumnos, hijos, asistencia,
  reportes y carga de notas.
- El componente `CardTitle` permite elegir el nivel semantico sin cambiar su
  presentacion visual.
- Verificacion disponible: Jest 33 de 33 y TypeScript sin errores.
- Playwright no pudo iniciar Next: el sistema tenia aproximadamente 1,5 GB de
  memoria fisica y menos de 0,8 GB de memoria virtual libres. Next aborto
  durante la compilacion inicial por falta de memoria, antes de ejecutar casos.
- Reanudacion del 13 de junio de 2026: Chromium logro ejecutar la matriz y
  detecto que la ficha del alumno saltaba de `h1` a `h3`; los encabezados de
  Notas, Sanciones y Asistencias se corrigieron a `h2`.
- El detector tambien contaba un `h1` dentro de un bloque `display: none` de
  Perfil. La prueba ahora excluye elementos sin geometria renderizada.
- El caso completo de profesor aprobo 1 de 1 en Chromium despues de las
  correcciones. La ruta `/mis-hijos` del padre alcanzo a validar la ficha
  corregida, pero Next agoto memoria al compilar `/calendario`.
- El fallo posterior del alumno mostro la pagina de error de Next despues de
  `JavaScript heap out of memory`; no confirma una regresion funcional de las
  rutas del alumno.
- Verificacion posterior: Jest 33 de 33 y TypeScript sin errores.
- Se genero un build de produccion y se reutilizaron servidores estables para
  evitar la recompilacion incremental de `next dev`.
- La matriz completa aprobo 4 de 4 casos en Chromium y 4 de 4 en Firefox,
  cubriendo las 17 rutas de profesor, preceptor, padre y alumno.
- El caso de Perfil del padre tenia una expectativa obsoleta sobre el
  encabezado legacy oculto; ahora valida el `h1` visible provisto por el shell.
- Build de produccion: aprobado, con 40 paginas generadas.
- La matriz se amplio posteriormente a administracion escolar y administracion
  de plataforma: 29 rutas protegidas distribuidas en seis roles.
- Se detectaron seis componentes administrativos con un segundo `h1` y salto
  posterior a `h3`: usuarios del colegio, asignaciones de personal, cursos por
  colegio, alta de colegio, admins por colegio y backups compartian el mismo
  patron; los titulos internos ahora son `h2`.
- La matriz ampliada aprobo 6 de 6 casos en Chromium y 6 de 6 en Firefox.
- La regresion asistida de teclado, foco, anuncios y encabezados aprobo 9 de 9
  en Chromium y 9 de 9 en Firefox despues de alinear el detector de visibilidad
  con la geometria realmente renderizada.
- La cobertura se amplio a rutas dinamicas y aliases legacy resolviendo IDs de
  curso e hilo mediante las APIs del seed, sin depender de claves fijas de la
  base.
- Se detecto un salto `h1` a `h3` en el detalle de curso del profesor; los
  nombres de alumno ahora continúan la jerarquia como `h2`.
- Se detectaron dos rutas que ocultan el encabezado del shell y no aportaban un
  `h1`: alumnos por curso comenzaba en `h2` y la vista legacy de sanciones en
  `h3`. Ambas vistas ahora exponen su encabezado principal como `h1`.
- Se verifico que `/gestion_alumnos/[cursoId]` redirige correctamente a
  `/alumnos/curso/[cursoId]` antes de auditar la pagina destino.
- Resultado final de la matriz semantica: 10 de 10 casos en Chromium y 10 de 10
  en Firefox, con 35 rutas o recorridos protegidos cubiertos.

## Seguridad especializada y restaurabilidad de backups

- Estado: Cubierto localmente para SQLite, autenticacion e importacion.
- Se detecto un hallazgo de severidad alta: el backup SQLite copiaba solamente
  el archivo principal y podia omitir transacciones confirmadas que aun estaban
  en el archivo WAL.
- La generacion ahora utiliza la API nativa `sqlite3.Connection.backup`, que
  crea una instantanea consistente mientras la base permanece operativa.
- La prueba de restauracion abre el archivo descargado, ejecuta
  `PRAGMA integrity_check` y confirma que conserva datos confirmados en WAL.
- Se agregaron caminos controlados para base SQLite inexistente, motor no
  soportado, `DATABASE_URL` ausente y `pg_dump` no disponible.
- Se detecto que las tasas DRF configuradas no limitaban intentos de login
  porque `/api/token/` no tenia un throttle asignado.
- El login ahora limita intentos por combinacion de IP y usuario, con tasa
  configurable mediante `LOGIN_THROTTLE_RATE`, evitando que el ataque a una
  cuenta bloquee otras cuentas de la misma red.
- Se verificaron cookies JWT `HttpOnly`, `Secure`, `SameSite`, path, duracion y
  ausencia de tokens en el cuerpo exitoso.
- Se detecto que importacion de alumnos cargaba CSV/XLSX sin validar primero el
  tamano. Ahora rechaza anticipadamente archivos mayores al limite configurable
  `STUDENT_IMPORT_MAX_BYTES`, con valor predeterminado de 5 MB.
- La UI de backups descarga un archivo con nombre esperado, tamano no trivial y
  firma binaria `SQLite format 3` en Chromium y Firefox.
- Resultados: autenticacion, contrasenas, contexto y backups 57 de 57;
  mensajeria y notificaciones 37 de 37; alumnos 36 de 36; E2E backups 2 de 2
  en Chromium y 2 de 2 en Firefox.
- La configuracion de produccion aislada del `.env` local aprobo
  `manage.py check --deploy` sin advertencias.
- La suite backend monolitica supero el timeout local de 10 minutos; los bloques
  afectados y de alto riesgo se ejecutaron por separado y aprobaron.

## Concurrencia en firmas

- Estado: Corregido y cubierto.
- Se detecto una condicion de carrera en las firmas de notas, inasistencias y
  sanciones: dos solicitudes podian leer `firmada=false` y ambas responder 200.
- Los tres endpoints ahora reclaman la firma mediante una actualizacion
  condicional atomica `WHERE firmada=false`; solamente una solicitud puede
  modificar el registro y las restantes reciben 400.
- La prueba nueva reproduce el intercalado con dos snapshots obsoletos del
  mismo registro y confirma que solo el primero puede reclamar la firma.
- Resultado focalizado: 10 de 10 pruebas aprobadas.
- Regresion ampliada: notas 20 de 20, asistencias 28 de 28 y sanciones 17 de 17;
  total 65 de 65. `manage.py check` tambien aprobo sin observaciones.
- Riesgo pendiente: la edicion simultanea de una nota mantiene semantica de
  ultimo guardado y las respuestas de mensajes no poseen clave de idempotencia.
  Ambos casos requieren definir primero la politica de conflicto esperada.

## Idempotencia de respuestas de mensajes

- Estado: Corregido y cubierto.
- Se detecto que un timeout seguido por el fallback JSON/FormData, un reintento
  de red o dos pestañas podian crear respuestas y notificaciones duplicadas.
- `Mensaje` incorpora `client_request_id` opcional y una restriccion unica por
  remitente. Los clientes anteriores siguen siendo compatibles.
- La bandeja y la vista de hilo generan UUID por intento logico; el fallback
  JSON/FormData reutiliza exactamente la misma clave.
- El primer envio responde 201; un reintento equivalente devuelve el mismo ID
  con 200 y `deduplicated=true`, sin crear otra notificacion.
- Reutilizar una clave para contenido o destinatario diferente devuelve 409.
- La migracion `0070_mensaje_client_request_id` fue aplicada correctamente y
  `makemigrations --check` no detecto deriva.
- Resultados: mensajeria backend 38 de 38; frontend focalizado 3 de 3;
  TypeScript y `manage.py check` sin errores.
- El riesgo pendiente principal de edicion simultanea de notas fue tratado en
  el bloque siguiente.

## Concurrencia en edicion de notas

- Estado: Corregido y cubierto.
- `Nota` incorpora un contador de version que se entrega en las respuestas de
  creacion, listado y edicion.
- Cada `PATCH` exige la version leida por el cliente y actualiza mediante una
  condicion atomica por ID y version.
- La primera edicion incrementa el contador. Una segunda edicion basada en el
  mismo estado recibe HTTP 409 y la version vigente, sin sobrescribir cambios.
- La ficha del alumno envia la version, reemplaza su estado local con el registro
  vigente ante conflicto y vuelve a abrir el formulario con un aviso explicito.
- Resultados: backend de notas 21 de 21; Jest 35 de 35; TypeScript sin errores.
- El flujo E2E de edicion aprobo en Chromium y Firefox. La corrida ampliada
  encontro un `NetworkError` intermitente en otro caso de filtros bajo Firefox,
  sin relacion con la edicion concurrente.
- WebKit permanece bloqueado por la ausencia del ejecutable local ya registrada.
