"""Authenticated download of captured dumps."""

from __future__ import annotations

from pathlib import Path

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView, require_admin

from .dump import DUMP_DIR_NAME, DumpInvalidName, dump_path


class DumpDownloadView(HomeAssistantView):
    url = "/api/spo_pool_heat_pump/dumps/{name}"
    name = "api:spo_pool_heat_pump:dumps"
    requires_auth = True

    @require_admin
    async def get(self, request: web.Request, name: str) -> web.StreamResponse:
        hass = request.app[KEY_HASS]
        directory = Path(hass.config.path(DUMP_DIR_NAME))
        try:
            path = dump_path(directory, name)
        except DumpInvalidName:
            return self.json_message("Invalid dump name", status_code=400)
        if not path.is_file():
            return self.json_message("Not found", status_code=404)
        return web.FileResponse(
            path,
            headers={"Content-Disposition": f'attachment; filename="{path.name}"'},
        )
