#!/usr/bin/env bash
# Build dump_ref.cpp against the unmodified KinectArmSimulator arm.cpp + GLM and
# emit the reference truth file ref_cases.json (committed, so the numpy tests run
# without a C++ toolchain). Re-run this only when arm.cpp changes.
#
# The KinectArmSimulator source tree is left untouched: arm.h/arm.cpp are copied
# into build/ and a single g++-compat patch is applied there (see below).
#
# Usage: ./build_and_dump.sh [path-to-KinectArmSimulator/KinectArmSimulator]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KAS="${1:-${KAS_DIR:-/d/github/KinectArmSimulator/KinectArmSimulator}}"

ARM_DIR="$KAS/src/window3"
GLM_DIR="$KAS/third_party/glm"
BUILD="$HERE/build"

[ -f "$ARM_DIR/arm.cpp" ] || { echo "arm.cpp not found under $ARM_DIR" >&2; exit 1; }
[ -f "$GLM_DIR/glm/glm.hpp" ] || { echo "glm not found under $GLM_DIR" >&2; exit 1; }

echo "KAS repo : $KAS"
rm -rf "$BUILD"; mkdir -p "$BUILD"
cp "$ARM_DIR/arm.h" "$ARM_DIR/arm.cpp" "$BUILD/"

# g++-compat patch (KAS tree untouched; applied to the build copy only):
# arm.h declares  solveIK(..., const IKOptions& opts = {})  where IKOptions is
# nested in Manipulator. GCC rejects value-initializing a nested aggregate via
# its default member initializers inside the still-incomplete enclosing class
# ("default member initializer required before the end of its enclosing class").
# MSVC/Clang accept it. The default argument is never used (arm.cpp and the
# dumper always pass opts explicitly), so we simply drop it — behaviour-identical.
sed -i 's/const IKOptions& opts = {}/const IKOptions\& opts/' "$BUILD/arm.h"

echo "compiling dump_ref ..."
g++ -std=c++17 -O2 \
    -I "$BUILD" \
    -I "$GLM_DIR" \
    "$HERE/dump_ref.cpp" "$BUILD/arm.cpp" \
    -o "$BUILD/dump_ref.exe"

echo "running dump_ref -> ref_cases.json ..."
"$BUILD/dump_ref.exe" > "$HERE/ref_cases.json"

echo "wrote $HERE/ref_cases.json ($(wc -c < "$HERE/ref_cases.json") bytes)"
