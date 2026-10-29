#!/usr/bin/env bash
# Explore one kit end to end: every page's screens, then pages found by URL become new roots (up to 6 rounds),
# then data variants are marked. Kit folder: kits/<kit>/states.json (page list) and, for source bundles, source/app.html.
set -u
K=kits/$1
R=$(python -c "import json;print(' '.join(s['id'] for s in json.load(open('$K/states.json')) if '__' not in s['id']))")
for round in 1 2 3 4 5 6; do
  python tools/explore_screens.py $K $R
  R=$(python tools/add_found_roots.py $K)
  [ -z "$R" ] && break
  echo "NEW ROOTS $1: $R"
done
python tools/mark_variants.py $K
echo "KIT_DONE $1"
