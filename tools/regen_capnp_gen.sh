#!/usr/bin/env bash
# M-17: regenerate Cap'n Proto C++ bindings for cereal/custom.capnp on C3 / AGNOS.
#
# Usage:
#   bash tools/regen_capnp_gen.sh             # regenerate + verify only (default)
#   bash tools/regen_capnp_gen.sh --commit    # also git add + commit (never pushes)
#
# Background: cereal/gen/cpp/custom.capnp.* were generated when AmapNavi had 15
# fields. custom.capnp now has 17 (@0..@16). scons keys the generated targets off
# schema_files, so a rebuild is triggered automatically; touching the schema makes
# it deterministic even after a checkout/scp flattens timestamps.
# See 34_M17_CapnProto生成物修复说明与设备重生成指引.md
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$BASH_SOURCE")/.." && pwd)"
cd "$REPO_ROOT"

SCHEMA="cereal/custom.capnp"
HDR="cereal/gen/cpp/custom.capnp.h"
SRC="cereal/gen/cpp/custom.capnp.c++"
SCHEMA_ID="aedffd8f31e7b55d"

ARG=""
if [[ $# -gt 0 ]]; then ARG="$1"; fi

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$SCHEMA" ]] || die "schema not found: $SCHEMA (run inside the openpilot checkout)"
[[ -f "$HDR" ]] || die "generated header not found: $HDR"
[[ -f "$SRC" ]] || die "generated source not found: $SRC"
command -v scons >/dev/null 2>&1 || die "scons not found in PATH; run this on the C3 / AGNOS device"
command -v python3 >/dev/null 2>&1 || die "python3 not found"

# Expected field count derived from the schema itself, not hardcoded.
EXPECTED_FIELDS="$(sed -n '/^struct AmapNavi/,/^}/p' "$SCHEMA" | grep -cE '@[0-9]+[[:space:]]*:')"
[[ "$EXPECTED_FIELDS" -gt 0 ]] || die "could not count AmapNavi fields in $SCHEMA; check schema syntax"
echo "schema AmapNavi fields: $EXPECTED_FIELDS"

echo "--- BEFORE ---"
grep -n "CAPNP_DECLARE_STRUCT_HEADER($SCHEMA_ID" "$HDR" || true
grep -n "i_$SCHEMA_ID\[\]" "$SRC" || true

touch "$SCHEMA"
echo "--- running scons ---"
scons -j"$(nproc)" cereal/

echo "--- AFTER ---"
grep -n "CAPNP_DECLARE_STRUCT_HEADER($SCHEMA_ID" "$HDR" || true
grep -n "i_$SCHEMA_ID\[\]" "$SRC" || true

echo "--- verifying ---"
python3 - "$HDR" "$SRC" "$SCHEMA_ID" "$EXPECTED_FIELDS" <<'PY'
import re, sys
hdr_path, src_path, sid, expected = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
hdr = open(hdr_path, encoding='utf-8', errors='replace').read()
src = open(src_path, encoding='utf-8', errors='replace').read()
errors = []

m = re.search(r'CAPNP_DECLARE_STRUCT_HEADER\(' + re.escape(sid) + r',\s*(\d+),\s*(\d+)\)', hdr)
if not m:
    errors.append('struct header not found in generated .h')
else:
    data_words = int(m.group(1))
    print('dataWordCount:', data_words, '(old build was 8)')
    if data_words == 8:
        errors.append('dataWordCount is still 8 - capnpc did not regenerate')

i = re.search(r'i_' + re.escape(sid) + r'\[\]\s*=\s*\{([^}]*)\}', src, re.S)
if not i:
    errors.append('field index array not found in generated .c++')
else:
    n = len([x for x in i.group(1).replace('\n', ' ').split(',') if x.strip().isdigit()])
    print('field index entries:', n, '(expected', expected, ')')
    if n != expected:
        errors.append('field index array has %s entries, expected %s' % (n, expected))

for g in ('getOvertakeMode', 'getLidarBehindVdistTime'):
    ok = g in hdr
    print('getter', g + ':', 'present' if ok else 'MISSING')
    if not ok:
        errors.append('missing accessor ' + g)

if errors:
    print('VERIFY FAILED:')
    for e in errors:
        print('  -', e)
    print('Common causes: capnpc missing, schema syntax error, scons did not rebuild.')
    print('Try a full build: scons -j$(nproc)')
    sys.exit(1)
print('VERIFY OK: generated bindings match the 17-field AmapNavi schema')
PY

echo "--- done (verification passed) ---"

if [[ "$ARG" == "--commit" ]]; then
  git add "$HDR" "$SRC"
  if git diff --cached --quiet -- "$HDR" "$SRC"; then
    die "nothing staged; generation produced no diff"
  fi
  git commit -m "chore(cereal): regenerate C++ schema bindings for AmapNavi 17 fields"
  echo "committed locally. Push manually when ready (this script never pushes)."
else
  echo "Generated files updated but NOT committed."
  echo "Inspect with: git diff -- $HDR $SRC"
  echo "To commit:    bash tools/regen_capnp_gen.sh --commit"
fi
