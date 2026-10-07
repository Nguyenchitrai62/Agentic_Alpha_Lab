#!/bin/bash
# emit one line when any OpenCode worker finishes (tag + exit); runs until killed
cd /c/TRAI_NC/Source_code/Agentic_Alpha_Lab/artifacts/research/opencode_background
declare -A seen
for f in *.current; do r=$(cat $f); grep -q "exit=" $r.stderr.log 2>/dev/null && seen[$f]=1; done
while true; do
  for f in *.current; do
    [ -n "${seen[$f]}" ] && continue
    r=$(cat $f); if grep -q "exit=" $r.stderr.log 2>/dev/null; then echo "DONE ${f%.current} $(grep exit= $r.stderr.log | tail -1)"; seen[$f]=1; fi
  done
  sleep 30
done
