from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

ALL_COURSE_MARKERS = ("ALL", "TODOS", "*")


@dataclass(frozen=True)
class CourseRef:
    school_id: int | None = None
    school_course_id: int | None = None
    course_code: str = ""


def normalize_course_code(value) -> str:
    return str(value or "").strip().upper()


def get_object_school_id(obj, *, school_attr: str = "school") -> int | None:
    if obj is None:
        return None
    school_id = getattr(obj, f"{school_attr}_id", None)
    if school_id is not None:
        return school_id
    school = getattr(obj, school_attr, None)
    return getattr(school, "id", None) if school is not None else None


def get_object_school_course_id(obj, *, school_course_attr: str = "school_course") -> int | None:
    if obj is None:
        return None
    school_course_id = getattr(obj, f"{school_course_attr}_id", None)
    if school_course_id is not None:
        return school_course_id
    school_course = getattr(obj, school_course_attr, None)
    return getattr(school_course, "id", None) if school_course is not None else None


def get_object_course_code(obj, *, code_attr: str = "curso", school_course_attr: str = "school_course") -> str:
    if obj is None:
        return ""
    school_course = getattr(obj, school_course_attr, None)
    school_course_code = getattr(school_course, "code", None) if school_course is not None else None
    return normalize_course_code(school_course_code or getattr(obj, code_attr, None))


def build_course_ref(
    *,
    obj=None,
    school=None,
    school_id: int | None = None,
    school_course_id: int | None = None,
    course_code: str | None = None,
    school_course_attr: str = "school_course",
    code_attr: str = "curso",
) -> CourseRef:
    if obj is not None:
        school_id = get_object_school_id(obj)
        school_course_id = get_object_school_course_id(obj, school_course_attr=school_course_attr)
        course_code = get_object_course_code(obj, code_attr=code_attr, school_course_attr=school_course_attr)
    elif school is not None and school_id is None:
        school_id = getattr(school, "id", None)
    return CourseRef(
        school_id=school_id,
        school_course_id=school_course_id,
        course_code=normalize_course_code(course_code),
    )


def course_ref_matches(
    refs,
    *,
    obj=None,
    school=None,
    school_id: int | None = None,
    school_course_id: int | None = None,
    course_code: str | None = None,
    school_course_attr: str = "school_course",
    code_attr: str = "curso",
) -> bool:
    target = build_course_ref(
        obj=obj,
        school=school,
        school_id=school_id,
        school_course_id=school_course_id,
        course_code=course_code,
        school_course_attr=school_course_attr,
        code_attr=code_attr,
    )
    if target.school_course_id is not None:
        for ref in refs or []:
            if ref.school_course_id == target.school_course_id:
                return True
    if not target.course_code:
        return False
    for ref in refs or []:
        if ref.course_code != target.course_code:
            continue
        if target.school_id is not None and ref.school_id is not None and ref.school_id != target.school_id:
            continue
        if target.school_course_id is None or ref.school_course_id is None:
            return True
    return False


def get_assignment_course_refs(qs) -> list[CourseRef]:
    out = []
    seen = set()
    try:
        rows = qs.values_list("school_id", "school_course_id", "school_course__code", "curso")
        with_school = True
    except Exception:
        try:
            rows = qs.values_list("school_course_id", "school_course__code", "curso")
            with_school = False
        except Exception:
            rows = []
            with_school = False

    for row in rows:
        if with_school:
            school_id, school_course_id, school_course_code, curso = row
        else:
            school_id = None
            school_course_id, school_course_code, curso = row
        ref = CourseRef(
            school_id=int(school_id) if school_id is not None else None,
            school_course_id=int(school_course_id) if school_course_id is not None else None,
            course_code=normalize_course_code(school_course_code or curso),
        )
        key = (ref.school_id, ref.school_course_id, ref.course_code)
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return out


