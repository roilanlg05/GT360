#!/bin/bash
# Quick test script for earnings system endpoints

echo "🧪 Testing Earnings System Endpoints"
echo "======================================"
echo ""

# Configuration
API_URL="http://localhost:8000"
DRIVER_ID="8f83da7b-7d21-4d49-891e-1ed75d411e4d"  # Roilan Lambert

echo "📋 Prerequisites:"
echo "  - Server must be running on $API_URL"
echo "  - You need a valid auth token"
echo ""
echo "To get a token, first authenticate:"
echo "  curl -X POST $API_URL/v1/auth/sign-in \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"driver@example.com\",\"password\":\"password\"}'"
echo ""
read -p "Enter your auth token (or press Enter to skip): " TOKEN
echo ""

if [ -z "$TOKEN" ]; then
    echo "⚠️  No token provided. Tests will likely fail."
    echo ""
fi

# Test 1: Health Check
echo "1️⃣  Testing Health Endpoint..."
curl -s "$API_URL/health" | jq '.' 2>/dev/null || echo "❌ Server not responding"
echo ""

# Test 2: Start Shift
echo "2️⃣  Testing Start Shift..."
if [ -n "$TOKEN" ]; then
    curl -s -X POST "$API_URL/v1/drivers/$DRIVER_ID/shifts/start" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{}' | jq '.' 2>/dev/null || echo "❌ Failed"
else
    echo "⏭️  Skipped (no token)"
fi
echo ""

# Test 3: Get Shifts
echo "3️⃣  Testing Get Shifts..."
if [ -n "$TOKEN" ]; then
    curl -s "$API_URL/v1/drivers/$DRIVER_ID/shifts?page=1&page_size=5" \
        -H "Authorization: Bearer $TOKEN" | jq '.' 2>/dev/null || echo "❌ Failed"
else
    echo "⏭️  Skipped (no token)"
fi
echo ""

# Test 4: Get Earnings
echo "4️⃣  Testing Get Earnings..."
if [ -n "$TOKEN" ]; then
    curl -s "$API_URL/v1/drivers/$DRIVER_ID/earnings?page=1&page_size=3" \
        -H "Authorization: Bearer $TOKEN" | jq '.year_to_date' 2>/dev/null || echo "❌ Failed"
else
    echo "⏭️  Skipped (no token)"
fi
echo ""

echo "✅ Test script completed!"
echo ""
echo "📚 For full API documentation, see:"
echo "   - docs/DRIVER_EARNINGS_SYSTEM_GUIDE.md"
echo "   - EARNINGS_SYSTEM_SETUP.md"
