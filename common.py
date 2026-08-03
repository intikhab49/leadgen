"""Shared helpers for the leadgen pipeline."""
import json
import random
import time
import re
import requests

CONFIG_PATH = "config.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class RotatingSession(requests.Session):
    def __init__(self, user_agents):
        super().__init__()
        self._user_agents = user_agents

    def get(self, url, **kwargs):
        kwargs.setdefault("headers", {})
        kwargs["headers"].setdefault("User-Agent", random.choice(self._user_agents))
        return super().get(url, **kwargs)


def request_with_retries(session, url, retries=3, timeout=12, **kwargs):
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=timeout, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise RuntimeError(f"HTTP {resp.status_code}")
            return resp
        except (requests.RequestException, RuntimeError) as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt + random.random())

EMAIL_REGEX = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
OBFUSCATED_PATTERNS = [
    (re.compile(r"\s*\[at\]\s*", re.I), "@"),
    (re.compile(r"\s*\(at\)\s*", re.I), "@"),
    (re.compile(r"\s*\bat\b\s*", re.I), "@"),
    (re.compile(r"\s*\[dot\]\s*", re.I), "."),
    (re.compile(r"\s*\(dot\)\s*", re.I), "."),
    (re.compile(r"\s*\[@\]\s*", re.I), "@"),
    (re.compile(r"\s*\b(?:dot|point)\b\s*", re.I), "."),
]


def decode_obfuscated(text):
    text = text.replace("&#64;", "@").replace("&commat;", "@")
    text = text.replace("&#46;", ".").replace("&period;", ".")
    for pattern, replacement in OBFUSCATED_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def extract_emails(text):
    text = decode_obfuscated(text)
    emails = set(EMAIL_REGEX.findall(text))
    blacklist = {"example.com", "sentry.io", "wixpress.com", "squarespace.com", "email.com"}
    junk_domains = {"latofonts.com", "rfuenzalida.com", "impallari.com", "yourdomain.com",
                    "yoursite.com", "yourname.com", "domain.com", "webmaster.com",
                    "temp.com", "test.com", "testing.com", "localhost.com", "gethosted.com"}
    junk_local = {"user", "username", "yourname", "youremail", "test", "testing", "your", "demo", "sample", "noreply", "no-reply"}
    cleaned = set()
    for e in emails:
        e = e.lower()
        if e.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
            continue
        if any(b in e for b in blacklist):
            continue
        local, _, dom = e.partition("@")
        if dom in junk_domains or local in junk_local:
            continue
        cleaned.add(e)
    return cleaned


def normalize_phone(raw):
    if not raw:
        return ""
    digits = re.sub(r"[^0-9]", "", raw or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits


def title_case(text):
    return " ".join(w.capitalize() for w in (text or "").lower().split())
