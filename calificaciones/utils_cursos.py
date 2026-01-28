# calificaciones/utils_cursos.py

VALID_CURSOS = [
    "1A",
    "1B",
    "2A",
    "2B",
    "3A",
    "3B",
    "4ECO",
    "4NAT",
    "5ECO",
    "5NAT",
    "6ECO",
    "6NAT",
]

VALID_CURSOS_SET = set(VALID_CURSOS)


def _normalize_curso_id(value) -> str:
    return str(value or "").strip().upper()


def is_curso_valido(value) -> bool:
    return _normalize_curso_id(value) in VALID_CURSOS_SET


def filtrar_cursos_validos(cursos):
    """Filtra listas de cursos (tuplas, dicts o strings) segun el whitelist."""
    out = []
    for c in cursos or []:
        if isinstance(c, dict):
            cid = c.get("id") or c.get("value") or c.get("curso") or c.get("codigo")
        elif isinstance(c, (list, tuple)) and c:
            cid = c[0]
        else:
            cid = c
        if is_curso_valido(cid):
            out.append(c)
    return out
