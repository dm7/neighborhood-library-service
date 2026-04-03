#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROTO_DIR="${ROOT}/proto"
OUT_GRPC="${ROOT}/grpc_service/src"
OUT_REST="${ROOT}/rest_gateway/src"

PROTO_PYTHON="${PROTO_PYTHON:-python3}"
if [[ -x "${ROOT}/grpc_service/.venv/bin/python" ]]; then
  PROTO_PYTHON="${ROOT}/grpc_service/.venv/bin/python"
fi
if ! "${PROTO_PYTHON}" -c "import grpc_tools.protoc" 2>/dev/null; then
  echo "gen_proto.sh: grpc_tools not found for: ${PROTO_PYTHON}" >&2
  echo "Install once:  cd grpc_service && python3 -m venv .venv && .venv/bin/pip install -e ." >&2
  echo "Or globally:   pip install grpcio-tools" >&2
  exit 1
fi

for OUT in "${OUT_GRPC}" "${OUT_REST}"; do
  if [[ ! -d "${OUT}" ]]; then
    continue
  fi
  "${PROTO_PYTHON}" -m grpc_tools.protoc \
    -I"${PROTO_DIR}" \
    --python_out="${OUT}" \
    --grpc_python_out="${OUT}" \
    "${PROTO_DIR}/library/v1/library.proto"
done

if [[ -d "${OUT_GRPC}" ]]; then
  mkdir -p "${OUT_GRPC}/library/v1"
  touch "${OUT_GRPC}/library/__init__.py" "${OUT_GRPC}/library/v1/__init__.py"
fi
if [[ -d "${OUT_REST}" ]]; then
  mkdir -p "${OUT_REST}/library/v1"
  touch "${OUT_REST}/library/__init__.py" "${OUT_REST}/library/v1/__init__.py"
fi
