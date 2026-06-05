FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

HEALTHCHECK --interval=5m --timeout=10s --start-period=30m --retries=3 \
  CMD vwgroup-vehicle2mqtt --config /config/config.json --healthcheck

ENTRYPOINT ["vwgroup-vehicle2mqtt"]
CMD ["--config", "/config/config.json"]
