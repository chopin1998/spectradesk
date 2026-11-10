#!/bin/sh
set -eu
cd "$(dirname "$0")"
make -s -C native
exec uv run --locked spectradesk "$@"
