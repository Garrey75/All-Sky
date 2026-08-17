# All-Sky

Personal all-sky camera station software for **Garrey**.

It captures a zenith-centered 180° frame on a schedule, stores a dated archive, and builds the two products all-sky operators actually look at: a **keogram** (time running left to right) and a **star-trail** stack.

Out of the box it runs a physically timed sky simulator — Sun position, sidereal star drift, dusk color — so the dashboard works without a Raspberry Pi or camera. Point a real capture pipeline at `data/inbox/` and turn `demo_mode` off when you have hardware.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.json config.json
python -m allsky --seed    # optional: write a demo night
python -m allsky           # http://127.0.0.1:8080
```

## Configure

`config.json` (see `config.example.json`):

| Field | Meaning |
| --- | --- |
| `station_name` / `operator` | Overlay and dashboard identity |
| `latitude` / `longitude` | Used for Sun altitude and star projection |
| `capture_interval_seconds` | Live capture cadence |
| `demo_mode` | `true` = simulator, `false` = newest file in `data/inbox/` |
| `image_size` | Square output size in pixels |

## Tests

```bash
pytest
```

## Layout

```
allsky/     station server, astronomy, simulator, products, dashboard
data/       captures, latest frame, keograms, star trails
tests/
```
