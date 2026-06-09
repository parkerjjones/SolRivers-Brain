# AlsoEnergy API & Authentication Guide

## Authentication Mechanism

### cURL Session Token Method
All scripts authenticate via `alsoenergy_curl.txt` — a copy of the browser's authenticated cURL request.

**File Location**: Root directory of scripts  
**File Format**: Single cURL command with:
- Custom headers (ae_s, ae_v, user-agent)
- Authentication cookies (AspNet.Cookies, AESession)
- CloudFlare protections (.AspNet.CookiesC1, .AspNet.CookiesC2, cf_clearance)

### Token Refresh Cycle
1. **User opens browser** → AlsoEnergy login page
2. **User navigates to PowerTrack dashboard** → Browser makes authenticated requests
3. **User right-clicks on network request** → Network panel
4. **User copies cURL** → Paste into `alsoenergy_curl.txt`
5. **Scripts run** → Parse headers + cookies from cURL
6. **Token expires** (12–24 hours of inactivity) → Scripts get 401/403
7. **User must re-copy fresh cURL** → Back to step 3

### Why This Design?
- **Pro**: No API key management; reuses browser session  
- **Con**: Requires manual refresh; not production-grade; fragile to API changes

---

## API Endpoints Used

### Portfolio Live Data
```
GET /api/view/portfolio/{portfolioKey}
  Returns:
    - sites[] array with:
      - key, name
      - power (current kW output)
      - powerAvg15 (15-min rolling average)
      - powerAvg15Exp (expected power baseline)
      - lastDataUTC (timestamp of last telemetry)
```

### Site Detail  
```
GET /api/view/site/{siteKey}
  Returns:
    - name, address, latitude, longitude
    - status (0=Offline, 1=Online, 8=Partial)
    - capacityAc, capacityDc (kW)
    - dailyProductionEstimate, monthlyProductionEstimate (kWh)
    - actualCommissioningDate, validDataDate (ISO timestamps)
    - isMonitored (boolean)
    - monitoringContractStatus, cellModemContractStatus (0=Active, 1=Warning, 2=Expired, 3=Unknown)
    - monitoringContractStartDate, monitoringContractEndDate
    - monitoringContractWarnDate
    - cellModemContractEndDate
```

### Hardware Inventory
```
GET /api/scriptsite/{siteKey}?lastChanged=1900-01-01T00:00:00.000Z
  Returns:
    - site metadata (name, timezone, latitude, longitude)
    - hardware[] array with:
      - key, name, functionCode (device type)
      - hardwareStatus, sort order
      - archiveColumns[] list (telemetry field names)
```

### Alert History (Critical)
```
POST /api/view/alerthistory
  Headers:
    - Authorization: Bearer {token}
  Body:
    {
      "key": "{portfolioKey}",
      "offset": {tzOffsetMin},
      "from": "2025-01-01",
      "to": "2025-12-31"
    }
  Returns:
    - List of alert records with:
      - alertId, siteKey, hardwareKey
      - eventCode (e.g., "614 - Rule Tool Alert")
      - description, severity, impact
      - isResolved, isAcknowledged
      - alert start/end times
      - resolvedByName, acknowledgedByName
```

---

## cURL Parsing Strategy

**File**: `ae_alert_loader.py` lines 68-97

```python
def parse_curl(path):
    # 1. Read file, handle line continuations (\\\r\n or \\\n)
    raw = raw.replace("\\\r\n", " ").replace("\\\n", " ")
    
    # 2. Tokenize using shell-aware parser (shlex.split)
    tokens = shlex.split(raw)
    
    # 3. Extract headers
    while tokens:
        if token == "-H" or token == "--header":
            parse "key: value" format
            store in headers dict
        elif token == "-b" or token == "--cookie":
            parse cookie string; store
        elif token.startswith("http"):
            url = token
    
    # 4. Return (url, headers, cookie) tuple
    # 5. scripts build_session() creates requests.Session with this
```

### Session Building
```python
def build_session(headers, cookie):
    s = requests.Session()
    # Filter out "Cookie" header (redundant; jar handles it)
    clean = {k: v for k, v in headers.items() if k.lower() != "cookie"}
    s.headers.update(clean)
    # Populate cookie jar
    if cookie:
        for "name=value" in cookie.split("; "):
            s.cookies.set(name, value)
    return s
```

---

## Error Handling & Recovery

### Auth Expiration (401/403)
```python
r = session.get(url)
if r.status_code in (401, 403):
    sys.exit("Auth failed. Re-copy a fresh cURL into alsoenergy_curl.txt")
```

**User Action**: 
1. Open browser → PowerTrack dashboard
2. Right-click any request → Copy as cURL
3. Paste entire cURL into `alsoenergy_curl.txt`
4. Re-run script

### No Data (204 Response)
Incremental mode: `--since {timestamp}` returns 204 if no alerts changed since that time. Treated as success (no update needed).

### Missing Records
```python
bad = sum(1 for r in rows if not r["alert_id"])
if bad:
    print(f"[warn] {bad} records missing alertId, skipping")
rows = [r for r in rows if r["alert_id"]]
```

**Action**: Investigate response structure; may indicate API schema change.

### Rate Limiting
No explicit rate-limit headers in code. Script uses hardcoded `SLEEP = 0.4–1.5` seconds between calls.

**If 429 (Too Many Requests)**:
- Increase SLEEP variable
- Reduce batch size (WINDOW_DAYS from 31 → 7)
- Implement exponential backoff

---

## Authentication Failure Scenarios

### Scenario 1: Token Expired (Most Common)
```
GET /api/view/portfolio/C12941
HTTP 401 Unauthorized
Response: {"error": "Invalid session"}
```
**Recovery Time**: 5 minutes (user action required)

