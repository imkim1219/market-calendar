#!/usr/bin/env python3
"""Build a single .ics feed of US earnings + macro releases.

Sources (all free):
  - Nasdaq earnings calendar API   (no key)
  - FRED releases/dates API        (free key, env FRED_API_KEY)
  - federalreserve.gov calendar    (no key, FOMC)

Run daily via launchd; the calendar app subscribes to the generated file.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "cache")
os.makedirs(CACHE, exist_ok=True)  # gitignored, so absent on a fresh checkout
ET = ZoneInfo("America/New_York")
UA = "market-calendar/1.0 (personal calendar sync)"


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def fetch(url, cache_key=None, cache_ttl=0):
    """GET a URL, optionally memoising the raw bytes on disk."""
    path = os.path.join(CACHE, cache_key) if cache_key else None
    if path and os.path.exists(path):
        age = time.time() - os.path.getmtime(path)
        if cache_ttl and age < cache_ttl:
            with open(path, "rb") as fh:
                return fh.read()
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
    if path:
        with open(path, "wb") as fh:
            fh.write(body)
    return body


# --------------------------------------------------------------------------
# events are dicts: {uid_seed, summary, description, start(datetime ET), all_day}
# --------------------------------------------------------------------------

def earnings_events(cfg, start, end):
    watch = {t.upper() for t in cfg["watchlist"]}
    events = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            url = f"https://api.nasdaq.com/api/calendar/earnings?date={day:%Y-%m-%d}"
            try:
                # past dates never change; future dates get re-checked every 6h
                ttl = 0 if day >= date.today() else 30 * 86400
                raw = fetch(url, cache_key=f"nas-{day:%Y%m%d}.json", cache_ttl=ttl or 21600)
                rows = (json.loads(raw).get("data") or {}).get("rows") or []
            except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
                log(f"  earnings {day} failed: {exc}")
                rows = []
            for row in rows:
                sym = (row.get("symbol") or "").upper()
                if sym not in watch:
                    continue
                slot = row.get("time") or ""
                if "pre-market" in slot:
                    when, tag = datetime.combine(day, datetime.min.time()).replace(hour=7, minute=0), "장전"
                elif "after-hours" in slot:
                    when, tag = datetime.combine(day, datetime.min.time()).replace(hour=16, minute=15), "장후"
                else:
                    when, tag = datetime.combine(day, datetime.min.time()).replace(hour=9, minute=0), "시간미정"
                desc = [f"{row.get('name', '')}".strip(), f"발표 시점: {tag} (ET)"]
                if row.get("epsForecast"):
                    desc.append(f"컨센서스 EPS: {row['epsForecast']}")
                if row.get("lastYearEPS"):
                    desc.append(f"전년 동기 EPS: {row['lastYearEPS']} ({row.get('lastYearRptDt', '')})")
                if row.get("fiscalQuarterEnding"):
                    desc.append(f"해당 분기: {row['fiscalQuarterEnding']}")
                desc.append("출처: Nasdaq earnings calendar")
                events.append({
                    "uid_seed": f"earn-{sym}-{day:%Y%m%d}",
                    "summary": f"실적 {sym} ({tag})",
                    "description": "\n".join(d for d in desc if d),
                    "start": when.replace(tzinfo=ET),
                    "all_day": False,
                })
            time.sleep(0.2)
        day += timedelta(days=1)
    return events


def fred_events(cfg, start, end):
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        log("  FRED_API_KEY 미설정 -> 경제지표 건너뜀")
        return []
    base = "https://api.stlouisfed.org/fred"
    raw = fetch(f"{base}/releases?api_key={key}&file_type=json&limit=1000",
                cache_key="fred-releases.json", cache_ttl=7 * 86400)
    releases = json.loads(raw).get("releases", [])

    events = []
    for spec in cfg["fred_releases"]:
        hits = [r for r in releases if spec["match"].lower() in r["name"].lower()]
        if not hits:
            log(f"  FRED release 매칭 실패: {spec['match']}")
            continue
        rel = hits[0]
        url = (f"{base}/release/dates?release_id={rel['id']}&api_key={key}&file_type=json"
               f"&realtime_start={start:%Y-%m-%d}&realtime_end={end:%Y-%m-%d}"
               f"&include_release_dates_with_no_data=true&limit=1000")
        try:
            dates = json.loads(fetch(url, cache_key=f"fred-{rel['id']}.json", cache_ttl=21600))
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            log(f"  FRED {rel['name']} failed: {exc}")
            continue
        hh, mm = (int(x) for x in spec["time"].split(":"))
        for entry in dates.get("release_dates", []):
            day = date.fromisoformat(entry["date"])
            if not (start <= day <= end):
                continue
            events.append({
                "uid_seed": f"fred-{rel['id']}-{day:%Y%m%d}",
                "summary": f"[지표] {spec['label']}",
                "description": f"{rel['name']}\n발표: {spec['time']} ET\n출처: FRED release calendar",
                "start": datetime(day.year, day.month, day.day, hh, mm, tzinfo=ET),
                "all_day": False,
            })
    return events


def fomc_events(cfg, start, end):
    if not cfg.get("include_fomc"):
        return []
    try:
        data = json.loads(fetch("https://www.federalreserve.gov/json/calendar.json",
                                cache_key="fed-calendar.json", cache_ttl=21600))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        log(f"  Fed calendar failed: {exc}")
        return []
    keys = [k.lower() for k in cfg["fomc_keywords"]]
    events = []
    for ev in data.get("events", []):
        title = ev.get("title") or ""
        if not any(k in title.lower() for k in keys):
            continue
        month = ev.get("month") or ""
        for dnum in str(ev.get("days") or "").replace("-", " ").split():
            if not dnum.strip().isdigit():
                continue
            try:
                day = date.fromisoformat(f"{month}-{int(dnum):02d}")
            except ValueError:
                continue
            if not (start <= day <= end):
                continue
            events.append({
                "uid_seed": f"fed-{day:%Y%m%d}-{title[:20]}",
                "summary": f"[Fed] {title}",
                "description": f"{ev.get('description', '')}\n{ev.get('time', '')}\n출처: federalreserve.gov",
                "start": datetime(day.year, day.month, day.day, tzinfo=ET),
                "all_day": True,
            })
    return events


# --------------------------------------------------------------------------

def esc(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def fold(line):
    """RFC 5545 requires lines <= 75 octets."""
    out, buf = [], line.encode("utf-8")
    while len(buf) > 73:
        cut = 73
        while cut > 0 and (buf[cut] & 0xC0) == 0x80:  # don't split a UTF-8 char
            cut -= 1
        out.append(buf[:cut].decode("utf-8"))
        buf = buf[cut:]
    out.append(buf.decode("utf-8"))
    return "\r\n ".join(out)


def render_ics(cfg, events):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//market-calendar//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(cfg['calendar_name'])}",
        "X-WR-TIMEZONE:America/New_York",
        "X-PUBLISHED-TTL:PT6H", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
    ]
    for ev in sorted(events, key=lambda e: e["start"]):
        uid = hashlib.sha1(ev["uid_seed"].encode()).hexdigest()[:20] + "@market-calendar"
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}")
        lines.append(f"DTSTAMP:{stamp}")
        if ev["all_day"]:
            lines.append(f"DTSTART;VALUE=DATE:{ev['start']:%Y%m%d}")
            lines.append(f"DTEND;VALUE=DATE:{ev['start'] + timedelta(days=1):%Y%m%d}")
        else:
            utc = ev["start"].astimezone(timezone.utc)
            lines.append(f"DTSTART:{utc:%Y%m%dT%H%M%SZ}")
            lines.append(f"DTEND:{utc + timedelta(minutes=30):%Y%m%dT%H%M%SZ}")
        lines.append(fold(f"SUMMARY:{esc(ev['summary'])}"))
        lines.append(fold(f"DESCRIPTION:{esc(ev['description'])}"))
        lines.append("TRANSP:TRANSPARENT")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    start = date.today()
    end = start + timedelta(days=cfg["horizon_days"])
    log(f"수집 기간 {start} ~ {end}")

    events = []
    for name, fn in (("경제지표(FRED)", fred_events), ("FOMC", fomc_events), ("실적(Nasdaq)", earnings_events)):
        got = fn(cfg, start, end)
        log(f"{name}: {len(got)}건")
        events += got

    if not events:
        log("이벤트 0건 -> 기존 파일 유지하고 종료")
        return 1

    # relative paths resolve against the script, so the repo works anywhere
    out = os.path.join(ROOT, os.path.expanduser(cfg["output_ics"]))
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(render_ics(cfg, events))
    os.replace(tmp, out)
    log(f"총 {len(events)}건 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
