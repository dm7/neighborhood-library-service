#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROTO_DIR="${ROOT}/proto"
OUT_GRPC="${ROOT}/grpc_service/src"
OUT_REST="${ROOT}/rest_gateway/src"

for OUT in "${OUT_GRPC}" "${OUT_REST}"; do
  python3 -m grpc_tools.protoc \
    -I"${PROTO_DIR}" \
    --python_out="${OUT}" \
    --grpc_python_out="${OUT}" \
    "${PROTO_DIR}/library/v1/library.proto"
done

mkdir -p "${OUT_GRPC}/library/v1" "${OUT_REST}/library/v1"
touch "${OUT_GRPC}/library/__init__.py" "${OUT_GRPC}/library/v1/__init__.py"
touch "${OUT_REST}/library/__init__.py" "${OUT_REST}/library/v1/__init__.py"
