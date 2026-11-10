# plot-runner-agent

Flask API server for controlling a NextDraw plotter from a Raspberry Pi. Accepts SVG uploads and executes plots by layer, with pause/resume support and a serial display integration.

## Architecture

- **`app.py`** — Flask server, route definitions, background status sync thread
- **`plotter_controller.py`** — Wraps the NextDraw API; handles job execution, pause/resume, and utility commands
- **`svg_manager.py`** — Stores the active SVG, extracts layer info, handles chunked uploads
- **`serial_communication.py`** — Serial link to the Plot Runner panel (LilyGo T-Display S3 AMOLED): reconnects, sends `AT`/`ARMED`/`IDLE`/`STATUS`, and dispatches the panel's events
- **`display_jobs.py`** — Armed-job state: checks an arm request against the loaded SVG, starts the plot when Start is pressed on the panel, keeps the panel in step. The panel is optional; plotting works without it
- **`wifi/`** — WiFi fallback hotspot watchdog and its page (separate root service, see below)
- **`config.json`** — Plotter and API settings

## Deploy

### Fresh install (Raspberry Pi)

```bash
git clone <repo> /home/james/plot-runner-agent
cd /home/james/plot-runner-agent
bash deploy/install.sh
```

The script:
- Installs system dependencies (`python3-venv`, `libusb`, `nginx`, etc.)
- Creates a Python virtualenv at `venv/`
- Installs Python deps from `requirements.txt` (includes NextDraw API 1.7.3)
- Configures udev rules for USB plotter access
- Installs and enables the `nextdraw-api` systemd service
- Configures nginx as a reverse proxy on port 80

### Ansible deploy

The inventory lives at `ansible/inventory.ini`. Deploy to all configured Raspberry Pis:

```bash
cd ansible
ansible-playbook -i inventory.ini deploy_app.yml
```

This syncs the repo, reinstalls deps, and restarts the service. The playbook targets the `raspberry_pis` host group.

### Update in place

On the Pi:

```bash
cd /home/james/plot-runner-agent
./update.sh
```

This pulls from `main`, reinstalls requirements (including NextDraw), and restarts the service.

### Service management

```bash
sudo systemctl start nextdraw-api
sudo systemctl stop nextdraw-api
sudo systemctl restart nextdraw-api
sudo journalctl -u nextdraw-api -f
```

## WiFi fallback hotspot

If a Pi can't join any saved WiFi network for 90 seconds (and has no wired link), it starts its own WPA2 hotspot named after its hostname, e.g. `nd-radius-direct`. Join it, then open **http://10.42.0.1/network/** (or `http://10.42.0.1:8080/`). While the hotspot is up, the Pi tries its saved networks every 5 minutes, but only when no device is connected to the hotspot.

The page shows the current state and lets you join a network, forget saved networks, start the hotspot now, try WiFi now, and change the timings. On WiFi it's at `http://<host>.local/network/`.

**Password.** Set it in `.env` at the repo root on the computer you deploy from (gitignored, and never copied to the Pi):

```bash
PLOT_RUNNER_HOTSPOT_PASSWORD=at-least-8-chars
```

An exported `PLOT_RUNNER_HOTSPOT_PASSWORD` takes precedence over `.env`. The deploy writes the password into NetworkManager's root-only hotspot profile. If it isn't set anywhere, a Pi that already has the profile keeps its password; one that doesn't fails the deploy before anything changes. To update just the hotspot: `ansible-playbook -i inventory.ini deploy_app.yml --tags wifi`.

**How it stays reachable**

- The watchdog (`wifi/wifi_fallback.py`, service `plot-runner-wifi`) uses system Python and the standard library only. It's installed in `/usr/local/lib/plot-runner-wifi`, not the app directory, so a broken app or venv doesn't affect it. systemd restarts it forever.
- Every switch ends with the Pi on WiFi or the hotspot up. Joining a new network adds a profile; if it fails, only that profile is deleted and the Pi returns to the previous network or the hotspot. Saved networks are never changed or removed except with **Forget**.
- The fallback can't be turned off from the page, and the timings are clamped (hotspot after 30–900 s, retry every 2–60 min).
- It turns the WiFi radio back on if it's off, and restarts NetworkManager if it stops answering.
- **Escape hatch:** if the Pi joins a network you can't reach it on, put an empty file named `force-hotspot` (or `force-hotspot.txt`) on the SD card's boot partition. The hotspot stays up while the file exists; delete it to go back to WiFi.

