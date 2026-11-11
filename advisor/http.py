"""Tiny HTTP helper: JSON GET with retries, polite backoff, and a short-lived disk cache."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".cache")
UA = {"User-Agent": "Mozilla/5.0 (fantasy-advisor)", "Accept": "application/json"}


def get_json(url, ttl=900, headers=None, retries=5):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.sha1(url.encode()).hexdigest() + ".json")
    if ttl and os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        with open(path) as f:
            return json.load(f)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode())
            with open(path, "w") as f:
                json.dump(data, f)
            return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (401, 403, 404):
                raise
            time.sleep(2 ** i)
        except Exception as e:  # network blips
            last = e
            time.sleep(2 ** i)
    raise last
