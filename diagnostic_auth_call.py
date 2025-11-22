import os, sys, httpx, json

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://gtjthmovvfpaekjtlxov.supabase.co"
ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd0anRobW92dmZwYWVranRseG92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM3NzE5NTksImV4cCI6MjA3OTEzMTk1OX0.B899huV7-OPoCugHEAGW2nk4F6PRo6ghR2J2iYA_g0k"
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd0anRobW92dmZwYWVranRseG92Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2Mzc3MTk1OSwiZXhwIjoyMDc5MTMxOTU5fQ.L6H-7slonmcB3ewyyN8eFIrXOQHcK9DskXaUhrJJrzQ"
TOKEN = os.getenv("TEST_JWT_TOKEN") or ""

if not TOKEN:
    print("ERRO: defina TEST_JWT_TOKEN (o JWT do usuário) no ambiente antes de rodar.")
    sys.exit(1)

endpoint = SUPABASE_URL.rstrip("/") + "/auth/v1/user"

def mask(s):
    if not s:
        return "<empty>"
    return f"{s[:8]}... len={len(s)}"

combos = [
    ("ANON + Bearer(user JWT)", {"apikey": ANON_KEY, "Authorization": f"Bearer {TOKEN}"}),
    ("SERVICE + Bearer(user JWT)", {"apikey": SERVICE_KEY, "Authorization": f"Bearer {TOKEN}"}),
    ("NO apikey + Bearer(user JWT)", {"Authorization": f"Bearer {TOKEN}"}),
    ("ANON + No Authorization", {"apikey": ANON_KEY}),
    ("SERVICE + No Authorization", {"apikey": SERVICE_KEY}),
]

print("Endpoint:", endpoint)
print("ANON_KEY (masked):", mask(ANON_KEY))
print("SERVICE_KEY (masked):", mask(SERVICE_KEY))
print("TEST_JWT_TOKEN (first 80 chars):", TOKEN[:80], "...")
print()

with httpx.Client(timeout=15.0) as client:
    for name, headers in combos:
        displayed = {k: ("Bearer <token>" if k.lower()=="authorization" else (v[:8] + "..." if v else "<empty>")) for k,v in headers.items()}
        print("="*80)
        print("Test:", name)
        print("Outgoing headers (masked):", displayed)
        try:
            r = client.get(endpoint, headers=headers)
            print("Status:", r.status_code)
            print("Response headers (subset):", {k:r.headers.get(k) for k in ["content-type","www-authenticate"] if r.headers.get(k)})
            try:
                print("Body:", json.dumps(r.json(), indent=2, ensure_ascii=False))
            except Exception:
                print("Body (text):", r.text)
        except Exception as e:
            print("Exception:", str(e))