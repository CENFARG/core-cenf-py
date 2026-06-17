#!/bin/bash
# CENF Rule: block files over 250 lines
find src/core_infrastructure -name '*.py' | while read f; do
  lines=$(wc -l < "$f")
  if [ "$lines" -gt 250 ]; then
    echo "$f: $lines lines (max 250)" >&2
    exit 1
  fi
done
