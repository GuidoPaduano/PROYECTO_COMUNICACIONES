from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from .user_groups import user_in_groups

@login_required
def post_login_redirect(request):
    u = request.user

    if u.is_superuser:
        return redirect('admin:index')

    # Profesores y Padres → al index (tu index ya muestra sus secciones)
    if user_in_groups(u, 'Profesores'):
        return redirect('index')
    if user_in_groups(u, 'Padres'):
        return redirect('index')

    # Preceptores → a pasar asistencia si existe, si no al index
    if user_in_groups(u, 'Preceptores'):
        try:
            return redirect('pasar_asistencia')
        except Exception:
            return redirect('index')
    if user_in_groups(u, 'Directivos'):
        return redirect('index')

    # Alumnos → a su panel actual
    if user_in_groups(u, 'Alumnos'):
        return redirect('vista_alumno')  # /mi_panel/

    # Fallback
    return redirect('index')
