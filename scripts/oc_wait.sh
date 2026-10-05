#!/usr/bin/env bash
# Wait for an orphaned OpenCode worker (by PID) to exit, then print its tag (background-task notification = worker done).
pid=$1; tag=$2
while tasklist //FI "PID eq $pid" 2>/dev/null | grep -q "$pid"; do sleep 60; done
echo "worker $tag (pid $pid) exited"
