import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from calificaciones.models import (
    AlertaAcademica,
    AlertaInasistencia,
    Alumno,
    Asistencia,
    Comunicado,
    Evento,
    Mensaje,
    Nota,
    Notificacion,
    Sancion,
    School,
    SchoolCourse,
)
from calificaciones.models_preceptores import PreceptorCurso, ProfesorCurso, SchoolAdmin, SchoolMembership


ROLE_GROUPS = (
    "Alumnos",
    "Padres",
    "Profesores",
    "Preceptores",
    "Directivos",
    "Administradores",
)


class Command(BaseCommand):
    help = "Seed local QA users, credentials, school data, and sample records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=os.environ.get("QA_DEFAULT_PASSWORD", "QaLocal123!"),
            help="Password for all QA users. Defaults to QA_DEFAULT_PASSWORD or QaLocal123!.",
        )
        parser.add_argument(
            "--school-slug",
            default=os.environ.get("QA_SCHOOL_SLUG", "qa-local"),
            help="School slug to create/use for QA data.",
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset passwords for existing QA users.",
        )
        parser.add_argument(
            "--reset-e2e-data",
            action="store_true",
            help="Delete accumulated E2E data for a qa-* school before rebuilding the canonical seed.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        school_slug = options["school_slug"]
        reset_passwords = options["reset_passwords"]
        reset_e2e_data = options["reset_e2e_data"]

        if reset_e2e_data:
            self._reset_e2e_data(school_slug)

        groups = self._ensure_groups()
        school = self._ensure_school(school_slug)
        course_1a = self._ensure_course(school, "1A", "1A QA", 1)
        course_2a = self._ensure_course(school, "2A", "2A QA", 2)

        users = self._ensure_users(groups, password, reset_passwords)
        self._ensure_assignments(school, course_1a, course_2a, users)
        alumnos = self._ensure_students(school, course_1a, course_2a, users)
        self._ensure_sample_records(school, course_1a, course_2a, users, alumnos)

        self.stdout.write(self.style.SUCCESS("QA local data ready."))
        self.stdout.write("")
        self.stdout.write("School:")
        self.stdout.write(f"  slug: {school.slug}")
        self.stdout.write("")
        self.stdout.write("Credentials:")
        for label, username in (
            ("Platform admin", users["platform_admin"].username),
            ("School admin", users["school_admin"].username),
            ("Directivo", users["directivo"].username),
            ("Profesor", users["profesor"].username),
            ("Preceptor", users["preceptor"].username),
            ("Padre", users["padre"].username),
            ("Alumno", users["alumno"].username),
        ):
            self.stdout.write(f"  {label}: {username} / {password}")

    def _reset_e2e_data(self, school_slug):
        if not str(school_slug or "").startswith("qa-"):
            raise CommandError("--reset-e2e-data solo puede utilizarse con colegios cuyo slug comienza con 'qa-'.")

        school = School.objects.filter(slug=school_slug).first()
        User = get_user_model()
        temporary_user_prefixes = ("qa_ui_", "qa_prof_", "qa_reset_")

        with transaction.atomic():
            if school is not None:
                for model in (
                    Notificacion,
                    AlertaInasistencia,
                    AlertaAcademica,
                    Nota,
                    Asistencia,
                    Sancion,
                    Mensaje,
                    Comunicado,
                    Evento,
                    PreceptorCurso,
                    ProfesorCurso,
                    SchoolAdmin,
                    SchoolMembership,
                ):
                    model.objects.filter(school=school).delete()
                Alumno.objects.filter(school=school).delete()
                SchoolCourse.objects.filter(school=school).delete()
                school.delete()

            temporary_users = User.objects.none()
            for prefix in temporary_user_prefixes:
                temporary_users = temporary_users | User.objects.filter(username__startswith=prefix)
            temporary_users.distinct().delete()

    def _ensure_groups(self):
        groups = {}
        for name in ROLE_GROUPS:
            groups[name], _ = Group.objects.get_or_create(name=name)
        return groups

    def _ensure_school(self, slug):
        school, _ = School.objects.update_or_create(
            slug=slug,
            defaults={
                "name": "Colegio QA Local",
                "short_name": "QA Local",
                "primary_color": "#1D4ED8",
                "accent_color": "#16A34A",
                "is_active": True,
            },
        )
        return school

    def _ensure_course(self, school, code, name, sort_order):
        course, _ = SchoolCourse.objects.update_or_create(
            school=school,
            code=code,
            defaults={
                "name": name,
                "sort_order": sort_order,
                "is_active": True,
            },
        )
        return course

    def _ensure_users(self, groups, password, reset_passwords):
        User = get_user_model()
        specs = {
            "platform_admin": {
                "username": os.environ.get("QA_PLATFORM_ADMIN_USERNAME", "qa_platform_admin"),
                "email": "qa_platform_admin@test.local",
                "first_name": "QA",
                "last_name": "Platform Admin",
                "groups": ["Administradores"],
                "is_staff": True,
                "is_superuser": True,
            },
            "school_admin": {
                "username": os.environ.get("QA_SCHOOL_ADMIN_USERNAME", "qa_school_admin"),
                "email": "qa_school_admin@test.local",
                "first_name": "QA",
                "last_name": "School Admin",
                "groups": ["Administradores"],
                "is_staff": True,
                "is_superuser": False,
            },
            "directivo": {
                "username": os.environ.get("QA_DIRECTIVO_USERNAME", "qa_directivo"),
                "email": "qa_directivo@test.local",
                "first_name": "QA",
                "last_name": "Directivo",
                "groups": ["Directivos"],
                "is_staff": True,
                "is_superuser": False,
            },
            "profesor": {
                "username": os.environ.get("QA_PROFESOR_USERNAME", "qa_profesor"),
                "email": "qa_profesor@test.local",
                "first_name": "QA",
                "last_name": "Profesor",
                "groups": ["Profesores"],
                "is_staff": True,
                "is_superuser": False,
            },
            "preceptor": {
                "username": os.environ.get("QA_PRECEPTOR_USERNAME", "qa_preceptor"),
                "email": "qa_preceptor@test.local",
                "first_name": "QA",
                "last_name": "Preceptor",
                "groups": ["Preceptores"],
                "is_staff": True,
                "is_superuser": False,
            },
            "padre": {
                "username": os.environ.get("QA_PADRE_USERNAME", "qa_padre"),
                "email": "qa_padre@test.local",
                "first_name": "QA",
                "last_name": "Padre",
                "groups": ["Padres"],
                "is_staff": False,
                "is_superuser": False,
            },
            "alumno": {
                "username": os.environ.get("QA_ALUMNO_USERNAME", "qa_alumno"),
                "email": "qa_alumno@test.local",
                "first_name": "QA",
                "last_name": "Alumno",
                "groups": ["Alumnos"],
                "is_staff": False,
                "is_superuser": False,
            },
        }

        users = {}
        for key, spec in specs.items():
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "email": spec["email"],
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "is_staff": spec["is_staff"],
                    "is_superuser": spec["is_superuser"],
                },
            )
            changed = False
            for field in ("email", "first_name", "last_name", "is_staff", "is_superuser"):
                if getattr(user, field) != spec[field]:
                    setattr(user, field, spec[field])
                    changed = True
            if created or reset_passwords:
                user.set_password(password)
                changed = True
            if changed:
                user.save()
            for group_name in spec["groups"]:
                user.groups.add(groups[group_name])
            users[key] = user
        return users

    def _ensure_assignments(self, school, course_1a, course_2a, users):
        SchoolAdmin.objects.get_or_create(school=school, admin=users["school_admin"])
        SchoolAdmin.objects.get_or_create(school=school, admin=users["platform_admin"])
        SchoolMembership.objects.get_or_create(school=school, user=users["directivo"])

        ProfesorCurso.objects.filter(
            school=school,
            profesor=users["profesor"],
        ).exclude(school_course=course_1a).delete()
        ProfesorCurso.objects.update_or_create(
            school=school,
            profesor=users["profesor"],
            curso=course_1a.code,
            defaults={"school_course": course_1a},
        )
        PreceptorCurso.objects.filter(
            school=school,
            preceptor=users["preceptor"],
        ).exclude(school_course__in=[course_1a, course_2a]).delete()
        PreceptorCurso.objects.update_or_create(
            school=school,
            preceptor=users["preceptor"],
            curso=course_1a.code,
            defaults={"school_course": course_1a},
        )
        PreceptorCurso.objects.update_or_create(
            school=school,
            preceptor=users["preceptor"],
            curso=course_2a.code,
            defaults={"school_course": course_2a},
        )

    def _ensure_students(self, school, course_1a, course_2a, users):
        alumno_1, _ = Alumno.objects.update_or_create(
            school=school,
            id_alumno="QA001",
            defaults={
                "school_course": course_1a,
                "curso": course_1a.code,
                "nombre": "Ana",
                "apellido": "QA",
                "padre": users["padre"],
                "usuario": users["alumno"],
            },
        )
        alumno_2, _ = Alumno.objects.update_or_create(
            school=school,
            id_alumno="QA002",
            defaults={
                "school_course": course_2a,
                "curso": course_2a.code,
                "nombre": "Bruno",
                "apellido": "QA",
                "padre": users["padre"],
                "usuario": None,
            },
        )
        return {"alumno_1": alumno_1, "alumno_2": alumno_2}

    def _ensure_sample(self, model, *, lookup, defaults):
        instance = model.objects.filter(**lookup).order_by("pk").first()
        if instance is None:
            return model.objects.create(**lookup, **defaults)

        changed_fields = []
        for field, value in defaults.items():
            if getattr(instance, field) != value:
                setattr(instance, field, value)
                changed_fields.append(field)
        if changed_fields:
            instance.save(update_fields=changed_fields)
        return instance

    def _ensure_sample_records(self, school, course_1a, course_2a, users, alumnos):
        today = timezone.localdate()
        alumno_1 = alumnos["alumno_1"]
        alumno_2 = alumnos["alumno_2"]

        self._ensure_sample(
            Nota,
            lookup={
                "school": school,
                "alumno": alumno_1,
                "materia": "Matem\u00e1tica",
                "tipo": "Examen",
                "fecha": today - timedelta(days=7),
            },
            defaults={
                "calificacion": "8.50",
                "nota_numerica": "8.50",
                "resultado": "TEA",
                "cuatrimestre": 1 if today.month <= 6 else 2,
                "observaciones": "Nota QA local",
            },
        )
        self._ensure_sample(
            Nota,
            lookup={
                "school": school,
                "alumno": alumno_2,
                "materia": "Lengua",
                "tipo": "Trabajo Pr\u00e1ctico",
                "fecha": today - timedelta(days=5),
            },
            defaults={
                "calificacion": "TEP",
                "resultado": "TEP",
                "cuatrimestre": 1 if today.month <= 6 else 2,
                "observaciones": "Nota QA local",
            },
        )

        self._ensure_sample(
            Asistencia,
            lookup={
                "school": school,
                "alumno": alumno_1,
                "fecha": today - timedelta(days=2),
                "tipo_asistencia": "clases",
            },
            defaults={
                "presente": True,
                "tarde": True,
                "justificada": False,
                "observacion": "Llegada tarde QA",
                "creado_por": users["preceptor"],
            },
        )
        self._ensure_sample(
            Asistencia,
            lookup={
                "school": school,
                "alumno": alumno_2,
                "fecha": today - timedelta(days=1),
                "tipo_asistencia": "clases",
            },
            defaults={
                "presente": False,
                "tarde": False,
                "justificada": True,
                "observacion": "Ausencia justificada QA",
                "creado_por": users["preceptor"],
            },
        )

        self._ensure_sample(
            Sancion,
            lookup={
                "school": school,
                "alumno": alumno_1,
                "fecha": today - timedelta(days=3),
                "motivo": "Registro QA local",
            },
            defaults={
                "tipo": "Llamado de atenci\u00f3n",
                "detalle": "Sancion de prueba para validar firma y visibilidad.",
                "docente": "QA Preceptor",
            },
        )

        self._ensure_sample(
            Evento,
            lookup={
                "school": school,
                "school_course": course_1a,
                "titulo": "Evaluacion QA",
                "fecha": today + timedelta(days=7),
            },
            defaults={
                "curso": course_1a.code,
                "descripcion": "Evento local para QA.",
                "tipo_evento": "Evaluaci\u00f3n",
                "creado_por": users["profesor"],
            },
        )

        self._ensure_sample(
            Comunicado,
            lookup={
                "school": school,
                "school_course": course_1a,
                "remitente": users["preceptor"],
                "titulo": "Comunicado QA",
            },
            defaults={
                "curso": course_1a.code,
                "contenido": "Comunicado local para validar bandeja y visibilidad.",
            },
        )

        self._ensure_sample(
            Mensaje,
            lookup={
                "school": school,
                "school_course": course_1a,
                "remitente": users["profesor"],
                "destinatario": users["padre"],
                "alumno": alumno_1,
                "asunto": "Mensaje QA a familia",
            },
            defaults={
                "curso": course_1a.code,
                "tipo_remitente": "Profesor",
                "contenido": "Mensaje local para validar inbox familiar.",
            },
        )
        self._ensure_sample(
            Mensaje,
            lookup={
                "school": school,
                "school_course": course_1a,
                "remitente": users["alumno"],
                "destinatario": users["profesor"],
                "alumno": alumno_1,
                "asunto": "Consulta QA del alumno",
            },
            defaults={
                "curso": course_1a.code,
                "tipo_remitente": "Profesor",
                "contenido": "Consulta local para validar conversacion alumno-docente.",
            },
        )

        self._ensure_sample(
            Notificacion,
            lookup={
                "school": school,
                "destinatario": users["padre"],
                "tipo": "mensaje",
                "titulo": "Notificacion QA",
            },
            defaults={
                "descripcion": "Notificacion local para validar campana.",
                "url": "/mensajes",
                "leida": False,
                "meta": {"school_course_id": course_1a.id, "alumno_id": alumno_1.id},
            },
        )
