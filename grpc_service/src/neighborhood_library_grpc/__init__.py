"""Neighborhood Library internal gRPC service package.

RPC implementations and process entry live in :mod:`neighborhood_library_grpc.server`. Protobuf modules
are generated under ``library.v1``. See ``docs/architecture.md`` for the split-runtime model.

Future: reflection service for grpcurl, interceptors (auth, metrics), pluggable repositories.
"""
