set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:58000}"
EMAIL="${EMAIL:-smoke$(date +%s)@local.dev}"
PASSWORD="${PASSWORD:-Password123!}"
TENANT="${TENANT:-Smoke Tenant}"

TOKEN="$(curl -s -X POST "$BASE_URL/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"tenant_name\":\"$TENANT\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")"

curl -s "$BASE_URL/health" | python3 -c "import sys,json; assert json.load(sys.stdin)['status']=='ok'"
curl -s "$BASE_URL/health/db" | python3 -c "import sys,json; assert json.load(sys.stdin)['status']=='ok'"

EVID="$(curl -s -X POST "$BASE_URL/evidence" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Smoke Evidence","description":"smoke"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")"

TMP="/tmp/securitypassport_smoke.txt"
echo "smoke file" > "$TMP"

curl -s -X POST "$BASE_URL/evidence/$EVID/upload" -H "Authorization: Bearer $TOKEN" -F "file=@$TMP" >/dev/null

LIST="$(curl -s "$BASE_URL/evidence" -H "Authorization: Bearer $TOKEN")"
echo "$LIST" | python3 -c "import sys,json; j=json.load(sys.stdin); assert any(x['id']==\"$EVID\" for x in j)"

DL="$(curl -s "$BASE_URL/evidence/$EVID/download" -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; print(json.load(sys.stdin)['url'])")"
curl -s "$DL" | grep -q "smoke file"

echo "smoke ok"
