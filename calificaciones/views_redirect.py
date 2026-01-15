from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

@login_required
def post_login_redirect(request):
    u = request.user

    if u.is_superuser:
        return redirect('admin:index')

    # Profesores y Padres → al index (tu index ya muestra sus secciones)
    if u.groups.filter(name='Profesores').exists():
        return redirect('index')
    if u.groups.filter(name='Padres').exists():
        return redirect('index')

    # Preceptores → a pasar asistencia si existe, si no al index
    if u.groups.filter(name='Preceptores').exists():
        try:
            return redirect('pasar_asistencia')
        except Exception:
            return redirect('index')

    # Alumnos → a su panel actual
    if u.groups.filter(name='Alumnos').exists():
        return redirect('vista_alumno')  # /mi_panel/

    # Fallback
    return redirect('index')