def filter_course_options_by_refs(options, refs):
    if not refs:
        return []

    allowed_ids = {
        ref.school_course_id
        for ref in refs
        if getattr(ref, "school_course_id", None) is not None
    }
    allowed_codes = {
        normalize_course_code(getattr(ref, "course_code", ""))
        for ref in refs
        if normalize_course_code(getattr(ref, "course_code", ""))
    }

    out = []
    for option in options or []:
        if isinstance(option, dict):
            option_id = option.get("school_course_id")
            option_code = option.get("code") or option.get("id") or option.get("curso")
        elif isinstance(option, (list, tuple)) and option:
            option_id = None
            option_code = option[0]
        else:
            option_id = None
            option_code = option

        if option_id in allowed_ids or normalize_course_code(option_code) in allowed_codes:
            out.append(option)
    return out


def build_assignment_course_q(
    *,
    obj=None,
    school=None,
    school_id: int | None = None,
    school_course_id: int | None = None,
    course_code: str | None = None,
    assignment_school_field: str = "school",
    assignment_school_course_field: str = "school_course",
    assignment_code_field: str = "curso",
    include_null_school: bool = True,
):
    if obj is not None:
        school_id = get_object_school_id(obj)
        school_course_id = get_object_school_course_id(obj)
        course_code = get_object_course_code(obj)
    elif school is not None and school_id is None:
        school_id = getattr(school, "id", None)

    normalized_code = normalize_course_code(course_code)
    query = Q()
    has_clause = False

    if school_course_id is not None:
        query |= Q(**{f"{assignment_school_course_field}_id": school_course_id})
        has_clause = True

    if normalized_code:
        code_query = Q(**{assignment_code_field: normalized_code})
        if school_id is not None:
            school_query = Q(**{f"{assignment_school_field}_id": school_id})
            if include_null_school:
                school_query |= Q(**{f"{assignment_school_field}__isnull": True})
            code_query &= school_query
        query |= code_query
        has_clause = True

    if not has_clause:
        return None
    return query


def filter_assignments_for_course(
    qs,
    *,
    obj=None,
    school=None,
    school_id: int | None = None,
    school_course_id: int | None = None,
    course_code: str | None = None,
    assignment_school_field: str = "school",
    assignment_school_course_field: str = "school_course",
    assignment_code_field: str = "curso",
    include_null_school: bool = True,
):
    course_q = build_assignment_course_q(
        obj=obj,
        school=school,
        school_id=school_id,
        school_course_id=school_course_id,
        course_code=course_code,
        assignment_school_field=assignment_school_field,
        assignment_school_course_field=assignment_school_course_field,
        assignment_code_field=assignment_code_field,
        include_null_school=include_null_school,
    )
    if course_q is None:
        return qs.none()
    return qs.filter(course_q)


def filter_assignments_for_course_refs(
    qs,
    refs,
    *,
    assignment_school_field: str = "school",
    assignment_school_course_field: str = "school_course",
    assignment_code_field: str = "curso",
    include_null_school: bool = True,
):
    course_q = build_assignment_course_q_for_refs(
        refs,
        assignment_school_field=assignment_school_field,
        assignment_school_course_field=assignment_school_course_field,
        assignment_code_field=assignment_code_field,
        include_null_school=include_null_school,
    )
    if course_q is None:
        return qs.none()
    return qs.filter(course_q)


def assignment_matches_course(qs, **kwargs) -> bool:
    try:
        return filter_assignments_for_course(qs, **kwargs).exists()
    except Exception:
        return False


def get_assignment_school_course_ids(qs) -> list[int]:
    out = []
    seen = set()
    for ref in get_assignment_course_refs(qs):
        course_id = getattr(ref, "school_course_id", None)
        if course_id is None or course_id in seen:
            continue
        seen.add(course_id)
        out.append(int(course_id))
    return out


def build_course_lookup_keys(
    *,
    school_id: int | None = None,
    school_course_id: int | None = None,
    course_code: str | None = None,
) -> list[tuple[int | None, int | None, str]]:
    normalized_code = normalize_course_code(course_code)
    keys = []

    if school_course_id is not None:
        keys.append((school_course_id, school_id, normalized_code))
        keys.append((school_course_id, None, normalized_code))
    if school_id is not None and normalized_code:
        keys.append((None, school_id, normalized_code))
    if normalized_code:
        keys.append((None, None, normalized_code))

    out = []
    seen = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def build_course_lookup_keys_for_refs(refs) -> list[tuple[int | None, int | None, str]]:
    out = []
    seen = set()
    for ref in refs or []:
        for key in build_course_lookup_keys(
            school_id=getattr(ref, "school_id", None),
            school_course_id=getattr(ref, "school_course_id", None),
            course_code=getattr(ref, "course_code", None),
        ):
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def get_object_course_lookup_keys(obj) -> list[tuple[int | None, int | None, str]]:
    if obj is None:
        return []
    return build_course_lookup_keys(
        school_id=get_object_school_id(obj),
        school_course_id=get_object_school_course_id(obj),
        course_code=get_object_course_code(obj),
    )


def build_course_membership_q(
    *,
    school_course_id: int | None = None,
    course_code: str | None = None,
    school_course_field: str = "school_course",
    code_field: str = "curso",
    include_all_markers: bool = False,
):
    normalized_code = normalize_course_code(course_code)
    query = Q()
    has_clause = False

    if school_course_id is not None:
        query |= Q(**{f"{school_course_field}_id": school_course_id})
        has_clause = True

    if normalized_code:
        query |= Q(**{code_field: normalized_code})
        has_clause = True

    if include_all_markers:
        for marker in ALL_COURSE_MARKERS:
            query |= Q(**{f"{code_field}__iexact": marker})
        has_clause = True

    if not has_clause:
        return None
    return query


def build_assignment_course_q_for_refs(
    refs,
    *,
    assignment_school_field: str = "school",
    assignment_school_course_field: str = "school_course",
    assignment_code_field: str = "curso",
    include_null_school: bool = True,
):
    query = Q()
    has_clause = False
    for ref in refs or []:
        ref_q = build_assignment_course_q(
            school_id=getattr(ref, "school_id", None),
            school_course_id=getattr(ref, "school_course_id", None),
            course_code=getattr(ref, "course_code", None),
            assignment_school_field=assignment_school_field,
            assignment_school_course_field=assignment_school_course_field,
            assignment_code_field=assignment_code_field,
            include_null_school=include_null_school,
        )
        if ref_q is None:
            continue
        query |= ref_q
        has_clause = True
    if not has_clause:
        return None
    return query


def build_course_membership_q_for_refs(
    refs,
    *,
    school_course_field: str = "school_course",
    code_field: str = "curso",
    school_field: str | None = None,
    include_all_markers: bool = False,
):
    query = Q()
    has_clause = False

    for ref in refs or []:
        ref_q = Q()
        ref_has_clause = False
        school_course_id = getattr(ref, "school_course_id", None)
        school_id = getattr(ref, "school_id", None)
        course_code = normalize_course_code(getattr(ref, "course_code", ""))

        if school_course_id is not None:
            ref_q |= Q(**{f"{school_course_field}_id": school_course_id})
            ref_has_clause = True

        if course_code:
            code_q = Q(**{code_field: course_code})
            if school_field and school_id is not None:
                code_q &= Q(**{f"{school_field}_id": school_id})
            ref_q |= code_q
            ref_has_clause = True

        if ref_has_clause:
            query |= ref_q
            has_clause = True

    if include_all_markers:
        for marker in ALL_COURSE_MARKERS:
            query |= Q(**{f"{code_field}__iexact": marker})
        has_clause = True

    if not has_clause:
        return None
    return query


def filter_queryset_for_course_membership(qs, **kwargs):
    course_q = build_course_membership_q(**kwargs)
    if course_q is None:
        return qs.none()
    return qs.filter(course_q)
