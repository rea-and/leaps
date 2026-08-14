# Leaps

A small self-hosted tracker for Andrea's H2 2026 SuperPlan.

## Run Locally

```bash
python3 server.py
```

Open `http://127.0.0.1:8787`.

## Persistence

Progress data is stored in SQLite at:

```text
data/leaps.sqlite3
```

Set a custom location with:

```bash
LEAPS_DB=/var/lib/leaps/leaps.sqlite3 python3 server.py
```

The database also holds the WHOOP connection and refresh token. Keep it readable only by
the service account:

```bash
sudo install -d -o www-data -g www-data -m 700 /var/lib/leaps
sudo chown www-data:www-data /var/lib/leaps/leaps.sqlite3
sudo chmod 600 /var/lib/leaps/leaps.sqlite3
```

## Ubuntu Service

```ini
[Unit]
Description=Leaps SuperPlan Tracker
After=network.target

[Service]
WorkingDirectory=/opt/leaps
ExecStart=/usr/bin/python3 /opt/leaps/server.py
Environment=PORT=8787
Environment=LEAPS_DB=/var/lib/leaps/leaps.sqlite3
Environment=LEAPS_BASE_PATH=/leaps
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

## Imports

The import box accepts CSV or JSON. Use these common columns:

```csv
date,value,goal,note
2026-08-14,85.2,weight,Renpho sync
2026-08-14,6,strain,Whoop weekly target days
```

When possible, the app auto-detects goals from pasted rows for Whoop/Renpho, Medium, Goodreads, and UltraLearn. You can also force the target from the dropdown.

## WHOOP Connection

The tracker has a persistent WHOOP OAuth connection for daily strain, sleep performance,
and recovery. It uses WHOOP's official V2 API, rather than storing a WHOOP password.

1. Create an app in the [WHOOP Developer Dashboard](https://developer.whoop.com/).
2. Register `https://carlevato.net/leaps/api/whoop/callback` as its redirect URL.
3. In **Connected Data -> WHOOP integration**, enter the client ID, client secret, and the same redirect URL.
4. Select **Connect WHOOP**, approve the requested access, then select **Sync last 30 days**.

Sync is idempotent: running it again updates the same daily samples. Raw sleep, strain,
and recovery readings are retained in SQLite, while the existing sleep/recovery target uses
the average of the two percentage scores for each day.

## Hosting at carlevato.net

Run the service with `LEAPS_BASE_PATH=/leaps`. Configure the reverse proxy to pass the
`/leaps/` prefix through unchanged to the application. The relevant public URLs are:

- App: `https://carlevato.net/leaps/`
- Privacy policy: `https://carlevato.net/leaps/privacy.html`
- WHOOP callback: `https://carlevato.net/leaps/api/whoop/callback`
