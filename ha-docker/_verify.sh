#!/bin/bash
set -e
echo "=== index ==="
curl -sS -D /tmp/ha-index.hdr -o /tmp/ha-index.html -w "http=%{http_code} bytes=%{size_download}\n" http://127.0.0.1:18123/
echo "location: $(grep -i ^location /tmp/ha-index.hdr || true)"
echo "--- extra module ---"
grep -o 'import("[^"]*spo_pool_heat_pump[^"]*")' /tmp/ha-index.html || echo "NO extra_module import"
echo "=== card ==="
curl -sS -D /tmp/ha-card.hdr -o /tmp/ha-card.js -w "http=%{http_code} ctype=%{content_type} bytes=%{size_download}\n" http://127.0.0.1:18123/spo_pool_heat_pump/spo-pool-heat-pump-card.js
head -n 8 /tmp/ha-card.hdr
echo "--- card head ---"
head -c 80 /tmp/ha-card.js; echo
echo "=== logs spo ==="
docker compose -f /mnt/d/COSMO13/pool-heatpump/ha-docker/docker-compose.yml logs homeassistant 2>/dev/null | grep -i -E "spo_pool|2026.12|update listener" | tail -n 30 || true
