# plot-runner-agent

Flask API server for controlling a NextDraw plotter from a Raspberry Pi. Accepts SVG uploads and executes plots by layer, with pause/resume support and a serial display integration.

## Architecture

- **`app.py`** — Flask server, route definitions, background status sync thread
- **`plotter_controller.py`** — Wraps the NextDraw API; handles job execution, pause/resume, and utility commands
- **`svg_manager.py`** — Stores the active SVG, extracts layer info, handles chunked uploads
- **`serial_communication.py`** — Serial link to the Plot Runner panel (LilyGo T-Display S3 AMOLED): reconnects, sends `AT`/`ARMED`/`IDLE`/`STATUS`, and dispatches the panel's events
- **`display_jobs.py`** — Armed-job state: checks an arm request against the loaded SVG, starts the plot when Start is pressed on the panel, keeps the panel in step. The panel is optional; plotting works without it
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
