"""Lovelace card static path + extra JS URL.

Needs the http and frontend integrations. The card is registered once via
add_extra_js_url. A Lovelace module resource in HA 2026.9 can evaluate the
bundle against a non-global customElements registry, so the element never
appears for hui-card and the view shows Configuration error. Matching
resources are deleted. Cleanup retries if Lovelace is not ready on the
first call. customElements.define is still guarded in the bundle so a
leftover load is a no-op.
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
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_STATIC_DIR, str(www), True)]
        )
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
        lovelace = hass.data.get("lovelace")
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
