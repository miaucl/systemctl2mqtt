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
