"""Stage 1: Pull mental-health providers from the NPPES NPI Registry API."""
import csv
import re
import sys
import time
from collections import OrderedDict

import requests
from tqdm import tqdm

from common import (
    RotatingSession,
    load_config,
    normalize_phone,
    request_with_retries,
    title_case,
)

OUTPUT = "outputs/raw_providers.csv"

ORG_SUFFIXES = re.compile(r"\b(?:llc|pllc|pa|pc|plc|llp|inc|corporation|corp|company|co|md|phd|do)\b\.?$", re.I)
ORG_SUFFIX_ALNUM = {
    "llc", "pllc", "pa", "pc", "plc", "llp", "inc", "corporation",
    "corp", "company", "co", "md", "phd", "do", "p.a", "m.d", "p.c", "l.l.c",
}


def clean_org_name(name):
    tokens = re.split(r"[\s,]+", name.strip())
    while tokens:
        tok = tokens[-1].strip(".,")
        key = re.sub(r"[^a-z]", "", tok.lower())
        if key in {"llc", "pllc", "pa", "pc", "plc", "llp", "inc", "corporation",
                   "corp", "company", "co", "md", "phd", "do", "pa", "pc"}:
            tokens.pop()
            continue
        if any(ORG_SUFFIX_ALNUM.intersection({key, f"{key[0]}.{key[1]}.{key[2]}"} if len(key) >= 3 else {key})):
            tokens.pop()
            continue
        break
    cleaned = " ".join(tokens)
    return title_case(cleaned) if cleaned else title_case(name)


def query_npi(session, cfg, taxonomy, city, state, skip, enum_type="NPI-1"):
    params = {
        "version": "2.1",
        "limit": cfg["npi"]["limit_per_request"],
        "skip": skip,
        "taxonomy_description": taxonomy["label"],
        "city": city,
        "state": state,
        "enumeration_type": enum_type,
    }
    url = cfg["npi"]["base_url"]
    resp = request_with_retries(
        session, url, retries=cfg["npi"]["retries"], timeout=30, params=params
    )
    return resp.json()


def is_target_taxonomy(res, target_codes):
    return any(t.get("code") in target_codes for t in res.get("taxonomies", []))


def get_location(res):
    for addr in res.get("addresses", []):
        if addr.get("address_purpose") == "LOCATION":
            return addr
    return None


def extract_provider(res, city, state):
    basic = res.get("basic", {})
    is_org = bool(basic.get("organization_name"))
    if is_org:
        name = clean_org_name(basic.get("organization_name", ""))
    elif basic.get("first_name"):
        name = f"{basic.get('first_name', '')} {basic.get('last_name', '')}".strip()
    else:
        return None
    if not name:
        return None

    location = get_location(res)
    if not location:
        return None
    loc_city = (location.get("city") or "").strip().upper()
    loc_state = (location.get("state") or "").strip().upper()
    if loc_state != state.upper():
        return None

    phone = normalize_phone(location.get("telephone_number") or "")
    if len(phone) < 10:
        return None

    taxonomy = None
    for t in res.get("taxonomies", []):
        if t.get("primary"):
            taxonomy = t
            break
    if not taxonomy and res.get("taxonomies"):
        taxonomy = res["taxonomies"][0]

    street = " ".join(filter(None, [location.get("address_1"), location.get("address_2")]))
    return {
        "npi": res.get("number", ""),
        "name": title_case(name),
        "phone": phone,
        "address": street,
        "city": title_case(location.get("city", "")),
        "state": location.get("state", ""),
        "zip": location.get("postal_code", ""),
        "taxonomy": taxonomy.get("desc", "") if taxonomy else "",
        "provider_type": "Organization" if is_org else "Individual",
    }


def fetch_all(session, cfg):
    results = OrderedDict()
    target_codes = {t["code"] for t in cfg["taxonomies"]}
    enum_types = cfg["npi"].get("enumeration_types", ["NPI-1"])

    for taxonomy in cfg["taxonomies"]:
        for place in cfg["cities"]:
            city, state = place["city"], place["state"]
            for enum_type in enum_types:
                skip = 0
                max_pages = cfg["npi"]["max_pages_per_query"]
                page = 0
                while page < max_pages:
                    data = query_npi(session, cfg, taxonomy, city, state, skip, enum_type)
                    if data.get("Errors"):
                        print(f"  [!] {taxonomy['label']} {city} {state} [{enum_type}]: {data['Errors'][0]['description']}", file=sys.stderr)
                        break
                    batch = data.get("results", [])
                    if not batch:
                        break
                    for res in batch:
                        if not is_target_taxonomy(res, target_codes):
                            continue
                        row = extract_provider(res, city, state)
                        if row:
                            results[row["npi"]] = row
                    returned = len(batch)
                    skip += returned
                    page += 1
                    if returned < cfg["npi"]["limit_per_request"]:
                        break
                    time.sleep(cfg["npi"]["delay_seconds"])
    return list(results.values())


def write_csv(rows):
    fields = ["npi", "name", "phone", "address", "city", "state", "zip", "taxonomy", "provider_type"]
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved {len(rows)} unique providers -> {OUTPUT}")


def main():
    cfg = load_config()
    session = RotatingSession(cfg["user_agents"])
    rows = fetch_all(session, cfg)
    write_csv(rows)
    with_phone = sum(1 for r in rows if len(r["phone"]) >= 10)
    print(f"  {len(rows)} providers, {with_phone} with valid phone")


if __name__ == "__main__":
    main()
