# StrategyOne: Multi-Agent Platform Hosting & Deployment Guide

This guide provides step-by-step instructions to host and deploy the **StrategyOne Autonomous Multi-Agent Trading System and Modern Web Cockpit**.

---

## 1. Unified Architecture Overview

The StrategyOne platform is engineered as a unified, high-performance web platform combining:
- **FastAPI Core Backend (`api/server.py`)**: Asynchronous REST endpoints, WebSocket streaming telemetry, risk monitoring, and trade execution order management.
- **Modern Vite React Web Cockpit (`frontend/`)**: Glassmorphic, dark-mode real-time UI featuring:
  - **Agent Consensus Network**: 9-agent deliberation graph and confidence voting.
  - **Live Execution & Ladder**: Dynamic R-multiple visualizer and OCO bracket tracking.
  - **2-Year Walk-Forward Backtest**: Full 25-month performance matrix and trade history.
  - **Institutional & Due Diligence Suite**: Executive comparison tear sheet, species benchmarking, and 1-click audit-pack downloads (`.xlsx`, `.csv`, `.html`).
- **Static SPA Mounting**: When built, the FastAPI backend automatically serves the React UI directly from `/`, eliminating the need for a separate web server in production.

---

## 2. Multi-Agent Taxonomy & Perspective Matrix

### A. Technical & Alpha Engine
| Agent | Layer | Key Metric / Role | Governance Rule |
| :--- | :---: | :--- | :--- |
| **Data Quality Agent** | Gateway | Tick freshness, null checks, gap interpolation | Unconditional veto on data anomalies |
| **Technical Analysis Agent** | Context | EMA 9/21/50, RSI 14, ATR 14, **Macro 200 SMA Gate** | **Longs: Price $\ge$ 200 SMA; Shorts: Price < 200 SMA** |
| **Volatility & Regime Agent** | Context | GARCH vol, ADX strength, market classification | Bull (24.7%), Bear (21.6%), Chop (41.2%), Chaos (12.4%) |
| **Market Microstructure Agent**| Context | Funding rates, open interest shifts, liquidation deltas | Filters out crowded trades |
| **Strategy Evolution Agent** | Alpha | Dynamic genetic weighting of 4 trading species | Re-weights genomes based on walk-forward fitness |
| **Decider Agent** | Strategy | Consensus voting ($\ge 60\%$ confidence required) | Enforces Macro 200 SMA veto power |

### B. Risk & Governance Shield
| Agent | Layer | Key Metric / Role | Governance Rule |
| :--- | :---: | :--- | :--- |
| **Risk Agent** | Governance | Cornish-Fisher VaR (95%), CVaR expected shortfall | Hard 1.0% risk cap per trade; **2.0% daily DD circuit breaker** |
| **Portfolio Agent** | Governance | Margin utilization buffer, cash management | Maintains **71.6% cash in USDT** for tail insulation |
| **Execution Agent** | Execution | OCO bracket placement, slippage guards | TP1 (50% size at $2.0 \times \text{SL}$), TP2 runner at $3.5 \times \text{SL}$ |

### C. User-Oriented Perspective (The Operator)
- **Real-Time Telemetry HUD**: Live BTC/USDT price, daemon state, committee signal, and market regime.
- **Interactive Position Ladder**: Visual track of entry fill, mark price, stop loss, trailing stop, TP1, and TP2.
- **Operator Controls**: 1-click Emergency Flatten to 100% USDT, Pause/Resume autonomous trading, and risk adjustment.

### D. Business & Institutional Perspective (The Trading Desk)
- **Audited Deliverables**: Instant downloads of `StrategyOne_2Y_Institutional_Backtest_Report.xlsx` (8 tabs) and daily ledger CSV.
- **Benchmark Evidence**: Side-by-side comparison proving how the committee delivered +13.19% net return and 1.45% max DD while naive standalone models lost -47% to -84%.
- **Tail-Risk Containment**: Empirical Cornish-Fisher VaR ($20.50) and CVaR ($42.80) metrics.

---

## 3. Hosting & Deployment Methods

