# Usa una imagen oficial de Python
FROM python:3.11-slim

# Optimizaciones: menos IO y logs más claros
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias primero para aprovechar cache de Docker
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del proyecto
COPY . ./

# Expone el puerto (por defecto en Railway es 8000)
EXPOSE 8000

# Comando de inicio: solo arranca Gunicorn
CMD ["gunicorn", "boletin.wsgi:application", "--bind", "0.0.0.0:8000"]



