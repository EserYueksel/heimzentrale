"""Werte aus einer Meldung lesen.

Versteht zwei Formate:
  v1  heimzentrale-melder (Bash, Version 1) - nur btcnode
  v2  heimzentrale-agent (Python, ab 2.0) - alle Pis
Ergebnis ist immer dasselbe flache Woerterbuch, damit der Rest des Programms nur ein Format kennt.
"""
import re


def as_int(v):
    try:
        if v is None or isinstance(v, bool):
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def as_float(v):
    try:
        if v is None or isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def as_str(v, limit=200):
    return v[:limit] if isinstance(v, str) else None


def dig(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def pct(part, whole):
    if part is None or not whole:
        return None
    return max(0.0, min(100.0, part / whole * 100))


def _disks(p):
    """Laufwerke als Liste; das erste ist das Haupt-Laufwerk ('/')."""
    out = []
    raw = dig(p, "system", "disks")
    if isinstance(raw, list):
        for d in raw[:8]:
            if not isinstance(d, dict):
                continue
            size, used, avail = as_int(d.get("size")), as_int(d.get("used")), as_int(d.get("avail"))
            if size is None or avail is None:
                continue
            out.append({"mount": as_str(d.get("mount"), 120) or "?", "device": as_str(d.get("device"), 120),
                        "size": size, "used": used, "avail": avail, "pct": pct(used, size)})
    else:  # v1
        size, used, avail = (as_int(dig(p, "system", "disk", k)) for k in ("size", "used", "avail"))
        if size is not None and avail is not None:
            out.append({"mount": "/", "device": None, "size": size, "used": used, "avail": avail, "pct": pct(used, size)})
    out.sort(key=lambda d: d["mount"] != "/")
    return out


def _docker(p):
    d = p.get("docker")
    if not isinstance(d, dict) or not d.get("available"):
        return None
    out = []
    for c in (d.get("containers") or [])[:100]:
        if not isinstance(c, dict):
            continue
        out.append({"name": as_str(c.get("name"), 120) or "?", "image": as_str(c.get("image"), 200),
                    "state": as_str(c.get("state"), 40), "status": as_str(c.get("status"), 120),
                    "project": as_str(c.get("project"), 120)})
    return sorted(out, key=lambda c: c["name"].lower())


def _bitcoin(b):
    bc = b.get("blockchain") if isinstance(b.get("blockchain"), dict) else {}
    warnings = bc.get("warnings")
    if isinstance(warnings, list):
        warnings = "; ".join(str(w) for w in warnings if w)
    subversion = as_str(dig(b, "network", "subversion"))
    mm = re.search(r"Satoshi:(\d+\.\d+(?:\.\d+)?)", subversion or "")
    m = {
        "has_bitcoin": True,
        "service": as_str(b.get("service"), 40),
        "btc_error": as_str(b.get("error"), 400) or "",
        "chain": as_str(bc.get("chain"), 20),
        "height": as_int(bc.get("blocks")),
        "headers": as_int(bc.get("headers")),
        "block_time": as_int(bc.get("time")),
        "ibd": bc.get("initialblockdownload") if isinstance(bc.get("initialblockdownload"), bool) else None,
        "verification": as_float(bc.get("verificationprogress")),
        "size_on_disk": as_int(bc.get("size_on_disk")),
        "pruned": bc.get("pruned") if isinstance(bc.get("pruned"), bool) else None,
        "btc_warnings": warnings if isinstance(warnings, str) else "",
        "peers_in": as_int(dig(b, "network", "connections_in")),
        "peers_out": as_int(dig(b, "network", "connections_out")),
        "peers": as_int(dig(b, "network", "connections")),
        "subversion": subversion,
        "core_installed": mm.group(1) if mm else None,
        "mempool_tx": as_int(dig(b, "mempool", "size")),
        "mempool_bytes": as_int(dig(b, "mempool", "bytes")),
        "mempool_usage": as_int(dig(b, "mempool", "usage")),
        "mempool_max": as_int(dig(b, "mempool", "maxmempool")),
        "net_recv": as_int(dig(b, "nettotals", "totalbytesrecv")),
        "net_sent": as_int(dig(b, "nettotals", "totalbytessent")),
        "node_uptime_s": as_int(b.get("uptime_s")),
    }
    if m["peers"] is None and m["peers_in"] is not None and m["peers_out"] is not None:
        m["peers"] = m["peers_in"] + m["peers_out"]
    return m


def extract(p):
    s = p.get("system") if isinstance(p.get("system"), dict) else {}
    dev = p.get("device") if isinstance(p.get("device"), dict) else {}
    disks = _disks(p)
    root = disks[0] if disks else {}

    if isinstance(s.get("mem"), dict):  # v2: Bytes
        mem_total, mem_avail = as_int(dig(s, "mem", "total")), as_int(dig(s, "mem", "available"))
        swap_total, swap_used = as_int(dig(s, "mem", "swap_total")), as_int(dig(s, "mem", "swap_used"))
    else:  # v1: kB
        mt, ma = as_int(dig(s, "mem_kb", "total")), as_int(dig(s, "mem_kb", "available"))
        mem_total = mt * 1024 if mt is not None else None
        mem_avail = ma * 1024 if ma is not None else None
        swap_total = swap_used = None

    load = dig(s, "cpu", "load") if isinstance(dig(s, "cpu", "load"), list) else s.get("load")
    m = {
        "version": as_int(p.get("v")) or 1,
        "agent": as_str(p.get("agent"), 20) or (f"melder {p.get('melder')}" if p.get("melder") else None),
        "model": as_str(dev.get("model")) or as_str(p.get("model")),
        "os": as_str(dev.get("os")),
        "kernel": as_str(dev.get("kernel"), 80),
        "ip": as_str(dev.get("ip"), 60),
        "arch": as_str(dev.get("arch"), 20),
        "cpu_pct": as_float(dig(s, "cpu", "percent")),
        "cores": as_int(dig(s, "cpu", "cores")),
        "load": [as_float(x) for x in load[:3]] if isinstance(load, list) else None,
        "mem_total": mem_total,
        "mem_avail": mem_avail,
        "mem_pct": pct(mem_total - mem_avail, mem_total) if mem_total and mem_avail is not None else None,
        "swap_total": swap_total,
        "swap_used": swap_used,
        "disks": disks,
        "disk_size": root.get("size"),
        "disk_used": root.get("used"),
        "disk_avail": root.get("avail"),
        "temp": as_float(s.get("temp_c")),
        "throttled": as_str(s.get("throttled"), 20),
        "uptime_s": as_float(s.get("uptime_s")),
        "net_iface": as_str(dig(s, "net", "iface"), 30),
        "net_rx": as_int(dig(s, "net", "rx")),
        "net_tx": as_int(dig(s, "net", "tx")),
        "docker": _docker(p),
        # eigenes Melde-Skript auf dem Pi? (Version 1 gab es nur auf dem btcnode mit btcnode-ntfy)
        "own_alarms": bool(p.get("own_alarms")) if p.get("v") == 2 else True,
        "has_bitcoin": False,
    }
    if isinstance(p.get("bitcoin"), dict):
        m.update(_bitcoin(p["bitcoin"]))
    return m
