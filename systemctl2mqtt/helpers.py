"""systemctl2mqtt helpers."""

from .type_definitions import ServiceEntry


def clean_for_discovery(
    val: ServiceEntry,
) -> dict[str, str | int | float | object]:
    """Cleanup a typed dict for home assistant discovery, which is quite picky and does not like empty of None values.

    Parameters
    ----------
    val
        The TypedDict to cleanup

    Returns
    -------
    dict
        The cleaned dict

    """

    return {
        k: v
        for k, v in dict(val).items()
        if isinstance(v, str | int | float | object) and v not in (None, "")
    }


def parse_top_size(s: str) -> float:
    """Parse size string from top (like '8.5g', '512m', '1024k') into float (kilobytes)."""
    s = s.strip().lower()
    if s[-1] in "kmgt":
        num = float(s[:-1])
        unit = s[-1]
        if unit == "k":
            return num
        elif unit == "m":
            return num * 1024**1
        elif unit == "g":
            return num * 1024**2
        elif unit == "t":
            return num * 1024**3
    return float(s)  # no suffix
