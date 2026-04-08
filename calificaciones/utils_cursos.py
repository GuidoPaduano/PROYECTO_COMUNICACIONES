from __future__ import annotations

from typing import Iterable, Optional

from django.core.cache import cache


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
ALL_COURSE_MARKERS = {"ALL", "TODOS", "*"}
COURSE_CATALOG_CACHE_TTL = 300


def _normalize_curso_id(value) -> str:
    return str(value or "").strip().upper()


def parse_school_course_id(value) -> Optional[int]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _school_cache_key_fragment(school) -> str:
    school_id = getattr(school, "id", None)
    if school_id is None:
        return "none"
    school_slug = str(getattr(school, "slug", "") or "").strip().lower()
    if school_slug:
        return f"{school_id}:{school_slug}"
    return str(school_id)


def _course_choices_cache_key(
    *,
    school=None,
    include_inactive: bool = False,
    fallback_to_defaults: bool = True,
    catalog_only: bool = False,
) -> str:
    return ":".join(
        [
            "course_choices",
            f"school:{_school_cache_key_fragment(school)}",
            f"inactive:{int(include_inactive)}",
            f"fallback:{int(fallback_to_defaults)}",
            f"catalog:{int(catalog_only)}",
        ]
    )


def _course_dicts_cache_key(
    *,
    school=None,
    include_inactive: bool = False,
    fallback_to_defaults: bool = True,
    catalog_only: bool = False,
) -> str:
    return ":".join(
        [
            "course_dicts",
            f"school:{_school_cache_key_fragment(school)}",
            f"inactive:{int(include_inactive)}",
            f"fallback:{int(fallback_to_defaults)}",
            f"catalog:{int(catalog_only)}",
        ]
    )


def _fallback_course_choices() -> list[tuple[str, str]]:
    try:
        from .models import Alumno

        fallback_rows = list(getattr(Alumno, "CURSOS", []) or [])
        if fallback_rows:
            return [(str(code), str(name)) for code, name in fallback_rows]
    except Exception:
        pass
    return [(code, code) for code in VALID_CURSOS]


def _course_choices_from_codes(codes: Iterable[str]) -> list[tuple[str, str]]:
    labels = {str(code): str(name) for code, name in _fallback_course_choices()}
    out = []
    seen = set()
    for raw_code in codes or []:
        code = _normalize_curso_id(raw_code)
        if not code or code in seen:
            continue
        seen.add(code)
        out.append((code, labels.get(code, code)))
    return out


def _db_course_choices_for_school(school=None) -> list[tuple[str, str]]:
    if school is None:
        return []

    from .models import Alumno

    codes = set(
        _normalize_curso_id(curso)
        for curso in Alumno.objects.filter(school=school).values_list("curso", flat=True)
        if _normalize_curso_id(curso)
    )

    try:
        from .models_preceptores import PreceptorCurso, ProfesorCurso

        codes.update(
            _normalize_curso_id(curso)
            for curso in PreceptorCurso.objects.filter(school=school).values_list("curso", flat=True)
            if _normalize_curso_id(curso)
        )
        codes.update(
            _normalize_curso_id(curso)
            for curso in ProfesorCurso.objects.filter(school=school).values_list("curso", flat=True)
            if _normalize_curso_id(curso)
        )
    except Exception:
        pass

    return _course_choices_from_codes(sorted(codes))


