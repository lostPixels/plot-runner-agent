# Arming the Plot Runner panel: changes for the parent application

The Plot Runner panel on each Pi is now interactive. A plot can start in two
ways:

- **Armed.** The parent application **arms** one layer of a job. The panel
  shows the job, ink and estimated time with a **Start** button, and the plot
  begins when the operator presses Start.
- **Remote.** The parent starts the plot directly, as it does today. The panel
  goes straight to its progress countdown.

This document lists what the parent application sends for each. Everything
here is on the Pi's existing HTTP API (`http://<pi>/`).

## What changes, in short

| | Before | Now |
|---|---|---|
| Upload SVG | `POST /api/svg` | Same, **plus a `job_id` form field** |
| Start on the operator's Start press | n/a | **`POST /arm`** |
| Start now | `POST /plot/<layer>` | Same, **plus panel fields** (`job_id`, `ink_color`, `ink_name`, `estimated_time`) so the countdown shows the right job and ink |
| Cancel before start | n/a | `DELETE /arm` |
| Track progress | Poll `GET /status` | Same; it now also reports `current_job_id` and a `display` block |

Existing `POST /plot/<layer>` calls keep working unchanged. With only the old
`time_data` fields, the panel still shows a countdown (see
[the fallbacks](#fallbacks-for-existing-callers)).

## The flow

```
parent                          Pi (plot-runner-agent)                  panel
  │ POST /api/svg (job_id)          │                                     │
  │────────────────────────────────▶│ stores SVG + job_id + sha256        │
  │ POST /arm (job, layer, ink…)    │                                     │
  │────────────────────────────────▶│ checks SVG/job/layer/plotter ──ARMED▶│ Armed screen
  │◀──────────────── 200 armed_job  │                                     │
  │                                 │◀──────────────────────START_PLOT────│ operator presses Start
  │ GET /status (poll)              │ re-checks, starts the plot          │ countdown
  │────────────────────────────────▶│ plotter_status PLOTTING             │
  │                                 │ plot ends ───────────────────IDLE──▶│ Idle screen
  │ GET /status → IDLE              │                                     │
  │ POST /arm (next layer)          │                                     │
```

## 1. Upload the SVG with a `job_id`

Add a `job_id` field to the upload form. It ties the file on the Pi to your
job, and `POST /arm` is refused unless it names the same job.

Direct upload:

```
POST /api/svg
Content-Type: multipart/form-data

file=<svg file>
job_id=poster-07
```

Chunked upload: send `job_id` with chunk 0 (it's read from the first chunk).

```
chunk_data=<bytes>  chunk_number=0  total_chunks=12  file_id=...  filename=poster.svg  job_id=poster-07
```

The response's `svg` object (and `GET /api/svg`) now includes:

| Field | Notes |
|---|---|
| `job_id` | As uploaded, or `null` |
| `sha256` | Hex SHA-256 of the uploaded file. Optionally send it back in `POST /arm` as `svg_sha256` |

Uploading a new SVG or clearing it (`DELETE /svg/clear`) disarms any armed
job and returns the panel to Idle.

## 2. Arm a layer: `POST /arm`

```
POST /arm
Content-Type: application/json

{
  "job_id": "poster-07",
  "layer_name": "1",
  "ink_color": "#1E90FF",
  "ink_name": "Pilot G2 Blue",
  "estimated_time": 4530,
  "svg_sha256": "9f2c…",
  "config_content": { "speed_pendown": 30 },
  "progress_in_mm": 0,
  "time_data": { }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `job_id` | string or integer | yes | Must equal the `job_id` the SVG was uploaded with. Strings are recommended; they're compared as text, so `42` matches an upload of `"42"`. Shown on the panel. |
| `layer_name` | string | yes | The layer to plot, exactly as you'd pass it to `POST /plot/<layer>`: a layer name or id from the SVG, or `"all"`. |
| `ink_color` | string | yes | `"#RRGGBB"` (`#` optional, any case). Fills the ink swatch. Previously sent as `time_data.layer_color`. |
| `ink_name` | string | no | Shown next to the swatch. |
| `estimated_time` | number, seconds | yes | `>= 0`, a JSON number, not a string. Shown on the Armed screen and drives the panel's countdown. Previously sent as `time_data.project_duration`. When resuming with `progress_in_mm`, send the **remaining** time. |
| `svg_sha256` | string | no | If present, must match the loaded file's `sha256`. Recommended: it catches a stale or partial upload that kept the right `job_id`. |
| `config_content` | object | no | NextDraw option overrides for this plot, the same as the `POST /plot` body. Stored now and applied when Start is pressed. |
| `progress_in_mm` | number | no | Resume position, the same as the `POST /plot` body. |
| `time_data` | object | no | Stored and reported back in `/status` while the plot runs, as before. No longer sent to the panel. |

The panel's line limit is 1023 bytes, so keep `job_id`, `layer_name` and
`ink_name` short. They're only for display, so this is easy to stay under.

### Checks, in order

| Status | When |
|---|---|
| `400` | A field is missing or has the wrong type (`error` names the field), or the ARMED line would exceed 1023 bytes |
| `409` | No SVG is loaded or its upload hasn't finished |
| `409` | The loaded SVG has no `job_id` (re-upload it with one) |
| `409` | The SVG's `job_id` differs (`svg_job_id` and `requested_job_id` are returned) |
| `409` | `svg_sha256` doesn't match (`svg_sha256` of the loaded file is returned) |
| `404` | `layer_name` isn't in the SVG (`available_layers` is returned) |
| `409` | The plotter is busy (`plotter_status` isn't `IDLE`) |
| `503` | The panel isn't connected |
| `502` / `504` | The panel rejected the request or didn't reply |
| `200` | Armed. Returns `{"message": "Armed", "armed_job": {...}}` |

Every error body has an `error` string.

Arming again while a job is armed replaces it. Only one job is armed at a time.

### Arm the next layer only after the plotter is idle

Arming is refused while a plot is running. After a plot, wait until
`GET /status` shows `system.plotter_status == "IDLE"`, then arm the next layer.

## 3. What happens after arming

You don't need to do anything else; this is what the Pi does by itself.

- **Start pressed.** The Pi checks that the panel's `job_id`/`layer_name` match
  the armed job, that the SVG hasn't changed since arming, and that the
  plotter is idle. Then it starts the plot with the stored `config_content` and
  `progress_in_mm`. If any check fails, it doesn't plot, it returns the panel to
  Idle, and it records the reason in `display.last_error`.
- **Not started within 10 minutes.** The panel disarms itself. The Pi clears
  the job and sets `display.last_disarm.reason` to `"timeout"`. Arm again to
  retry.
- **Plot runs.** The countdown follows the plotter as described in
  [While a plot runs](#5-while-a-plot-runs).
- **Panel resets or is unplugged.** It loses its state. The Pi checks the
  panel's status every 15 s and on reconnect, and clears the armed job if the
  panel no longer shows it (`last_disarm.reason` is `"device_idle"`).

## 4. Start a plot remotely: `POST /plot/<layer>`

This starts the plot immediately, with no Start press, and the panel shows the
progress countdown. The existing body fields are unchanged; the panel fields
are new and optional.

```
POST /plot/1
Content-Type: application/json

{
  "job_id": "poster-07",
  "ink_color": "#EE0E99",
  "ink_name": "Magenta",
  "estimated_time": 1800,
  "elapsed_time": 0,
  "svg_sha256": "9f2c…",
  "config_content": { "speed_pendown": 30 },
  "progress_in_mm": 0,
  "time_data": { }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `job_id` | string or integer | no | Shown on the panel and reported as `current_job_id`. If given, and the SVG was uploaded with a `job_id`, the two must match (`409` otherwise). |
| `ink_color` | string | no | `"#RRGGBB"`. |
| `ink_name` | string | no | Shown next to the swatch. |
| `estimated_time` | number, seconds | no | Drives the countdown. **Without an estimate (here or in `time_data`), the plot still runs but the panel stays on Idle.** |
| `elapsed_time` | number, seconds | no | How far into the plot this already is, e.g. when resuming with `progress_in_mm` and `estimated_time` is the job's full length. Defaults to `0`. |
| `svg_sha256` | string | no | If given, must match the loaded file (`409` otherwise). |
| `config_content`, `progress_in_mm`, `time_data` | | no | Unchanged. |

A panel field with the wrong type (say `"ink_color": "red"` or
`"estimated_time": "60"`) gets a `400` and nothing is plotted. As before, it's
`409` if the plotter is busy and `404` if the layer doesn't exist.

A remote start replaces anything armed (`last_disarm.reason` is
`"remote_plot"`).

### Fallbacks for existing callers

Each panel field that's missing falls back to the following:

| Panel field | Falls back to |
|---|---|
| `job_id` | The SVG's upload `job_id`, then its filename |
| `estimated_time` | `time_data.project_duration` |
| `ink_color` | `time_data.layer_color` (not for layer `"all"`), then white |

## 5. While a plot runs

These apply to both armed and remote plots:

- **Pause** (`POST /plot/pause`) returns the panel to Idle.
- **Resume** (`POST /plot/resume`) puts the countdown back, picking up from
  where it paused.
- **Stop** (`POST /plot/stop`) and plot completion return the panel to Idle.
- **Panel resets or reconnects mid-plot:** the Pi puts the countdown back,
  with the time already elapsed, within 15 s.

The countdown is only an estimate. If a plot overruns, the panel goes to
Idle when its countdown hits zero, while the plotter keeps going.

## 6. Cancel an armed job: `DELETE /arm`

```
DELETE /arm
→ 200 {"message": "Disarmed", "disarmed": true}
```

Returns the panel to Idle. `disarmed` is `false` if nothing was armed. To
cancel a running plot, use `POST /plot/stop` as before.

## 7. Track state: `GET /status`

`system` has two new fields, and there is a new `display` block (also
available on its own from `GET /arm`):

```json
{
  "system": {
    "plotter_status": "PLOTTING",
    "current_layer": "1",
    "current_job_id": "poster-07",
    "plot_source": "display",
    "time_data": null,
    "uptime_start": "…"
  },
  "svg": { "job_id": "poster-07", "sha256": "9f2c…", "...": "…" },
  "display": {
    "connected": true,
    "port": "/dev/ttyACM0",
    "device_state": "PLOTTING",
    "device_status_at": "2026-11-09T12:13:16",
    "idle_gif": true,
    "armed_job": null,
    "active_plot": {
      "job_id": "poster-07", "layer_name": "1", "ink_color": "#1E90FF",
      "ink_name": "Pilot G2 Blue", "estimated_time": 4530, "progress_in_mm": 0,
      "armed_at": "…", "started_at": "…", "svg_sha256": "9f2c…", "svg_filename": "poster.svg",
      "source": "display", "paused": false, "shown_on_panel": true, "elapsed_time": 612.4
    },
    "last_event": {"command": "START_PLOT", "job_id": "poster-07", "layer_name": "1", "received_at": "…"},
    "last_disarm": null,
    "last_error": null
  }
}
```

| Field | Meaning |
|---|---|
| `system.current_job_id` | Job being plotted (`null` when idle). |
| `system.plot_source` | `"display"` (Start pressed), `"api"` (`POST /plot`), `"bullseye"` or `null`. |
| `display.armed_job` | Armed and waiting for Start, or `null`. |
| `display.active_plot` | The running or paused plot, or `null`. `source` is `"display"` (Start pressed) or `"api"` (remote). `shown_on_panel` is `false` when there was no estimate. `elapsed_time` excludes time spent paused. |
| `display.last_disarm` | Last time an armed job was cleared without plotting: `{job_id, layer_name, reason, at}`. `reason` is `timeout`, `host`, `svg_changed`, `remote_plot`, `device_idle` or `start_refused`. |
| `display.last_error` | Last refused Start, or a countdown that couldn't be shown: `{error, event, job_id, layer_name, at}`. |
| `display.device_state` | The panel's last reported state: `IDLE`, `ARMED`, `PLOTTING`, or `null` if disconnected. |

Telling outcomes apart while polling:

- **Started:** `plotter_status` becomes `PLOTTING`, `current_job_id` is yours, and `plot_source` is `"display"`.
- **Timed out or cancelled:** `armed_job` becomes `null` and `last_disarm` names your job with its reason.
- **Start refused:** `last_error` names your job.

## Example

```bash
PI=http://nd-radius.local

curl -F file=@poster.svg -F job_id=poster-07 $PI/api/svg

curl -X POST $PI/arm -H 'Content-Type: application/json' -d '{
  "job_id": "poster-07", "layer_name": "1",
  "ink_color": "#1E90FF", "ink_name": "Pilot G2 Blue",
  "estimated_time": 4530, "config_content": {"speed_pendown": 30}
}'

curl $PI/status        # poll until plotter_status is IDLE again

# Or start the next layer now, without a Start press:
curl -X POST $PI/plot/2 -H 'Content-Type: application/json' -d '{
  "job_id": "poster-07", "ink_color": "#EE0E99", "ink_name": "Magenta", "estimated_time": 1800
}'
```

## Bullseye

The panel's Tools screen has a **Draw Bullseye** button. The Pi draws the
bullseye when it's pressed, as long as the plotter is idle and nothing is
armed. The parent application doesn't need to do anything for this.
