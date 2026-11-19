from __future__ import annotations

import re


def validate_appearance(value: object) -> dict[str, object] | None:
    """Validate the portable seed, never CSS or arbitrary style properties."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"version", "preset", "primary", "background"}:
        raise ValueError("appearance_invalid")
    if (
        type(value["version"]) is not int or value["version"] != 1
        or value["preset"] not in ("default", "custom")
        or not isinstance(value["primary"], str)
        or not re.fullmatch(r"#[0-9a-fA-F]{6}", value["primary"])
        or value["background"] not in ("neutral", "warm", "cool", "tinted")
    ):
        raise ValueError("appearance_invalid")
    if value["preset"] == "default":
        return {"version": 1, "preset": "default", "primary": "#457B66", "background": "tinted"}
    return {**value, "primary": value["primary"].upper()}
