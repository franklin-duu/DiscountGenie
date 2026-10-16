# Small client for the public Steam Store app-details endpoint.

from typing import Any, Optional

import requests


STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"


class SteamAPIError(RuntimeError):
    # Raised when Steam cannot return valid details for an app.
    pass


def _price_in_dollars(price_overview: Optional[dict[str, Any]], key: str) -> Optional[float]:
    if not price_overview or price_overview.get(key) is None:
        return None
    return price_overview[key] / 100


def get_steam_game(
    app_id: int,
    country_code: str = "us",
    language: str = "en",
    timeout: float = 10.0,
) -> dict[str, Any]:
    # Fetch Steam data and return fields accepted by GamesDBManager.input_game.
    try:
        response = requests.get(
            STEAM_APP_DETAILS_URL,
            params={"appids": app_id, "cc": country_code, "l": language},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise SteamAPIError(f"Steam request failed for app {app_id}") from error
    except ValueError as error:
        raise SteamAPIError(f"Steam returned invalid JSON for app {app_id}") from error

    app_result = payload.get(str(app_id))
    if not app_result or not app_result.get("success"):
        raise SteamAPIError(f"Steam app {app_id} was not found")

    data = app_result.get("data") or {}
    price_overview = data.get("price_overview")
    if data.get("is_free"):
        base_price = current_price = 0.0
        discount_percent = 0.0
    else:
        base_price = _price_in_dollars(price_overview, "initial")
        current_price = _price_in_dollars(price_overview, "final")
        discount_percent = (price_overview or {}).get("discount_percent", 0.0)

    return {
        "app_id": app_id,
        "name": data.get("name") or f"Steam app {app_id}",
        "publisher": (data.get("publishers") or [None])[0],
        "developer": (data.get("developers") or [None])[0],
        "base_price": base_price,
        "current_price": current_price,
        "discount_percent": discount_percent,
    }
