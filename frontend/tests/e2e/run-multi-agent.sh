#!/bin/bash
set -e

E2E_DIR="/Users/jung/pro/quant-agent/frontend"
REPORT_DIR="$E2E_DIR/test-results"
BUG_REPORT="$E2E_DIR/bug-reports.md"

mkdir -p "$REPORT_DIR"

echo "🚀 Starting Multi-Agent E2E Testing..."
echo "========================================"
echo "Time: $(date)"
echo ""

# 记录开始时间
START_TIME=$(date +%s)

# 并行运行 3 个测试 agent
echo "📦 Starting Auth E2E tests..."
pnpm playwright test tests/e2e/auth.spec.ts --reporter=list --output="$REPORT_DIR/auth" 2>&1 | tee "$REPORT_DIR/auth-output.txt" &
PID_AUTH=$!

echo "📦 Starting Chat E2E tests..."
pnpm playwright test tests/e2e/chat.spec.ts --reporter=list --output="$REPORT_DIR/chat" 2>&1 | tee "$REPORT_DIR/chat-output.txt" &
PID_CHAT=$!

echo "📦 Starting Workspace E2E tests..."
pnpm playwright test tests/e2e/threads.spec.ts tests/e2e/reconnect.spec.ts --reporter=list --output="$REPORT_DIR/workspace" 2>&1 | tee "$REPORT_DIR/workspace-output.txt" &
PID_WORKSPACE=$!

# 等待所有测试完成并收集结果
echo ""
echo "⏳ Waiting for tests to complete..."
echo ""

wait $PID_AUTH
AUTH_RESULT=$?

wait $PID_CHAT
CHAT_RESULT=$?

wait $WORKSPACE_RESULT=$?

wait $PID_WORKSPACE
WORKSPACE_RESULT=$?

# 计算总时间
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# 解析测试结果
parse_results() {
    local dir=$1
    local passed=0
    local failed=0

    if [ -f "$dir/-results.json" ]; then
        passed=$(grep -o '"passed":[[:space:]]*[0-9]*' "$dir/results.json" | grep -o '[0-9]*$' | head -1 || echo 0)
        failed=$(grep -o '"failed":[[:space:]]*[0-9]*' "$dir/results.json" | grep -o '[0-9]*$' | head -1 || echo 0)
    fi

    echo "$passed:$failed"
}

AUTH_RESULTS=$(parse_results "$REPORT_DIR/auth")
CHAT_RESULTS=$(parse_results "$REPORT_DIR/chat")
WORKSPACE_RESULTS=$(parse_results "$REPORT_DIR/workspace")

# 生成汇总报告
SUMMARY_FILE="$REPORT_DIR/summary.md"

cat > "$SUMMARY_FILE" << EOF
# E2E Test Summary

**Run Date:** $(date)
**Duration:** ${DURATION}s

## Results by Suite

### Auth E2E
- **Status:** $([ $AUTH_RESULT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL")
- **Exit Code:** $AUTH_RESULT
- **Output:** $([ -f "$REPORT_DIR/auth-output.txt" ] && echo "saved" || echo "N/A")

### Chat E2E
- **Status:** $([ $CHAT_RESULT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL")
- **Exit Code:** $CHAT_RESULT
- **Output:** $([ -f "$REPORT_DIR/chat-output.txt" ] && echo "saved" || echo "N/A")

### Workspace E2E
- **Status:** $([ $WORKSPACE_RESULT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL")
- **Exit Code:** $WORKSPACE_RESULT
- **Output:** $([ -f "$REPORT_DIR/workspace-output.txt" ] && echo "saved" || echo "N/A")

## Overall
- **All Passed:** $([ $AUTH_RESULT -eq 0 ] && [ $CHAT_RESULT -eq 0 ] && [ $WORKSPACE_RESULT -eq 0 ] && echo "✅ Yes" || echo "❌ No")

## Detailed Logs
- Auth: $REPORT_DIR/auth-output.txt
- Chat: $REPORT_DIR/chat-output.txt
- Workspace: $REPORT_DIR/workspace-output.txt
EOF

# 更新 bug-reports.md
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
cat >> "$BUG_REPORT" << EOF

---

## Test Run: $TIMESTAMP

| Suite | Result | Duration |
|-------|--------|----------|
| Auth | $([ $AUTH_RESULT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL") | - |
| Chat | $([ $CHAT_RESULT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL") | - |
| Workspace | $([ $WORKSPACE_RESULT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL") | - |
EOF

echo ""
echo "========================================"
echo "✅ Multi-Agent E2E Testing Complete!"
echo ""
echo "Duration: ${DURATION}s"
echo ""
echo "Results:"
echo "  Auth:      $([ $AUTH_RESULT -eq 0 ] && echo '✅ PASS' || echo '❌ FAIL')"
echo "  Chat:      $([ $CHAT_RESULT -eq 0 ] && echo '✅ PASS' || echo '❌ FAIL')"
echo "  Workspace: $([ $WORKSPACE_RESULT -eq 0 ] && echo '✅ PASS' || echo '❌ FAIL')"
echo ""
echo "Reports:"
echo "  Summary:   $SUMMARY_FILE"
echo "  Bug Reports: $BUG_REPORT"
