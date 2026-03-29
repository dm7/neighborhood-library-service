FROM python:3.12-slim-bookworm

WORKDIR /app

COPY proto /app/proto
COPY scripts/gen_proto.sh /app/scripts/gen_proto.sh
COPY grpc_service/pyproject.toml /app/grpc_service/pyproject.toml
COPY grpc_service/src/neighborhood_library_grpc /app/grpc_service/src/neighborhood_library_grpc

RUN pip install --no-cache-dir grpcio-tools \
  && chmod +x /app/scripts/gen_proto.sh \
  && /app/scripts/gen_proto.sh \
  && pip install --no-cache-dir /app/grpc_service

WORKDIR /app/grpc_service

ENV PYTHONPATH=/app/grpc_service/src

CMD ["python", "-m", "neighborhood_library_grpc"]
