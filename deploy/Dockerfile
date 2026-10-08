FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY deploy/requirements.txt /app/deploy/requirements.txt
RUN pip install --no-cache-dir -r deploy/requirements.txt
COPY vision /app/vision
COPY central /app/central
COPY licenses /app/licenses
COPY THIRD_PARTY.md /app/THIRD_PARTY.md
RUN python -m central.download_models && useradd --uid 10001 --create-home maggpie && mkdir /data && chown maggpie:maggpie /data
USER maggpie
ENV MAGGPIE_DATA_DIR=/data
EXPOSE 8010
CMD ["python", "-m", "central.server", "--host", "0.0.0.0", "--port", "8010"]
