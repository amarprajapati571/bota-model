# Ubuntu Setup And Run Guide

These commands install packages, clone the project, verify it, and run the static operator dashboard.

## 1. Install System Packages

```bash
sudo apt update
sudo apt install -y git curl nginx ffmpeg python3 python3-pip python3-venv npm
```

Install Node.js 20:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Check versions:

```bash
python3 --version
node --version
npm --version
ffmpeg -version
```

## 2. Clone The Project

```bash
sudo mkdir -p /opt/bota-model
sudo chown -R $USER:$USER /opt/bota-model
cd /opt/bota-model

git clone https://github.com/amarprajapati571/bota-model.git app
cd app
```

## 3. Install Python Packages

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

For machines that will train models or run real YOLO/Torch inference:

```bash
python3 -m pip install -r requirements-ml.txt
```

## 4. Install Frontend Packages

```bash
npm install --prefix frontend
```

## 5. Verify The Project

```bash
source .venv/bin/activate
python3 -m unittest discover -s tests
npm test --prefix frontend
python3 -m src.cli.replay --input examples/sample_observations.jsonl
```

## 6. Run Frontend For Development

Start the live capture/WebSocket backend in one terminal:

```bash
source .venv/bin/activate
python3 -m src.live.app --config configs/live/md3212.yaml --host 0.0.0.0 --port 8010
```

The backend will:

- open `https://bota.dft-yui.com/` in a headless browser,
- capture live frames,
- save latest frame and ROI crops under `evidence/live/MD3212`,
- publish WebSocket events to the frontend,
- run baseline card-box detection inside Player/Banker ROIs.

The baseline detector shows card boxes/slots only. Rank, suit, totals, and winner still require trained OCR/card models.

In another terminal, start the frontend:

```bash
python3 -m http.server 4173 -d frontend
```

Open:

```text
http://localhost:4173
```

On a remote server:

```bash
sudo ufw allow 4173/tcp
```

Then open:

```text
http://SERVER_IP:4173
```

If the browser is not running on the same machine as the backend, update:

```text
frontend/config/live-session.json
```

Set:

```json
"realtime": {
  "protocol": "websocket",
  "ws_url": "ws://SERVER_IP:8010/ws/v1/tables/MD3212/live"
}
```

## 7. Production Frontend With Nginx

Create an Nginx site:

```bash
sudo nano /etc/nginx/sites-available/bota-model
```

Paste this, replacing `your-domain.com`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    root /opt/bota-model/app/frontend;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /hls/ {
        alias /var/www/bota-hls/;
        add_header Cache-Control no-cache;
        add_header Access-Control-Allow-Origin *;
    }

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/bota-model /etc/nginx/sites-enabled/bota-model
sudo nginx -t
sudo systemctl reload nginx
```

## 8. Example Live HLS Output

Use only an authorized stream URL. This is where the original/private stream URL goes:

```bash
export SOURCE_STREAM_URL="https://your-authorized-live-stream-url.m3u8"

sudo mkdir -p /var/www/bota-hls/MD3212
sudo chown -R $USER:$USER /var/www/bota-hls

ffmpeg -re -i "$SOURCE_STREAM_URL" \
  -c:v copy \
  -c:a aac \
  -f hls \
  -hls_time 2 \
  -hls_list_size 6 \
  -hls_flags delete_segments+append_list \
  /var/www/bota-hls/MD3212/index.m3u8
```

The browser playback URL becomes:

```text
http://your-domain.com/hls/MD3212/index.m3u8
```

Now put that browser playback URL in:

```text
/opt/bota-model/app/frontend/config/live-session.json
```

Example:

```json
{
  "demo_mode": false,
  "mock_events": false,
  "playback": {
    "primary_protocol": "hls",
    "hls_url": "http://your-domain.com/hls/MD3212/index.m3u8",
    "fallback_protocol": "hls"
  }
}
```

If the provider only gives a full page endpoint, use iframe mode:

```json
{
  "demo_mode": false,
  "mock_events": false,
  "playback": {
    "primary_protocol": "iframe",
    "iframe_url": "https://bota.dft-yui.com/",
    "fallback_protocol": "iframe"
  }
}
```

Important:

- `SOURCE_STREAM_URL` is private and stays on the server.
- `hls_url` is the browser-safe playback URL served by Nginx/media server.
- `hls_url` should normally be the exact `.m3u8` playlist, not a website homepage.
- Do not add the original source stream URL to frontend code.

## Important Current Limit

The repository now includes live frame capture and WebSocket event delivery. Full real ML still requires trained OCR/card models:

- clock OCR model,
- card detector,
- rank/suit classifier,
- model integration into `src/live/capture.py`.
