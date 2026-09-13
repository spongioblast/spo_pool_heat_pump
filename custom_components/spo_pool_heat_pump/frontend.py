"""Lovelace card static path + extra JS URL.

Needs the http and frontend integrations. The card is registered once via
add_extra_js_url. A Lovelace module resource plus extra JS loads the bundle
twice (duplicate picker rows). Matching resources are deleted. Cleanup
retries if Lovelace is not ready on the first call. The bundle defines
elements after home-assistant so the scoped-registry polyfill is in place.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant

from .const import CARD_STATIC_DIR, CARD_URL_PATH, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _lovelace_store(hass: HomeAssistant):
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA

        return hass.data.get(LOVELACE_DATA)
    except ImportError:
        return hass.data.get("lovelace")


async def async_register_card(hass: HomeAssistant) -> None:
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("card"):
        www = Path(__file__).parent / "www"
        www.mkdir(exist_ok=True)
        card = www / "spo-pool-heat-pump-card.js"
        version = "0"
        if await hass.async_add_executor_job(card.exists):
            digest = await hass.async_add_executor_job(card.read_bytes)
            version = hashlib.sha256(digest).hexdigest()[:12]
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_STATIC_DIR, str(www), False)]
            )
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Static path already registered", exc_info=True)
        add_extra_js_url(hass, f"{CARD_URL_PATH}?v={version}")
        data["card"] = True
    await _purge_card_resources(hass)
    if data.get("resources_purged") or data.get("resource_retry"):
        return
    data["resource_retry"] = True

    async def _retry(_event: Event | None = None) -> None:
        await _purge_card_resources(hass)

    if hass.is_running:
        hass.async_create_task(_retry())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _retry)


async def _purge_card_resources(hass: HomeAssistant) -> bool:
    try:
        lovelace = _lovelace_store(hass)
        resources = getattr(lovelace, "resources", None) if lovelace else None
        if resources is None:
            return False
        if not getattr(resources, "loaded", True):
            await resources.async_load()
        items = list(resources.async_items()) if hasattr(resources, "async_items") else []
        for item in items:
            if str(item.get("url", "")).split("?", 1)[0] != CARD_URL_PATH:
                continue
            item_id = item.get("id")
            if item_id and hasattr(resources, "async_delete_item"):
                await resources.async_delete_item(item_id)
        hass.data[DOMAIN]["resources_purged"] = True
        return True
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Lovelace resource cleanup skipped", exc_info=True)
        return False
