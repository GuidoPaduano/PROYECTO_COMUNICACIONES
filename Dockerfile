# Usa una imagen oficial de Python
FROM python:3.11-slim

# Establece el directorio de trabajo
WORKDIR /app

# Copia los archivos del proyecto
COPY . .

# Instala dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Expone el puerto (por defecto en Railway es 8000)
EXPOSE 8000

# Comando de inicio
CMD ["sh", "-c", "python manage.py migrate && python manage.py collectstatic --noinput && gunicorn boletin.wsgi:application --bind 0.0.0.0:8000"]
