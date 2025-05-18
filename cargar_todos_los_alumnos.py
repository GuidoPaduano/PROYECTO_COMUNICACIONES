import csv
import os
from calificaciones.models import Alumno

def normalizar_curso(nombre_archivo):
    nombre = os.path.basename(nombre_archivo).lower()
    if "1a" in nombre: return "1A"
    if "1b" in nombre: return "1B"
    if "2a" in nombre: return "2A"
    if "2b" in nombre: return "2B"
    if "3a" in nombre: return "3A"
    if "3b" in nombre: return "3B"
    if "4e" in nombre: return "4ECO"
    if "4n" in nombre: return "4NAT"
    if "5e" in nombre: return "5ECO"
    if "5n" in nombre: return "5NAT"
    if "6e" in nombre: return "6ECO"
    if "6n" in nombre: return "6NAT"
    return None

def run():
    archivos = [f for f in os.listdir() if f.endswith(".csv") and "libretas" in f.lower()]
    if not archivos:
        print("❌ No se encontraron archivos CSV.")
        return

    for archivo in archivos:
        curso = normalizar_curso(archivo)
        if not curso:
            print(f"⚠️ Curso no detectado en archivo: {archivo}")
            continue

        print(f"\n📥 Procesando curso {curso} desde {archivo}...")

        with open(archivo, newline='', encoding='utf-8', errors='replace') as f:
            lector = csv.reader(f)
            next(lector)  # saltear encabezado

            contador = 1
            for fila in lector:
                if len(fila) < 2:
                    continue
                nombre = fila[1].strip()
                if not nombre:
                    continue

                id_alumno = f"{curso}{contador:03}"
                Alumno.objects.create(
                    nombre=nombre,
                    id_alumno=id_alumno,
                    curso=curso,
                    padre=None
                )
                print(f"✅ {nombre} agregado como {id_alumno}")
                contador += 1

