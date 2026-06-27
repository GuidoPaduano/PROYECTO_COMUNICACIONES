DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def paginate_queryset(qs, request, default_size=DEFAULT_PAGE_SIZE):
    """
    Aplica paginación a un queryset usando ?page y ?page_size de la request.
    Retorna (items, meta_dict).
    """
    try:
        page = max(1, int(request.GET.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        size = min(max(1, int(request.GET.get("page_size", default_size))), MAX_PAGE_SIZE)
    except (ValueError, TypeError):
        size = default_size

    total = qs.count()
    total_pages = max(1, (total + size - 1) // size)
    page = min(page, total_pages)

    start = (page - 1) * size
    items = qs[start : start + size]

    return items, {
        "page": page,
        "page_size": size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }
