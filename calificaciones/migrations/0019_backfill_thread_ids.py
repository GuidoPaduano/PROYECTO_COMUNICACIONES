from django.db import migrations
import uuid

def backfill_thread_ids(apps, schema_editor):
    Mensaje = apps.get_model('calificaciones', 'Mensaje')

    # Procesamos en orden ascendente para asegurar que el padre (reply_to) se vea antes que los hijos
    qs = Mensaje.objects.all().order_by('id').only('id', 'thread_id', 'reply_to_id')

    # Para no reconsultar cada vez, armamos un dict id -> (thread_id, reply_to_id)
    cache = {}

    # Primera pasada: cargamos cache existente
    for m in qs.iterator():
        cache[m.id] = [m.thread_id, m.reply_to_id]  # [thread_id, reply_to_id]

    # Segunda pasada: asignamos thread_id donde falte, propagando el del padre si existe
    updates = []
    for mid, (tid, parent_id) in cache.items():
        if tid:
            continue
        if parent_id:
            parent_tid = cache.get(parent_id, [None, None])[0]
            if parent_tid:
                new_tid = parent_tid
            else:
                # Si el padre tampoco tenía, generamos uno nuevo para el padre y lo cacheamos;
                # luego el hijo lo tomará en esta misma pasada si aún no lo tomó.
                new_tid = uuid.uuid4()
                cache[parent_id] = [new_tid, cache.get(parent_id, [None, None])[1]]
        else:
            # Mensaje "raíz" sin reply_to: nuevo hilo
            new_tid = uuid.uuid4()

        cache[mid][0] = new_tid
        updates.append((mid, new_tid))

    # Guardamos en lote (loop simple; .bulk_update no siempre está disponible en todas las versiones)
    if updates:
        # Vamos a evitar traer columnas demás
        for mid, tid in updates:
            Mensaje.objects.filter(pk=mid, thread_id__isnull=True).update(thread_id=tid)

class Migration(migrations.Migration):

    dependencies = [
        ('calificaciones', '0018_alter_mensaje_options_mensaje_reply_to_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_thread_ids, migrations.RunPython.noop),
    ]