Only Pis running NetworkManager get the hotspot (Raspberry Pi OS bookworm and later); others are skipped with a message. `deploy/install.sh` doesn't install it. Logs: `sudo journalctl -u plot-runner-wifi -f`.

## Configuration

Edit `config.json` before starting the service. Key settings:

```json
{
  "plotter_settings": {
    "speed_pendown": 25,
    "speed_penup": 75,
    "pen_pos_down": 40,
    "pen_pos_up": 60,
    "model": 8
  }
}
```

Config overrides can also be sent per-plot request (see API below).

## API

Base URL: `http://<pi-ip>/`

### Status

```
GET /health
GET /status
GET /logs?lines=100
```

### SVG management

```
POST   /api/svg          Upload SVG (multipart/form-data, field: "file")
POST   /api/svg          Chunked upload (fields: chunk_data, chunk_number, total_chunks, file_id, filename)
GET    /api/svg          Get current SVG info and available layers
GET    /api/svg/filename Get original filename
DELETE /svg/clear        Clear current SVG
```

SVG uploads replace the current file. Layers are extracted automatically from Inkscape layer groups.

### Arming (Plot Runner panel)

```
POST   /arm    Arm a layer of the loaded SVG on the panel; plotting starts when Start is pressed
GET    /arm    Panel state, armed job, last event
DELETE /arm    Cancel the armed job
```

Upload the SVG with a `job_id` form field first: `/arm` is refused unless the job matches. See [docs/arming-api.md](docs/arming-api.md) for the fields and responses.

Set `PLOT_RUNNER_DISPLAY_PORT=/dev/ttyACM0` to skip USB auto-detection of the panel.

### Plotting

```
POST /plot/<layer_name>   Start plot — use a layer name, layer ID, or "all"
POST /plot/stop           Stop current plot
POST /plot/pause          Pause current plot
POST /plot/resume         Resume paused plot
```

Plot request body (all fields optional):

```json
{
  "config_content": { "speed_pendown": 30 },
  "time_data": { ... },
  "progress_in_mm": 1500
}
```

- `config_content` — NextDraw option overrides applied to this plot only
- `time_data` — Stored and reported in `/status` while plotting
- `job_id`, `ink_color`, `ink_name`, `estimated_time`, `elapsed_time` — Shown on the panel's progress countdown (falls back to `time_data.project_duration` / `layer_color`). See [docs/arming-api.md](docs/arming-api.md)

A `POST /plot` replaces any armed job on the panel.
- `progress_in_mm` — Resume plotting from this position (in mm × 100)
- `homing` — `true`/`false` overrides `config_content`'s homing (NextDraw defaults to on). Use `false` for plotters without a homing switch, e.g. the AxiDraw on nd-radius

`POST /plot/<layer>` returns `202 Accepted` immediately; the plot runs in a background thread. Poll `/status` to track progress.

### Utility commands

```
POST /utility/home
POST /utility/disable_motors
POST /utility/bullseye
POST /utility/set_pen_z     body: { "direction": "raise"|"lower", "position": 50 }
```

## Plotter status values

| Status | Meaning |
|---|---|
| `IDLE` | Ready for a new job |
| `PLOTTING` | Plot in progress |
| `PAUSED` | Paused, can be resumed |
| `ERROR` | Failed; check `last_error` in `/status` |
| `DISCONNECTED` | No plotter detected |

## NextDraw API

Version 1.7.3, installed from:
```
https://software-download.bantamtools.com/nd/1_7_3/nd_api_173.zip
```

This is included in `requirements.txt` and installed automatically by `pip install -r requirements.txt`.
