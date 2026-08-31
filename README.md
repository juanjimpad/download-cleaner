# download-cleaner

Borra de qBittorrent y Transmission los torrents cuyo fichero ya no existe
en disco -- p.ej. porque se borro a mano antes de que ningun *arr*
(Sonarr/Radarr/...) pudiera hacerse cargo.

Escrito para una categoria/carpeta de descargas sin ningun *arr* detras
(trackers privados, descarga y ves directo) -- ese caso no lo cubre ninguna
herramienta del ecosistema existente:

- **Cleanuparr**: no tiene ninguna funcion para "torrent con fichero
  desaparecido".
- **Decluttarr** (`REMOVE_MISSING_FILES`): solo actua sobre la cola de un
  *arr* -- inutil si no hay ninguno.
- **qbit_manage**: tiene "orphaned files" (el caso contrario: fichero sin
  torrent) y "no hardlinks", ninguno cubre "torrent sin fichero".

## Como funciona

Bucle que cada `CHECK_INTERVAL_SECONDS` (30 min por defecto) consulta los
clientes de descarga configurados y por cada torrent comprueba si su
fichero existe en el volumen `/downloads` (montarlo **solo lectura**; el
contenedor nunca toca ficheros directamente):

- **qBittorrent**: filtra por `QBIT_CATEGORY` via API.
- **Transmission**: filtra por `downloadDir == TRANSMISSION_PRIVATE_DIR`
  via RPC -- Transmission no tiene categorias nativas.

Si falta: no borra a la primera. Lo marca "sospechoso" en `state.json`
(persistido en `/config`) y solo borra el torrent (+ cualquier resto de
fichero) si sigue faltando en la **siguiente pasada** -- protege contra un
fallo puntual de un montaje de red (NFS stale handle y similares).

## Variables de entorno

| Variable | Obligatoria | Por defecto | Uso |
|---|---|---|---|
| `QBIT_URL` | si | -- | `http://host:8080` |
| `QBIT_API_KEY` | si | -- | `Authorization: Bearer` de qBittorrent (Settings → Web UI → API Key, o el mismo que uses en Sonarr/Radarr) |
| `QBIT_CATEGORY` | no | `private` | categoria a vigilar |
| `TRANSMISSION_URL` | no | (desactivado si vacio) | `http://host:9091` |
| `TRANSMISSION_RPC_PATH` | no | `/transmission/rpc` | |
| `TRANSMISSION_PRIVATE_DIR` | no | `/downloads/complete/private` | carpeta a vigilar |
| `CHECK_INTERVAL_SECONDS` | no | `1800` | |
| `STATE_FILE` | no | `/config/state.json` | |

## Despliegue

Imagen publicada por GitHub Actions en cada push a `main`:
`ghcr.io/juanjimpad/download-cleaner:latest`.

```yaml
services:
  download-cleaner:
    image: ghcr.io/juanjimpad/download-cleaner:latest
    restart: unless-stopped
    environment:
      QBIT_URL: http://192.168.1.7:8080
      QBIT_API_KEY: ${QBIT_API_KEY}
      QBIT_CATEGORY: private
      TRANSMISSION_URL: http://192.168.1.7:9091
      TRANSMISSION_PRIVATE_DIR: /downloads/complete/private
    volumes:
      - ./config:/config
      - /path/a/downloads:/downloads:ro
```
