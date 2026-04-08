from __future__ import annotations


def get_user_group_names(user) -> tuple[str, ...]:
    try:
        if user is None or not getattr(user, "is_authenticated", False):
            return ()
    except Exception:
        return ()

    cached = getattr(user, "_cached_group_names", None)
    if cached is not None:
        return cached

    prefetched_groups = None
    try:
        prefetched_groups = getattr(user, "_prefetched_objects_cache", {}).get("groups")
    except Exception:
        prefetched_groups = None

    if prefetched_groups is not None:
        try:
            names = tuple(
                str(getattr(group, "name", "")).strip()
                for group in prefetched_groups
                if str(getattr(group, "name", "")).strip()
            )
        except Exception:
            names = ()
    else:
        try:
            names = tuple(
                str(name).strip()
                for name in user.groups.values_list("name", flat=True)
                if str(name).strip()
            )
        except Exception:
            names = ()

    try:
        setattr(user, "_cached_group_names", names)
    except Exception:
        pass
    return names


def get_user_group_names_lower(user) -> tuple[str, ...]:
    cached = getattr(user, "_cached_group_names_lower", None)
    if cached is not None:
        return cached

    lower_names = tuple(name.lower() for name in get_user_group_names(user))
    try:
        setattr(user, "_cached_group_names_lower", lower_names)
    except Exception:
        pass
    return lower_names


def user_in_groups(user, *names: str) -> bool:
    wanted = {str(name).strip() for name in names if str(name).strip()}
    if not wanted:
        return False
    return bool(wanted.intersection(get_user_group_names(user)))


def user_has_group_fragment(user, *fragments: str) -> bool:
    lowered = get_user_group_names_lower(user)
    if not lowered:
        return False
    wanted = [str(fragment).strip().lower() for fragment in fragments if str(fragment).strip()]
    if not wanted:
        return False
    return any(fragment in group_name for fragment in wanted for group_name in lowered)


def get_first_user_group_name(user, default: str = "") -> str:
    names = get_user_group_names(user)
    return names[0] if names else default
