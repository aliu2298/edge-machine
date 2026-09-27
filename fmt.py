"""Presentation formatting for the public pages.

Money, percents, prices, and clock times. Nothing here settles, grades, or
changes a stored number. Callers keep the same values they already computed.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MINUS = "\u2212"  # U+2212, not a hyphen
CHICAGO = ZoneInfo("America/Chicago")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _as_utc(value):
    """A datetime or ISO instant, as UTC. A naive datetime is UTC."""
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _magnitude(value, spec):
    """`value` rounded the way `format` prints it, without a sign."""
    return format(abs(value), spec)


def _is_displayed_zero(magnitude):
    return float(magnitude.replace(",", "")) == 0.0


def _sign(value, magnitude, plus):
    """'' when the rounded magnitude is zero, else U+2212 or an optional plus."""
    if _is_displayed_zero(magnitude):
        return ""
    if value < 0:
        return MINUS
    return "+" if plus else ""


def money(x):
    """Whole dollars, signed. −$100 uses U+2212. None is an em dash.

    A value that rounds to $0 prints with no sign.
    """
    if x is None:
        return "—"
    body = _magnitude(x, ",.0f")
    return f"{_sign(x, body, plus=True)}${body}"


def pct(x, digits=1, sign=False):
    """x is a ratio (0.01 == 1%). A negative uses U+2212.

    A value that rounds to zero at `digits` prints with no sign.
    """
    if x is None:
        return "—"
    scaled = x * 100
    body = _magnitude(scaled, f".{digits}f")
    return f"{_sign(scaled, body, plus=sign)}{body}%"


def cents(x):
    """An exchange price as whole cents. 0.77 -> 77¢.

    Rounded with the same two-decimal step the pages used to print, so 0.333
    is 33¢ just as it used to print 0.33. None is an em dash. A price that
    rounds to 0¢ has no minus sign.
    """
    if x is None:
        return "—"
    shown = f"{float(x):.2f}"
    n = int(round(abs(float(shown)) * 100))
    if n == 0:
        return "0¢"
    sign = MINUS if shown.startswith("-") else ""
    return f"{sign}{n}¢"


def signed_cents(x, digits=1):
    """A price difference stored as a fraction, shown in signed cents.

    0.07 -> +7.0¢ and -0.08 -> −8.0¢. This is the CLV display. None is an em dash.
    A difference that rounds to 0.0¢ has no sign.
    """
    if x is None:
        return "—"
    scaled = x * 100
    body = _magnitude(scaled, f".{digits}f")
    return f"{_sign(scaled, body, plus=True)}{body}¢"


def chicago(value):
    """The instant in America/Chicago, so CDT and CST both come out right."""
    return _as_utc(value).astimezone(CHICAGO)


def zone_abbr(value):
    """CDT in summer, CST after the fall-back. Empty if the zone has no name."""
    return chicago(value).tzname() or ""


def clock(value):
    """12-hour clock labelled CT. 2026-09-27T05:12:00Z -> 12:12 AM CT."""
    local = chicago(value)
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{hour}:{local.minute:02d} {ampm} CT"


def when(value):
    """Sep 27, 12:12 AM CT. The date is the Chicago calendar day."""
    local = chicago(value)
    month = _MONTHS[local.month - 1]
    return f"{month} {local.day}, {clock(value)}"


def display_updated(value):
    """Updated Sep 27, 12:12 AM CT."""
    return "Updated " + when(value)


def machine_stamp(value):
    """The tracker freshness form. Sandbox and Production carry this; the root must not."""
    return _as_utc(value).strftime("updated %Y-%m-%d %H:%M UTC")


def iso_z(value):
    """UTC instant for a <time datetime> attribute."""
    return _as_utc(value).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def tone(value, spec=".1f", scale=100):
    """'pos', 'neg', or 'mut' from the value as it would be displayed.

    `spec` formats the scaled absolute value, the same way money and pct round.
    A value that rounds to zero at that precision is 'mut', even when the raw
    value is negative. -0.0004 shown as 0.0% (digits 1) is neutral.
    """
    if value is None:
        return "mut"
    scaled = value * scale
    body = _magnitude(scaled, spec)
    sign = _sign(scaled, body, plus=True)
    if sign == MINUS:
        return "neg"
    if sign == "+":
        return "pos"
    return "mut"


def shown_digits(value, spec=",.0f", scale=1):
    """The number as displayed, ASCII-signed, with no unit and no thousands comma.

    None stays None. A value that rounds to zero is '0', with no minus. Negatives
    use ASCII '-' so a data-v attribute stays a number. The displayed text still
    uses U+2212 via money() and pct().
    """
    if value is None:
        return None
    scaled = value * scale
    body = _magnitude(scaled, spec).replace(",", "")
    if _is_displayed_zero(body):
        return "0"
    if scaled < 0:
        return "-" + body
    return body


def shown_cents_digits(x):
    """The cent figure cents() prints, ASCII-signed. 0.77 -> '77'. None stays None."""
    if x is None:
        return None
    shown = f"{float(x):.2f}"
    n = int(round(abs(float(shown)) * 100))
    if n == 0:
        return "0"
    return f"-{n}" if shown.startswith("-") else str(n)


def tstat(value):
    """A t statistic the way the pages print it.

    A value that rounds to 0.00 is 't 0.00', with no plus. A negative uses
    U+2212. A positive keeps the plus: 't +1.23'. None is an em dash.
    """
    if value is None:
        return "—"
    body = _magnitude(value, ".2f")
    return f"t {_sign(value, body, plus=True)}{body}"
