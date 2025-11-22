import os, sys, httpx, json

SUPABASE_URL = os.getenv("SUPABASE_URL") or "https://gtjthmovvfpaekjtlxov.supabase.co"
ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd0anRobW92dmZwYWVranRseG92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM3NzE5NTksImV4cCI6MjA3OTEzMTk1OX0.B899huV7-OPoCugHEAGW2nk4F6PRo6ghR2J2iYA_g0k"
EMAIL = os.getenv("DIAG_EMAIL") or "test+agent@seudominio.com"
PASSWORD = os.getenv("DIAG_PASSWORD") or "TempPass123!"

if not ANON_KEY:
    print("ERRO: defina SUPABASE_ANON_KEY no ambiente antes de rodar.")
    sys.exit(1)

endpoint = SUPABASE_URL.rstrip("/") + "/auth/v1/signup"
payload = {"email": EMAIL, "password": PASSWORD}

print("Endpoint:", endpoint)
print("ANON_KEY prefix:", ANON_KEY[:10], "len=", len(ANON_KEY))
print("Email:", EMAIL)

with httpx.Client(timeout=20.0) as client:
    r = client.post(endpoint, json=payload, headers={
        "apikey": ANON_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    })
    print("Status:", r.status_code)
    print("Response headers:", {k:v for k,v in r.headers.items() if k.lower() in ["content-type","www-authenticate"]})
    try:
        body = r.json()
        print("Body JSON:")
        print(json.dumps(body, indent=2, ensure_ascii=False))
    except Exception:
        print("Body text:")
        print(r.text)