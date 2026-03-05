---
source: https://nicegui.io/documentation/section_configuration_deployment
fetched: 2026-03-05
library: nicegui
version: "3.8.0"
summary: Server hosting, Docker, HTTPS/SSL, reverse proxy (nginx, traefik)
---

# NiceGUI Deployment

## Server Hosting

Execute your `main.py` (containing `ui.run(...)`) on your cloud infrastructure. Options:

1. Install NiceGUI via pip, use systemd or similar to run the script
2. Use the pre-built multi-arch Docker image

Set port to 80 (HTTP) or 443 (HTTPS) for public access.

## Docker

### Single Container

```bash
docker run -it --restart always \
  -p 80:8080 \
  -e PUID=$(id -u) \
  -e PGID=$(id -g) \
  -v $(pwd)/:/app/ \
  zauberzeug/nicegui:latest
```

### Docker Compose

```yaml
services:
  app:
    image: zauberzeug/nicegui:latest
    restart: always
    ports:
      - 80:8080
    environment:
      - PUID=1000  # change to your user id
      - PGID=1000  # change to your group id
    volumes:
      - ./:/app/
```

## HTTPS / SSL

### Direct SSL (via Uvicorn)

```python
from nicegui import ui

ui.run(
    port=443,
    ssl_certfile="<path_to_certfile>",
    ssl_keyfile="<path_to_keyfile>",
)
```

The `ssl_certfile` and `ssl_keyfile` parameters are passed through to Uvicorn.

### Reverse Proxy (Recommended for Production)

In production, use a reverse proxy like **Traefik** or **NGINX** to handle SSL termination.

**NGINX example** — proxy to NiceGUI on port 8080:

```nginx
server {
    listen 443 ssl;
    server_name example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (required for NiceGUI)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

**Important:** NiceGUI uses WebSockets — your reverse proxy must support WebSocket upgrades.

See the NiceGUI repository for:
- `docker-compose.yml` example with Traefik
- `nginx.conf` example configuration

## Custom FastAPI App

For flexible deployments, use a custom FastAPI app:

```python
from fastapi import FastAPI
from nicegui import ui

app = FastAPI()

@app.get('/api/health')
def health():
    return {'status': 'ok'}

ui.run_with(app)  # instead of ui.run()
```

This allows deployments as described in the [FastAPI documentation](https://fastapi.tiangolo.com/deployment/).

**Note:** Additional steps are required to allow multiple workers with NiceGUI.

## App URLs

Access application URLs programmatically via `app.urls`:

```python
from nicegui import app

# Not available during app.on_startup
# Use page functions or app.urls.on_change instead
app.urls.on_change(lambda urls: print(f"Available at: {urls}"))
```
