#!/usr/bin/env bash
set -euo pipefail

benchmark_dir="vendor/quanbench-plus"
commit="2dfd1a863b13d3762a734ed96742adb39e65e34b"
url="https://github.com/JawadKotaichh/quanbench-plus.git"

if [ -d "$benchmark_dir/.git" ]; then
  actual="$(git -C "$benchmark_dir" rev-parse HEAD)"
  if [ "$actual" = "$commit" ]; then
    exit 0
  fi
  echo "Existing benchmark checkout has commit $actual; expected $commit" >&2
  exit 1
fi

mkdir -p vendor
git clone "$url" "$benchmark_dir"
git -C "$benchmark_dir" checkout "$commit"
actual="$(git -C "$benchmark_dir" rev-parse HEAD)"
[ "$actual" = "$commit" ]
