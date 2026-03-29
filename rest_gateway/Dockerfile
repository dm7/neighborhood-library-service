FROM python:3.12-slim-bookworm

WORKDIR /app

COPY proto /app/proto
COPY scripts/gen_proto.sh /app/scripts/gen_proto.sh
COPY rest_gateway/pyproject.toml /app/rest_gateway/pyproject.toml
COPY rest_gateway/src/neighborhood_library_gateway /app/rest_gateway/src/neighborhood_library_gateway

RUN pip install --no-cache-dir grpcio-tools \
  && chmod +x /app/scripts/gen_proto.sh \
  && /app/scripts/gen_proto.sh \
  && pip install --no-cache-dir /app/rest_gateway

WORKDIR /app/rest_gateway

ENV PYTHONPATH=/app/rest_gateway/src

CMD ["python", "-m", "neighborhood_library_gateway"]
