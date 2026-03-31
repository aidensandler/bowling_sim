# Bowling Simulation Engine

This project implements a deterministic bowling simulation engine behind a **single Flask URL**. The behavior changes based on the required `mode` query parameter.

## Public API

Base route:

`/`

Supported query parameters for all modes:
- `mode=frame | game | viz`
- `skill=<float in [0,1]>`
- `seed=<integer>`

Additional required parameter for frame simulation:
- `isLastFrame=<0 or 1>`

Optional visualization parameter:
- `vizScope=game | frame`

## Required Modes

### 1) Frame mode
Returns JSON for exactly one frame.

Example non-final frame:

`/?mode=frame&skill=0.75&seed=42&isLastFrame=0`

Example 10th frame:

`/?mode=frame&skill=0.75&seed=42&isLastFrame=1`

Notes:
- RNG is initialized **once** using the provided seed.
- Exactly one frame is simulated.
- For frames 1-9, a third roll is never allowed.
- For frame 10, a third roll is allowed only if earned by a strike or spare.
- Output is deterministic for the same input parameters.
- No `frame_score` is included in ordinary frame mode output.

### 2) Game mode
Returns JSON for a full 10-frame game with official scoring.

Example:

`/?mode=game&skill=0.75&seed=42`

Notes:
- RNG is initialized **once** at the start of the game.
- The game is simulated sequentially for all 10 frames.
- The program does **not** re-seed inside frames.
- Output contains:
  - `total_score`
  - exactly 10 frame objects
  - `frame_number`
  - `rolls`
  - `frame_score`
  - `cumulative_score`

### 3) Visualization mode
Returns human-readable HTML built from the same deterministic engine.

Full game scoreboard:

`/?mode=viz&skill=0.75&seed=42`

Animated frame replay:

`/?mode=viz&vizScope=frame&skill=0.75&seed=42&isLastFrame=0`

Notes:
- `viz` uses the same simulation logic as `frame` and `game`.
- The full-game visualization shows the scoreboard and official scoring.
- The frame visualization includes an animated bowling ball, pins, scoreboard, and retro neon styling.
- The animation uses simplified but believable lane physics inputs such as release offset, hook, speed, and entry angle.

## Determinism

This project is designed to behave like a stateless function:

`output = f(mode, skill, seed, ...)`

That means:
- If the same URL is called multiple times with the same inputs, it returns the same result.
- If the seed changes, the result changes.
- `frame` and `game` return deterministic JSON.
- `viz` is also deterministic because it is driven by the same underlying simulation output.

## Skill Model

The model maps `skill` in `[0,1]` to bowling performance using a per-pin knockdown probability.

Core idea:
- Each standing pin has some probability of being knocked down.
- Higher skill increases that probability.
- Later rolls get a modest bonus to reflect easier spare conversion.

This model was chosen because it:
- obeys bowling constraints naturally
- increases strike and spare likelihood as skill increases
- remains simple enough to explain clearly in the written portion

## Project Files

- `app.py` — Flask app, simulation engine, scoring logic, and visualizations
- `requirements.txt` — Python dependency list
- `WRITTEN_EXPLANATION.md` — 1–4 page written explanation for submission

## Run Locally

```bash
pip install -r requirements.txt
python app.py
```

Then open one of these in your browser:

```text
http://127.0.0.1:5000/?mode=frame&skill=0.75&seed=42&isLastFrame=0
http://127.0.0.1:5000/?mode=frame&skill=0.75&seed=42&isLastFrame=1
http://127.0.0.1:5000/?mode=game&skill=0.75&seed=42
http://127.0.0.1:5000/?mode=viz&skill=0.75&seed=42
http://127.0.0.1:5000/?mode=viz&vizScope=frame&skill=0.75&seed=42&isLastFrame=0
```

## Hosting

This project is ready to be stored in GitHub for version control. To get **one public URL**, deploy the repository on a Python-capable host such as:
- Render
- Railway
- Replit

Plain GitHub Pages alone cannot run Flask because it only hosts static files.