def get_school_course_choices(
    school=None,
    include_inactive: bool = False,
    fallback_to_defaults: bool = True,
    catalog_only: bool = False,
) -> list[tuple[str, str]]:
    cache_key = _course_choices_cache_key(
        school=school,
        include_inactive=include_inactive,
        fallback_to_defaults=fallback_to_defaults,
        catalog_only=catalog_only,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return list(cached)

    rows: list[tuple[str, str]] = []
    try:
        from .models import SchoolCourse

        if school is not None:
            qs = SchoolCourse.objects.filter(school=school)
            if not include_inactive:
                qs = qs.filter(is_active=True)
            rows = [(str(code), str(name)) for code, name in qs.values_list("code", "name")]
    except Exception:
        rows = []

    if rows:
        cache.set(cache_key, rows, COURSE_CATALOG_CACHE_TTL)
        return rows

    if catalog_only:
        cache.set(cache_key, [], COURSE_CATALOG_CACHE_TTL)
        return []

    rows = _db_course_choices_for_school(school)
    if rows:
        cache.set(cache_key, rows, COURSE_CATALOG_CACHE_TTL)
        return rows

    if fallback_to_defaults:
        rows = _fallback_course_choices()
        cache.set(cache_key, rows, COURSE_CATALOG_CACHE_TTL)
        return rows

    cache.set(cache_key, [], COURSE_CATALOG_CACHE_TTL)
    return []


def get_school_course_by_id(course_id, school=None, include_inactive: bool = True):
    parsed_id = parse_school_course_id(course_id)
    if parsed_id is None:
        return None

    try:
        from .models import SchoolCourse

        qs = SchoolCourse.objects.filter(pk=parsed_id)
        if school is not None:
            qs = qs.filter(school=school)
        if not include_inactive:
            qs = qs.filter(is_active=True)
        return qs.first()
    except Exception:
        return None


def get_school_course_dicts(
    school=None,
    include_inactive: bool = False,
    fallback_to_defaults: bool = True,
    catalog_only: bool = False,
) -> list[dict]:
    cache_key = _course_dicts_cache_key(
        school=school,
        include_inactive=include_inactive,
        fallback_to_defaults=fallback_to_defaults,
        catalog_only=catalog_only,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return list(cached)

    rows = []
    try:
        from .models import SchoolCourse

        if school is not None:
            qs = SchoolCourse.objects.filter(school=school)
            if not include_inactive:
                qs = qs.filter(is_active=True)
            rows = [
                {
                    "id": str(code),
                    "nombre": str(name),
                    "school_course_id": int(course_id),
                }
                for course_id, code, name in qs.values_list("id", "code", "name")
            ]
    except Exception:
        rows = []

    if rows:
        cache.set(cache_key, rows, COURSE_CATALOG_CACHE_TTL)
        return rows

    rows = [
        {"id": code, "nombre": name}
        for code, name in get_school_course_choices(
            school=school,
            include_inactive=include_inactive,
            fallback_to_defaults=fallback_to_defaults,
            catalog_only=catalog_only,
        )
    ]
    cache.set(cache_key, rows, COURSE_CATALOG_CACHE_TTL)
    return rows


def get_course_label(value, school=None) -> str:
    code = _normalize_curso_id(value)
    if not code:
        return ""
    for item_code, item_name in get_school_course_choices(school=school):
        if _normalize_curso_id(item_code) == code:
            return item_name
    return code


def resolve_course_reference(
    *,
    school=None,
    raw_course=None,
    raw_school_course_id=None,
    required: bool = False,
    allow_all_markers: bool = False,
    include_inactive: bool = True,
    deprecated_course_error: str | None = None,
):
    course_code = _normalize_curso_id(raw_course)
    school_course = get_school_course_by_id(
        raw_school_course_id,
        school=school,
        include_inactive=include_inactive,
    )

    if raw_school_course_id not in (None, "", []) and school_course is None:
        return None, "", "school_course_id inválido."

    if school_course is not None:
        resolved_code = _normalize_curso_id(getattr(school_course, "code", ""))
        if course_code:
            if allow_all_markers and course_code in ALL_COURSE_MARKERS:
                return None, "", "No podés combinar school_course_id con un curso global."
            if course_code != resolved_code:
                return None, "", "El school_course_id no coincide con el curso enviado."
        return school_course, resolved_code, None

    if course_code:
        if allow_all_markers and course_code in ALL_COURSE_MARKERS:
            return None, course_code, None
        return None, "", (
            deprecated_course_error
            or "El parámetro 'curso' está deprecado en este endpoint. Usa school_course_id."
        )

    if required:
        return None, "", "Falta el campo requerido: school_course_id o curso."

    return None, "", None


def is_curso_valido(value, school=None) -> bool:
    code = _normalize_curso_id(value)
    if not code:
        return False
    dynamic = get_school_course_choices(school=school, fallback_to_defaults=False)
    if dynamic:
        return code in {_normalize_curso_id(item_code) for item_code, _ in dynamic}
    return code in VALID_CURSOS_SET


def filtrar_cursos_validos(cursos, school=None):
    """Filtra listas de cursos (tuplas, dicts o strings) segun el catalogo disponible."""
    valid_ids = {
        _normalize_curso_id(code)
        for code, _name in get_school_course_choices(school=school)
    }
    out = []
    for c in cursos or []:
        if isinstance(c, dict):
            cid = c.get("id") or c.get("value") or c.get("curso") or c.get("codigo")
        elif isinstance(c, (list, tuple)) and c:
            cid = c[0]
        else:
            cid = c
        if _normalize_curso_id(cid) in valid_ids:
            out.append(c)
    return out
