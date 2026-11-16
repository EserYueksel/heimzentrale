"""Zahlen und Zeiten fuer deutsche Texte (Handy-Meldungen, Protokoll)."""

GiB = 1024 ** 3


def de_int(n):
    return f"{int(n):,}".replace(",", ".")


def de_num(x, decimals=1):
    return f"{x:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def de_gb(b):
    return de_num(b / GiB, 1) + " GB"


def seit(sec):
    """Dauer fuer Saetze mit 'seit ...' (Dativ): 'seit 25 Minuten', 'seit 3 Tagen'."""
    m = int(max(0, sec) // 60)
    if m < 1:
        return "weniger als einer Minute"
    if m < 60:
        return "1 Minute" if m == 1 else f"{m} Minuten"
    h, mm = divmod(m, 60)
    if h < 24:
        s = "1 Stunde" if h == 1 else f"{h} Stunden"
        if mm and h < 6:
            s += f" {mm} Min."
        return s
    d = h // 24
    return "1 Tag" if d == 1 else f"{d} Tagen"
