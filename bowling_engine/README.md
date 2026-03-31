# Bowling Simulation Engine

This project exposes one public URL and switches behavior with query parameters, exactly as the assignment requires.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Then open:

- Frame mode: `http://127.0.0.1:5000/?mode=frame&skill=0.75&seed=42&isLastFrame=0`
- Game mode: `http://127.0.0.1:5000/?mode=game&skill=0.75&seed=42`
- Visualization mode: `http://127.0.0.1:5000/?mode=viz&skill=0.75&seed=42`

## Deploy from GitHub

GitHub Pages cannot run a Python server, so the easiest GitHub-based workflow is:

1. Push this folder to a GitHub repository.
2. Connect the repo to Render, Railway, Replit, or another Python host.
3. Start command: `python app.py`

If your host lets you set a web command, use a production server such as:

```bash
gunicorn app:app
```

## Query parameters

- `mode=frame|game|viz`
- `skill=<float in [0,1]>`
- `seed=<integer>`
- `isLastFrame=<0 or 1>` only when `mode=frame`

## Design notes

- Deterministic randomness comes from seeding once per request.
- `game` mode seeds once and simulates all 10 frames sequentially.
- Bowling scoring follows official strike/spare rules.
- `viz` uses the exact same engine as `game` and only changes presentation.
- Skill is mapped to a per-pin knockdown probability, with a small later-roll bonus to reflect easier spare shots when fewer pins remain.
