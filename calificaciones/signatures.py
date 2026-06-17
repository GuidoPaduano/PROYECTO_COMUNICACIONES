from django.utils import timezone


def claim_signature(instance, *, user, signed_at=None) -> bool:
    signed_at = signed_at or timezone.now()
    updated = type(instance)._default_manager.filter(
        pk=instance.pk,
        firmada=False,
    ).update(
        firmada=True,
        firmada_en=signed_at,
        firmada_por=user,
    )

    if updated == 0:
        instance.refresh_from_db(fields=["firmada", "firmada_en", "firmada_por"])
        return False

    instance.firmada = True
    instance.firmada_en = signed_at
    instance.firmada_por = user
    return True
