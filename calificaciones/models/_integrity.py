from django.core.exceptions import ValidationError

from ._school import School, SchoolCourse, resolve_school_course_for_value


def _get_single_school_fallback():
    try:
        active = list(School.objects.filter(is_active=True).order_by("id")[:2])
        if len(active) == 1:
            return active[0]
        if active:
            return None
        schools = list(School.objects.order_by("id")[:2])
        if len(schools) == 1:
            return schools[0]
    except Exception:
        return None
    return None


def _collect_related_school_candidates(instance, related_fields):
    candidates = []
    seen = set()
    for field_name in related_fields or ():
        if not hasattr(instance, field_name):
            continue
        related = getattr(instance, field_name, None)
        if related is None:
            continue
        school = getattr(related, "school", None)
        if school is None:
            nested_alumno = getattr(related, "alumno", None)
            school = getattr(nested_alumno, "school", None)
        if school is None:
            continue
        school_id = getattr(school, "id", None)
        if school_id is None or school_id in seen:
            continue
        seen.add(school_id)
        candidates.append(school)
    return candidates


def _should_enforce_school_integrity(instance, kwargs, tracked_fields):
    if getattr(instance._state, "adding", False):
        return True
    update_fields = kwargs.get("update_fields")
    if update_fields is None:
        return True
    return bool(set(update_fields).intersection(set(tracked_fields)))


def _mark_update_field(kwargs, field_name: str):
    update_fields = kwargs.get("update_fields")
    if update_fields is None:
        return
    update_fields_set = set(update_fields)
    update_fields_set.add(field_name)
    kwargs["update_fields"] = list(update_fields_set)


def sync_school_course_fields(instance, *, field_name: str = "school_course", school_attr: str = "school", code_attr: str = "curso"):
    school = getattr(instance, school_attr, None)
    school_course = getattr(instance, field_name, None)
    course_code = str(getattr(instance, code_attr, "") or "").strip().upper()

    if school_course is not None:
        if school is None:
            setattr(instance, school_attr, school_course.school)
            school = school_course.school

        if course_code and course_code != str(getattr(school_course, "code", "") or "").strip().upper():
            resolved = resolve_school_course_for_value(school=school or school_course.school, curso=course_code)
            setattr(instance, field_name, resolved)
            if resolved is not None:
                setattr(instance, code_attr, resolved.code)
            return

        if school is not None and getattr(school_course, "school_id", None) != getattr(school, "id", None):
            resolved = resolve_school_course_for_value(school=school, curso=course_code or getattr(school_course, "code", ""))
            setattr(instance, field_name, resolved)
            if resolved is not None:
                setattr(instance, code_attr, resolved.code)
            return

        setattr(instance, code_attr, getattr(school_course, "code", "") or course_code)
        return

    if school is None or not course_code:
        return

    resolved = resolve_school_course_for_value(school=school, curso=course_code)
    if resolved is not None:
        setattr(instance, field_name, resolved)
        setattr(instance, code_attr, resolved.code)


def sync_school_course_for_save(instance, kwargs, *, field_name: str = "school_course", school_attr: str = "school", code_attr: str = "curso"):
    update_fields = kwargs.get("update_fields")

    if update_fields is None:
        sync_school_course_fields(instance, field_name=field_name, school_attr=school_attr, code_attr=code_attr)
        return

    tracked_fields = {field_name, school_attr, code_attr}
    update_fields_set = set(update_fields)
    if not update_fields_set.intersection(tracked_fields):
        return

    before_ids = {
        school_attr: getattr(instance, f"{school_attr}_id", None),
        field_name: getattr(instance, f"{field_name}_id", None),
    }
    before_values = {code_attr: getattr(instance, code_attr, None)}

    sync_school_course_fields(instance, field_name=field_name, school_attr=school_attr, code_attr=code_attr)

    if getattr(instance, f"{school_attr}_id", None) != before_ids[school_attr]:
        update_fields_set.add(school_attr)
    if getattr(instance, f"{field_name}_id", None) != before_ids[field_name]:
        update_fields_set.add(field_name)
    if getattr(instance, code_attr, None) != before_values[code_attr]:
        update_fields_set.add(code_attr)

    kwargs["update_fields"] = list(update_fields_set)


def ensure_school_for_save(instance, kwargs, *, related_fields=(), required_on_create: bool = True):
    tracked_fields = {"school", *set(related_fields or ())}
    if not _should_enforce_school_integrity(instance, kwargs, tracked_fields):
        return

    before_school_id = getattr(instance, "school_id", None)
    school = getattr(instance, "school", None)
    candidates = _collect_related_school_candidates(instance, related_fields)

    if school is None and len(candidates) == 1:
        setattr(instance, "school", candidates[0])
        school = candidates[0]

    if school is None and getattr(instance._state, "adding", False):
        fallback = _get_single_school_fallback()
        if fallback is not None:
            setattr(instance, "school", fallback)
            school = fallback

    after_school_id = getattr(instance, "school_id", None) or getattr(school, "id", None)
    if before_school_id != after_school_id:
        _mark_update_field(kwargs, "school")

    if after_school_id is not None:
        for candidate in candidates:
            candidate_id = getattr(candidate, "id", None)
            if candidate_id is not None and candidate_id != after_school_id:
                raise ValidationError("El colegio no coincide con la relacion asociada.")

    if required_on_create and getattr(instance._state, "adding", False):
        current_school = getattr(instance, "school", None)
        if getattr(instance, "school_id", None) is None and getattr(current_school, "id", None) is None:
            raise ValidationError("Debe indicarse el colegio para nuevas altas.")


def ensure_school_course_for_save(instance, kwargs, *, field_name: str = "school_course", school_attr: str = "school", code_attr: str = "curso"):
    tracked_fields = {field_name, school_attr, code_attr}
    if not _should_enforce_school_integrity(instance, kwargs, tracked_fields):
        return

    before_school_id = getattr(instance, f"{school_attr}_id", None)
    school = getattr(instance, school_attr, None)
    school_course = getattr(instance, field_name, None)

    if school is None and school_course is not None and getattr(school_course, "school", None) is not None:
        setattr(instance, school_attr, school_course.school)
        school = school_course.school

    if school is None and getattr(instance._state, "adding", False):
        fallback = _get_single_school_fallback()
        if fallback is not None:
            setattr(instance, school_attr, fallback)
            school = fallback

    if before_school_id != (getattr(instance, f"{school_attr}_id", None) or getattr(school, "id", None)):
        _mark_update_field(kwargs, school_attr)

    sync_school_course_for_save(instance, kwargs, field_name=field_name, school_attr=school_attr, code_attr=code_attr)

    school = getattr(instance, school_attr, None)
    school_id = getattr(instance, f"{school_attr}_id", None) or getattr(school, "id", None)
    school_course = getattr(instance, field_name, None)
    course_code = str(getattr(instance, code_attr, "") or "").strip().upper()

    if getattr(instance._state, "adding", False) and school_id is None:
        raise ValidationError("Debe indicarse el colegio para nuevas altas.")

    if school_course is not None and school_id is not None and getattr(school_course, "school_id", None) != school_id:
        raise ValidationError("El curso asignado no pertenece al colegio indicado.")

    if school_id is not None and course_code and school_course is None:
        raise ValidationError(f"No existe un curso '{course_code}' para el colegio indicado.")