### Scenario 2: CloudFlare Block
```
Status: 403 Forbidden
Body: <HTML> You have been blocked by Cloudflare
```
**Root Cause**: 
- User IP flagged for suspicious activity
- CloudFlare WAF rule triggered by script user-agent
- cf_clearance cookie missing or stale

**Recovery**: 
- Open browser normally → CloudFlare challenge
- Copy fresh cURL (includes new cf_clearance)

### Scenario 3: AlsoEnergy Outage
```
HTTP 500 Internal Server Error
Status: Service Unavailable
```
**Recovery Time**: Wait for AlsoEnergy team (minutes to hours)

---

## Timezone Handling

### Root Issue
AlsoEnergy API stores times in **UTC**.  
Portfolio is in **US Eastern Time (UTC-5 or UTC-4 DST)**.  
Alert analysis needs to reference local time (not UTC).

### Implementation
```python
TZ_OFFSET_MIN = 360  # minutes west of UTC; 360 = 6 hours west = US Eastern
```

In alert fetch request body:
```json
{
  "key": "C12941",
  "offset": 360,  // Tells API to apply this offset
  "from": "2025-01-01",
  "to": "2025-12-31"
}
```

**Parsing**:
```python
def parse_ts(v):
    # API returns: "2025-06-08T14:30:45Z" (UTC with Z suffix)
    # Parse as UTC, then let caller adjust if needed
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")
```

**Issue**: Timestamps returned are UTC; user sees them as UTC but thinks they're Eastern.  
**Fix**: Post-process timestamps to add timezone info:
```python
dt_utc = parse_ts(...)  # datetime(2025, 6, 8, 14, 30, 45)
dt_eastern = dt_utc - timedelta(hours=5)  # Adjust for UTC-5
```

---

## Security Concerns

### 1. **DO NOT COMMIT alsoenergy_curl.txt**
Contains:
- Session token (valid for 12-24h)
- Personal browser cookies
- CloudFlare challenge tokens

**Fix**: Add to `.gitignore`:
```
alsoenergy_curl.txt
*.session
auth.json
```

### 2. **Token Reuse Risk**
cURL copied from browser is valid only from that IP/device.  
If committed to GitHub → Anyone can use it (same IP) for hours.

**Mitigation**:
- Never push to public repo
- Set token expiry in `.gitignore`
- Rotate daily (not practical; requires browser access)
- Use OAuth2 instead (AlsoEnergy must support)

### 3. **Plaintext Cookie Storage**
Database password: `host=localhost port=5432 dbname=solriver user=postgres password=postgres`

**Hardcoded in source** (line 44 of ae_alert_loader.py).

**Fix**: Use environment variables:
```python
import os
DB_DSN = os.environ.get("DB_DSN", "default...")
```

---

## Recommendations for Production

### Immediate Fixes (< 1 week)
1. **Use environment variables** for DB password
2. **Add `.gitignore`** entries for auth files
3. **Implement token refresh prompt** instead of exit
4. **Add retry logic** with exponential backoff

### Medium-term (1–4 weeks)
5. **Request AlsoEnergy OAuth2 support** (replace cURL method)
6. **Implement Postgres connection pooling** (avoid connection resets)
7. **Add monitoring for auth failures** (alert when 3+ consecutive 401s)

### Long-term (1–3 months)
8. **Switch to API key model** (if AlsoEnergy supports)
9. **Implement local token cache** with refresh-on-401
10. **Build web UI** for cURL copy/paste (avoid terminal errors)

---

## Token Lifecycle Example

```
T=0:00    User logs into AlsoEnergy → Browser gets auth token (expires 12h)
T=0:10    User opens Network tab, copies cURL → Paste into alsoenergy_curl.txt
T=0:11    python ae_alert_loader.py runs → Uses cURL session
T=6:00    Token still valid (used < 12h)
T=12:30   Token EXPIRED; user hasn't run script in 12h of inactivity
T=12:31   python ae_alert_loader.py runs again → HTTP 401
T=12:32   Script exits: "Auth failed. Re-copy a fresh cURL"
T=12:35   User opens browser, navigates to PowerTrack (triggers new auth)
T=12:36   User copies fresh cURL → Paste into file
T=12:37   python ae_alert_loader.py runs → Success with new token
```

---

## Debugging Tips

### Check Session Validity
```bash
curl -H "User-Agent: ..." \
     -H "ae_s: ..." \
     -H "ae_v: ..." \
     -b "session_cookies_here" \
     https://apps.alsoenergy.com/api/view/portfolio/C12941
```

If 200 → Session valid  
If 401 → Need fresh cURL

### Extract Session from cURL
```bash
grep -o "ae_s: [^ ]*" alsoenergy_curl.txt
grep -o "ae_v: [^ ]*" alsoenergy_curl.txt
```

### Verify Cookies Parsing
```python
from ae_alert_loader import parse_curl, build_session
url, headers, cookie = parse_curl("alsoenergy_curl.txt")
print("Headers:", headers)
print("Cookie parts:", cookie.split("; "))
```

### Test API Endpoint Directly
```python
import requests
s = build_session(headers, cookie)
r = s.get("https://apps.alsoenergy.com/api/view/portfolio/C12941")
print(r.status_code, r.json().keys())
```

---

## Contact & Support

- **AlsoEnergy Support**: support@alsoenergy.com
- **API Docs**: (None public; reverse-engineered from browser)
- **Portfolio Key**: C12941 (internal SolRiver identifier)
- **Timezone**: US/Eastern (UTC-5 standard, UTC-4 DST)