### Method 1: Local / VPS Native Launch (Fastest)

Run the platform directly with Python and Node.js:

```bash
# 1. Build the production frontend bundle
cd frontend
npm install
npm run build
cd ..

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Launch the unified platform on port 8000
python -m uvicorn api.server:app --host 0.0.0.0 --port 8000
```
Open **`http://localhost:8000`** in your browser. Both the API and the React web app run seamlessly on a single port!

---

### Method 2: Docker & Docker Compose (Recommended for Production)

StrategyOne includes a production multi-stage `Dockerfile` and `docker-compose.yml`:

```bash
# 1. Configure your environment variables
cp .env.example .env
# Edit .env with your Binance API keys (if live/testnet trading)

# 2. Build and run containerized platform in background
docker compose up -d --build

# 3. Check container logs
docker compose logs -f
```

The container automatically:
- Builds the Vite React frontend.
- Prepares the Python 3.11 environment.
- Configures healthchecks against `http://localhost:8000/api/health`.
- Mounts `./data` and `./logs` for state persistence across restarts.

---

### Method 3: Cloud VPS Deployment (Ubuntu / Debian on AWS, DigitalOcean, Hetzner)

#### 1. Setup Server & Firewall
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git nginx certbot python3-certbot-nginx
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
```

#### 2. Clone and Setup Environment
```bash
git clone <your-repository-url> /opt/strategyone
cd /opt/strategyone

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Build frontend
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
cd frontend && npm install && npm run build && cd ..
```

#### 3. Setup Systemd Service (`/etc/systemd/system/strategyone.service`)
```ini
[Unit]
Description=StrategyOne Autonomous Quantitative Trading Platform
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/strategyone
ExecStart=/opt/strategyone/venv/bin/uvicorn api.server:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
EnvironmentFile=/opt/strategyone/.env

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable strategyone
sudo systemctl start strategyone
sudo systemctl status strategyone
```

#### 4. Configure Nginx Reverse Proxy with Free SSL
Create `/etc/nginx/sites-available/strategyone`:
```nginx
server {
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Enable the site and obtain SSL:
```bash
sudo ln -s /etc/nginx/sites-available/strategyone /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo certbot --nginx -d yourdomain.com
```

---

### Method 4: Cloud Platform as a Service (Railway, Render, Fly.io)

For cloud platforms supporting Docker:
1. Connect your GitHub repository to **Railway** or **Render**.
2. Select **Dockerfile** deployment.
3. Configure the environment variables:
   - `PORT`: `8000`
   - `TRADING_MODE`: `PAPER` (or `TESTNET`)
   - `BINANCE_API_KEY`: `your_key`
   - `BINANCE_API_SECRET`: `your_secret`
4. Deploy! The platform will automatically build the frontend, launch the FastAPI server, and expose a secure HTTPS public URL.

---

## 4. Key Endpoints Reference

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/` | `GET` | Serves the full interactive Vite React Web Cockpit |
| `/api/health` | `GET` | Healthcheck endpoint (`{"status": "healthy"}`) |
| `/api/system/status` | `GET` | Real-time system state, active regime, and portfolio equity |
| `/api/agents` | `GET` | Status, confidence, weights, and metrics for all 9 agents |
| `/api/positions` | `GET` | Active positions, OCO bracket orders, and R-multiple status |
| `/api/backtest/2y` | `GET` | 2-Year Walk-Forward backtest results & sampled equity curve |
| `/api/download/excel` | `GET` | Streams `StrategyOne_2Y_Institutional_Backtest_Report.xlsx` |
| `/api/download/ledger` | `GET` | Streams `StrategyOne_2Y_Daily_Ledger.csv` |
| `/api/download/report` | `GET` | Streams `StrategyOne_2Y_Quantitative_Strategy_Report.html` |
| `/api/operator/emergency-flatten` | `POST` | Immediately cancels orders and flattens to 100% cash |
| `/api/operator/toggle-pause` | `POST` | Freezes or unfreezes autonomous trading committee |
| `/ws/live` | `WebSocket` | Real-time price ticks, consensus pulses, and trade events |
