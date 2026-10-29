#!/usr/bin/env bash
# Explore one kit end to end: every page's screens, then pages found by URL become new roots (up to 6 rounds),
# then data variants are marked. Kit folder: kits/<kit>/states.json (page list) and, for source bundles, source/app.html.
set -u
K=kits/$1
if [ "${MODE:-explore}" = "harvest" ] || [ "${MODE:-explore}" = "remeasure" ]; then
  [ "$MODE" = "remeasure" ] && export REMEASURE=1   # components only, over the screens already recorded in screens.json
  R=$(python -c "import json;print(' '.join(json.load(open('$K/screens.json'))['roots_done']))")
  HARVEST=1 python tools/explore_screens.py $K $R
  [ -s $K/components.json ] || { echo "NO COMPONENTS for $1"; exit 1; }
  echo "KIT_DONE $1"; exit 0
fi
R=$(python -c "import json;print(' '.join(s['id'] for s in json.load(open('$K/states.json'))))")   # every listed page is a root
for round in 1 2 3 4 5 6; do
  python tools/explore_screens.py $K $R
  R=$(python tools/add_found_roots.py $K)
  [ -z "$R" ] && break
  echo "NEW ROOTS $1: $R"
done
[ -s $K/screens.json ] || { echo "NO SCREENS for $1"; exit 1; }   # a crash must fail the job, not pass it
python tools/mark_variants.py $K
echo "KIT_DONE $1"
