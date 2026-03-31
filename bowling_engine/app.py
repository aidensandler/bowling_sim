from __future__ import annotations

from flask import Flask, jsonify, request, Response
from html import escape
import json
import random
from typing import List, Dict, Any

app = Flask(__name__)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def parse_skill(raw: str | None) -> float:
    if raw is None:
        raise ValueError("Missing required query parameter: skill")
    try:
        skill = float(raw)
    except ValueError as exc:
        raise ValueError("skill must be a float in [0,1]") from exc
    if not 0.0 <= skill <= 1.0:
        raise ValueError("skill must be a float in [0,1]")
    return skill


def parse_seed(raw: str | None) -> int:
    if raw is None:
        raise ValueError("Missing required query parameter: seed")
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError("seed must be an integer") from exc


def parse_is_last_frame(raw: str | None) -> bool:
    if raw is None:
        raise ValueError("Frame mode requires isLastFrame=<0 or 1>")
    if raw not in {"0", "1", "true", "false", "True", "False"}:
        raise ValueError("isLastFrame must be 0 or 1")
    return raw in {"1", "true", "True"}


def parse_viz_scope(raw: str | None) -> str:
    if raw is None:
        return "game"
    if raw not in {"game", "frame"}:
        raise ValueError("vizScope must be either game or frame")
    return raw


# -------------------------
# Core simulation engine
# -------------------------

def pin_probability(skill: float, standing_pins: int, attempt_number: int) -> float:
    """
    Coherent skill model:
    - skill controls base per-pin knockdown chance
    - later rolls get a small spare-conversion bonus
    - fewer standing pins are a bit easier to clear accurately
    """
    base = 0.10 + 0.78 * skill
    spare_bonus = 0.12 * ((10 - standing_pins) / 10.0) if attempt_number >= 2 else 0.0
    return clamp(base + spare_bonus, 0.05, 0.98)



def roll_ball(standing_pins: int, skill: float, rng: random.Random, attempt_number: int) -> int:
    if standing_pins <= 0:
        return 0
    p = pin_probability(skill, standing_pins, attempt_number)
    knocked = sum(1 for _ in range(standing_pins) if rng.random() < p)
    return knocked



def simulate_non_final_frame(skill: float, rng: random.Random) -> List[int]:
    roll1 = roll_ball(10, skill, rng, attempt_number=1)
    if roll1 == 10:
        return [10]
    roll2 = roll_ball(10 - roll1, skill, rng, attempt_number=2)
    return [roll1, roll2]



def simulate_final_frame(skill: float, rng: random.Random) -> List[int]:
    roll1 = roll_ball(10, skill, rng, attempt_number=1)

    if roll1 == 10:
        roll2 = roll_ball(10, skill, rng, attempt_number=2)
        if roll2 == 10:
            roll3 = roll_ball(10, skill, rng, attempt_number=3)
        else:
            roll3 = roll_ball(10 - roll2, skill, rng, attempt_number=3)
        return [roll1, roll2, roll3]

    roll2 = roll_ball(10 - roll1, skill, rng, attempt_number=2)
    if roll1 + roll2 == 10:
        roll3 = roll_ball(10, skill, rng, attempt_number=3)
        return [roll1, roll2, roll3]

    return [roll1, roll2]



def simulate_frame(skill: float, seed: int, is_last_frame: bool) -> Dict[str, Any]:
    rng = random.Random(seed)
    rolls = simulate_final_frame(skill, rng) if is_last_frame else simulate_non_final_frame(skill, rng)

    payload: Dict[str, Any] = {
        "skill": skill,
        "seed": seed,
        "is_last_frame": is_last_frame,
        "roll1": rolls[0],
    }
    if len(rolls) >= 2:
        payload["roll2"] = rolls[1]
    if len(rolls) == 3:
        payload["roll3"] = rolls[2]
    return payload



def simulate_game_frames(skill: float, seed: int) -> List[List[int]]:
    rng = random.Random(seed)
    frames: List[List[int]] = []
    for _ in range(9):
        frames.append(simulate_non_final_frame(skill, rng))
    frames.append(simulate_final_frame(skill, rng))
    return frames



def frame_score(frames: List[List[int]], frame_index: int) -> int:
    frame = frames[frame_index]
    if frame_index == 9:
        return sum(frame)

    next_rolls: List[int] = []
    for later_frame in frames[frame_index + 1 :]:
        next_rolls.extend(later_frame)

    if frame[0] == 10:
        return 10 + next_rolls[0] + next_rolls[1]
    if sum(frame) == 10:
        return 10 + next_rolls[0]
    return sum(frame)



def simulate_game(skill: float, seed: int) -> Dict[str, Any]:
    frames = simulate_game_frames(skill, seed)
    details: List[Dict[str, Any]] = []
    running_total = 0

    for i in range(10):
        score = frame_score(frames, i)
        running_total += score
        details.append(
            {
                "frame_number": i + 1,
                "rolls": frames[i],
                "frame_score": score,
                "cumulative_score": running_total,
            }
        )

    return {
        "skill": skill,
        "seed": seed,
        "total_score": running_total,
        "frames": details,
    }



def render_rolls(rolls: List[int], frame_number: int) -> str:
    if frame_number < 10:
        if rolls == [10]:
            return "X"
        if len(rolls) == 2 and sum(rolls) == 10:
            return f"{rolls[0]} /"
        if len(rolls) == 2:
            return f"{rolls[0]} {rolls[1]}"
        return " ".join(str(r) for r in rolls)

    out: List[str] = []
    out.append("X" if rolls[0] == 10 else str(rolls[0]))
    if len(rolls) >= 2:
        if rolls[0] == 10:
            out.append("X" if rolls[1] == 10 else str(rolls[1]))
        elif rolls[0] + rolls[1] == 10:
            out.append("/")
        else:
            out.append(str(rolls[1]))
    if len(rolls) == 3:
        if rolls[0] == 10 and rolls[1] == 10:
            out.append("X" if rolls[2] == 10 else str(rolls[2]))
        elif rolls[0] == 10 and rolls[1] + rolls[2] == 10:
            out.append("/")
        else:
            out.append("X" if rolls[2] == 10 else str(rolls[2]))
    return " ".join(out)


# -------------------------
# Visualization helpers
# -------------------------

def build_frame_shot_data(skill: float, seed: int, is_last_frame: bool) -> Dict[str, Any]:
    frame_payload = simulate_frame(skill, seed, is_last_frame)
    rolls = [frame_payload["roll1"]]
    if "roll2" in frame_payload:
        rolls.append(frame_payload["roll2"])
    if "roll3" in frame_payload:
        rolls.append(frame_payload["roll3"])

    rng = random.Random(seed + 100003)
    shots: List[Dict[str, Any]] = []
    standing = 10
    rack_size = 10
    for i, knocked in enumerate(rolls, start=1):
        release_x = round(rng.uniform(-0.7, 0.7) * (1.1 - 0.55 * skill), 4)
        hook = round(rng.uniform(-0.16, 0.16) * (1.0 - 0.6 * skill), 4)
        speed_mps = round(6.1 + 1.7 * skill + rng.uniform(-0.22, 0.22), 3)
        rev_rate = round(220 + 180 * skill + rng.uniform(-15, 15), 2)
        entry_angle_deg = round(3.0 + 3.8 * skill + hook * 10.0, 3)
        impact_energy = round(0.5 * 6.8 * speed_mps * speed_mps, 3)
        shots.append(
            {
                "roll_number": i,
                "knocked": knocked,
                "standing_before": standing,
                "standing_after": max(standing - knocked, 0),
                "rack_size": rack_size,
                "release_x": release_x,
                "hook": hook,
                "speed_mps": speed_mps,
                "rev_rate": rev_rate,
                "entry_angle_deg": entry_angle_deg,
                "impact_energy_j": impact_energy,
            }
        )
        if is_last_frame and (i == 1 and knocked == 10 or i == 2 and rolls[0] == 10 or len(rolls) == 3 and i == 2 and rolls[0] + rolls[1] == 10):
            rack_size = 10
            standing = 10
        else:
            standing = max(standing - knocked, 0)
            rack_size = standing

    return {
        "frame": frame_payload,
        "shots": shots,
    }



def retro_shell(title: str, body: str, script: str = "") -> Response:
    html = f"""
    <!doctype html>
    <html lang=\"en\">
    <head>
      <meta charset=\"utf-8\">
      <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
      <title>{escape(title)}</title>
      <style>
        :root {{
          --bg1:#06030f;
          --bg2:#120b2c;
          --panel:rgba(13,10,34,.72);
          --line:#63f3ff;
          --pink:#ff4fd8;
          --yellow:#ffe66d;
          --text:#e8f6ff;
          --muted:#9cb9d8;
          --green:#6affb7;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin:0;
          min-height:100vh;
          font-family: Inter, Arial, sans-serif;
          color:var(--text);
          background:
            radial-gradient(circle at top, rgba(255,79,216,.15), transparent 28%),
            radial-gradient(circle at bottom, rgba(99,243,255,.12), transparent 28%),
            linear-gradient(180deg,var(--bg2),var(--bg1));
        }}
        .wrap {{ max-width: 1380px; margin: 0 auto; padding: 22px; }}
        .header {{ display:flex; justify-content:space-between; gap:16px; align-items:end; flex-wrap:wrap; margin-bottom:18px; }}
        h1 {{ margin:0; font-size: clamp(1.8rem, 3vw, 3rem); letter-spacing:.04em; text-transform:uppercase; text-shadow: 0 0 24px rgba(99,243,255,.45); }}
        .subtitle {{ color:var(--muted); margin-top:8px; }}
        .chips {{ display:flex; gap:10px; flex-wrap:wrap; }}
        .chip {{ border:1px solid rgba(99,243,255,.45); background:rgba(6,8,20,.5); padding:10px 14px; border-radius:999px; box-shadow: inset 0 0 20px rgba(99,243,255,.08), 0 0 18px rgba(99,243,255,.08); }}
        .grid {{ display:grid; grid-template-columns: 1.35fr .95fr; gap:18px; }}
        .panel {{ background:var(--panel); border:1px solid rgba(99,243,255,.28); border-radius:24px; padding:16px; box-shadow: 0 0 0 1px rgba(255,79,216,.08) inset, 0 15px 60px rgba(0,0,0,.25); backdrop-filter: blur(10px); }}
        .panel h2 {{ margin:0 0 12px; color:var(--yellow); font-size:1rem; letter-spacing:.12em; text-transform:uppercase; }}
        table {{ width:100%; border-collapse:collapse; overflow:hidden; border-radius:18px; }}
        th, td {{ padding:12px 10px; text-align:center; border-bottom:1px solid rgba(156,185,216,.18); }}
        th {{ color:var(--yellow); font-size:.8rem; letter-spacing:.12em; text-transform:uppercase; }}
        tr:last-child td {{ border-bottom:none; }}
        .scorecard td:first-child, .scorecard th:first-child {{ text-align:left; }}
        .big {{ font-size:2rem; font-weight:800; color:var(--green); text-shadow:0 0 18px rgba(106,255,183,.35); }}
        .mini {{ color:var(--muted); font-size:.9rem; }}
        .canvas-box {{ position:relative; border-radius:22px; overflow:hidden; background:#090612; border:1px solid rgba(255,255,255,.05); }}
        canvas {{ width:100%; height:auto; display:block; aspect-ratio: 16/9; }}
        .legend {{ display:grid; grid-template-columns: repeat(3, 1fr); gap:10px; margin-top:12px; }}
        .legend-item {{ background:rgba(255,255,255,.03); padding:10px 12px; border-radius:16px; }}
        .legend-item strong {{ display:block; color:var(--yellow); font-size:.82rem; margin-bottom:4px; letter-spacing:.08em; text-transform:uppercase; }}
        .code {{ white-space:pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background:rgba(255,255,255,.03); padding:14px; border-radius:16px; color:#ccefff; overflow:auto; }}
        a {{ color:var(--line); }}
        @media (max-width: 980px) {{ .grid {{ grid-template-columns:1fr; }} .legend {{ grid-template-columns:1fr; }} }}
      </style>
    </head>
    <body>
      <div class=\"wrap\">{body}</div>
      {script}
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")



def viz_response_game(skill: float, seed: int) -> Response:
    game = simulate_game(skill, seed)
    rows = []
    for frame in game["frames"]:
        rows.append(
            f"<tr>"
            f"<td>{frame['frame_number']}</td>"
            f"<td>{escape(render_rolls(frame['rolls'], frame['frame_number']))}</td>"
            f"<td>{frame['frame_score']}</td>"
            f"<td>{frame['cumulative_score']}</td>"
            f"</tr>"
        )

    body = f"""
    <div class=\"header\">
      <div>
        <h1>Neon Lanes</h1>
        <div class=\"subtitle\">Deterministic bowling game visualization using the same engine as the JSON API.</div>
      </div>
      <div class=\"chips\">
        <div class=\"chip\">Mode: <strong>viz</strong></div>
        <div class=\"chip\">Viz Scope: <strong>game</strong></div>
        <div class=\"chip\">Skill: <strong>{game['skill']}</strong></div>
        <div class=\"chip\">Seed: <strong>{game['seed']}</strong></div>
      </div>
    </div>
    <div class=\"grid\">
      <section class=\"panel\">
        <h2>Scoreboard</h2>
        <div class=\"big\">Total Score: {game['total_score']}</div>
        <table class=\"scorecard\">
          <thead>
            <tr><th>Frame</th><th>Rolls</th><th>Frame Score</th><th>Cumulative</th></tr>
          </thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </section>
      <section class=\"panel\">
        <h2>API Notes</h2>
        <div class=\"legend\">
          <div class=\"legend-item\"><strong>Single URL</strong><span>Use <code>/?mode=game</code>, <code>/?mode=frame</code>, or <code>/?mode=viz</code>.</span></div>
          <div class=\"legend-item\"><strong>Deterministic</strong><span>Same mode, skill, and seed return the same result every time.</span></div>
          <div class=\"legend-item\"><strong>Scoring</strong><span>Frames 1-9 use official strike and spare bonuses. Frame 10 sums earned bonus rolls.</span></div>
        </div>
        <p class=\"mini\">For an animated single-frame lane with a ball, pins, and a live frame scoreboard, call <code>/?mode=viz&amp;vizScope=frame&amp;skill=0.75&amp;seed=42&amp;isLastFrame=0</code>.</p>
        <div class=\"code\">{escape(json.dumps(game, indent=2))}</div>
      </section>
    </div>
    """
    return retro_shell("Neon Lanes - Full Game", body)



def viz_response_frame(skill: float, seed: int, is_last_frame: bool) -> Response:
    shot_data = build_frame_shot_data(skill, seed, is_last_frame)
    frame = shot_data["frame"]
    shots = shot_data["shots"]
    shots_json = json.dumps(shots)
    frame_json = escape(json.dumps(frame, indent=2))
    title_rolls = " / ".join(str(frame[k]) for k in ("roll1", "roll2", "roll3") if k in frame)

    score_table_rows = []
    for shot in shots:
        score_table_rows.append(
            f"<tr><td>Roll {shot['roll_number']}</td><td>{shot['knocked']}</td><td>{shot['standing_before']}</td><td>{shot['standing_after']}</td><td>{shot['speed_mps']} m/s</td><td>{shot['entry_angle_deg']}°</td></tr>"
        )

    body = f"""
    <div class=\"header\">
      <div>
        <h1>Neon Frame Replay</h1>
        <div class=\"subtitle\">Retro arcade styling with deterministic lane animation driven by the same frame engine.</div>
      </div>
      <div class=\"chips\">
        <div class=\"chip\">Mode: <strong>viz</strong></div>
        <div class=\"chip\">Viz Scope: <strong>frame</strong></div>
        <div class=\"chip\">Skill: <strong>{frame['skill']}</strong></div>
        <div class=\"chip\">Seed: <strong>{frame['seed']}</strong></div>
        <div class=\"chip\">Final Frame: <strong>{str(frame['is_last_frame']).lower()}</strong></div>
      </div>
    </div>
    <div class=\"grid\">
      <section class=\"panel\">
        <h2>Lane Animation</h2>
        <div class=\"canvas-box\"><canvas id=\"laneCanvas\" width=\"1200\" height=\"675\"></canvas></div>
        <div class=\"legend\">
          <div class=\"legend-item\"><strong>Approx. Speed</strong><span id=\"liveSpeed\">--</span></div>
          <div class=\"legend-item\"><strong>Entry Angle</strong><span id=\"liveAngle\">--</span></div>
          <div class=\"legend-item\"><strong>Ball Energy</strong><span id=\"liveEnergy\">--</span></div>
        </div>
      </section>
      <section class=\"panel\">
        <h2>Frame Scoreboard</h2>
        <div class=\"big\">Rolls: {escape(title_rolls)}</div>
        <table class=\"scorecard\">
          <thead>
            <tr><th>Shot</th><th>Pins Down</th><th>Standing Before</th><th>Standing After</th><th>Speed</th><th>Angle</th></tr>
          </thead>
          <tbody>{''.join(score_table_rows)}</tbody>
        </table>
        <p class=\"mini\">This animation uses simplified lane physics, not a full rigid-body simulation. The ball path includes release offset, hook, speed, and a deterministic impact phase for the exact pinfall generated by the engine.</p>
        <div class=\"code\">{frame_json}</div>
      </section>
    </div>
    """

    script = f"""
    <script>
      const shots = {shots_json};
      const canvas = document.getElementById('laneCanvas');
      const ctx = canvas.getContext('2d');
      const liveSpeed = document.getElementById('liveSpeed');
      const liveAngle = document.getElementById('liveAngle');
      const liveEnergy = document.getElementById('liveEnergy');

      const W = canvas.width;
      const H = canvas.height;
      const laneTopY = 78;
      const laneBottomY = H - 36;
      const foulY = H - 118;
      const pinDeckY = laneTopY + 40;
      const laneBottomWidth = 610;
      const laneTopWidth = 245;
      const centerX = W / 2;
      const ballRadius = 24;
      const pinSpacing = 34;
      const animationState = {{ rollIndex: 0, t: 0, knockedPins: new Set(), settledPins: new Set() }};

      const pinPattern = [1,2,3,4];
      function buildPins() {{
        const pins = [];
        let n = 0;
        for (let row = 0; row < 4; row++) {{
          const count = pinPattern[row];
          const rowY = pinDeckY + row * 30;
          const rowWidth = (count - 1) * pinSpacing;
          for (let i = 0; i < count; i++) {{
            pins.push({{
              id: n,
              x: centerX - rowWidth / 2 + i * pinSpacing,
              y: rowY,
              standing: true,
              falling: false,
              vx: 0,
              vy: 0,
              angVel: 0,
              angle: 0,
              fade: 1
            }});
            n += 1;
          }}
        }}
        return pins;
      }}

      let pins = buildPins();
      let lastFrameTime = 0;
      let impactTriggered = false;
      let rollPause = 0;

      function laneWidthAt(y) {{
        const ratio = (y - laneTopY) / (laneBottomY - laneTopY);
        return laneTopWidth + (laneBottomWidth - laneTopWidth) * Math.max(0, Math.min(1, ratio));
      }}

      function quad(a, b, c, t) {{ return (1-t)*(1-t)*a + 2*(1-t)*t*b + t*t*c; }}

      function getBallPos(shot, t) {{
        const startY = H - 60;
        const midY = (foulY + pinDeckY) / 2;
        const endY = pinDeckY + 68;
        const startX = centerX + shot.release_x * laneBottomWidth * 0.36;
        const midX = centerX + shot.release_x * 45 + shot.hook * 370;
        const endX = centerX + shot.hook * 120;
        return {{
          x: quad(startX, midX, endX, t),
          y: quad(startY, midY, endY, t)
        }};
      }}

      function resetRackForNextShot(shot) {{
        if (shot.rack_size === 10 && shot.standing_before === 10) {{
          pins = buildPins();
        }} else {{
          const standingNeeded = shot.standing_before;
          let standingCount = 0;
          pins.forEach(pin => {{
            pin.falling = false;
            pin.vx = 0; pin.vy = 0; pin.angVel = 0; pin.angle = 0;
            if (standingCount < standingNeeded) {{
              pin.standing = true; pin.fade = 1; standingCount += 1;
            }} else {{
              pin.standing = false; pin.fade = 0.08;
            }}
          }});
        }}
        impactTriggered = false;
        animationState.knockedPins = new Set();
        animationState.settledPins = new Set();
      }}

      function pickPinsToKnock(shot) {{
        const candidates = pins.filter(p => p.standing);
        const order = candidates.slice().sort((a,b) => {{
          const da = Math.abs(a.x - centerX) + (a.y - pinDeckY) * 0.3;
          const db = Math.abs(b.x - centerX) + (b.y - pinDeckY) * 0.3;
          return da - db;
        }});
        return order.slice(0, shot.knocked).map(p => p.id);
      }}

      function triggerImpact(shot) {{
        impactTriggered = true;
        const knockedIds = pickPinsToKnock(shot);
        animationState.knockedPins = new Set(knockedIds);
        const sign = shot.hook >= 0 ? 1 : -1;
        pins.forEach((pin, idx) => {{
          if (animationState.knockedPins.has(pin.id)) {{
            pin.falling = true;
            const spread = ((idx % 4) - 1.5) * 0.7;
            pin.vx = (1.8 + Math.abs(spread)) * sign + spread * 0.5;
            pin.vy = 2.2 + (idx % 3) * 0.45;
            pin.angVel = 0.04 * sign * (1 + (idx % 3));
          }}
        }});
      }}

      function updatePins(dt) {{
        pins.forEach(pin => {{
          if (!pin.falling) return;
          pin.x += pin.vx * dt * 60;
          pin.y += pin.vy * dt * 60;
          pin.vx *= 0.982;
          pin.vy *= 0.986;
          pin.angle += pin.angVel * dt * 60;
          pin.fade = Math.max(0.06, pin.fade - 0.0035 * dt * 60);
          if (Math.abs(pin.angle) > 1.25 || pin.y > laneBottomY - 30) {{
            pin.standing = false;
          }}
        }});
      }}

      function drawBackground() {{
        const bg = ctx.createLinearGradient(0, 0, 0, H);
        bg.addColorStop(0, '#120728');
        bg.addColorStop(1, '#06030f');
        ctx.fillStyle = bg;
        ctx.fillRect(0, 0, W, H);

        for (let i = 0; i < 40; i++) {{
          ctx.fillStyle = `rgba(255,255,255,${{0.02 + (i % 5) * 0.01}})`;
          ctx.beginPath();
          ctx.arc((i * 137) % W, (i * 89) % (laneTopY - 10), 1.4 + (i % 3), 0, Math.PI * 2);
          ctx.fill();
        }}
      }}

      function drawLane() {{
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(centerX - laneTopWidth / 2, laneTopY);
        ctx.lineTo(centerX + laneTopWidth / 2, laneTopY);
        ctx.lineTo(centerX + laneBottomWidth / 2, laneBottomY);
        ctx.lineTo(centerX - laneBottomWidth / 2, laneBottomY);
        ctx.closePath();
        const lane = ctx.createLinearGradient(0, laneTopY, 0, laneBottomY);
        lane.addColorStop(0, '#a66a28');
        lane.addColorStop(0.4, '#d18b34');
        lane.addColorStop(1, '#6a3b17');
        ctx.fillStyle = lane;
        ctx.fill();

        ctx.strokeStyle = 'rgba(99,243,255,0.6)';
        ctx.lineWidth = 3;
        ctx.stroke();

        for (let i = 1; i <= 4; i++) {{
          const y = laneTopY + i * ((laneBottomY - laneTopY) / 5);
          const half = laneWidthAt(y) / 2;
          ctx.strokeStyle = 'rgba(255,255,255,0.08)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(centerX - half, y);
          ctx.lineTo(centerX + half, y);
          ctx.stroke();
        }}

        const gutterGlow = ctx.createLinearGradient(0, laneTopY, 0, laneBottomY);
        gutterGlow.addColorStop(0, 'rgba(255,79,216,0.35)');
        gutterGlow.addColorStop(1, 'rgba(99,243,255,0.18)');
        ctx.strokeStyle = gutterGlow;
        ctx.lineWidth = 10;
        ctx.beginPath();
        ctx.moveTo(centerX - laneTopWidth / 2 - 12, laneTopY);
        ctx.lineTo(centerX - laneBottomWidth / 2 - 12, laneBottomY);
        ctx.moveTo(centerX + laneTopWidth / 2 + 12, laneTopY);
        ctx.lineTo(centerX + laneBottomWidth / 2 + 12, laneBottomY);
        ctx.stroke();

        ctx.strokeStyle = 'rgba(255,230,109,0.75)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(centerX - laneWidthAt(foulY) / 2, foulY);
        ctx.lineTo(centerX + laneWidthAt(foulY) / 2, foulY);
        ctx.stroke();
        ctx.restore();
      }}

      function drawPins() {{
        pins.forEach(pin => {{
          if (!pin.standing && pin.fade <= 0.06) return;
          ctx.save();
          ctx.translate(pin.x, pin.y);
          ctx.rotate(pin.angle);
          ctx.globalAlpha = pin.fade;
          ctx.fillStyle = '#f6fbff';
          ctx.strokeStyle = 'rgba(255,79,216,.6)';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(-7, 11);
          ctx.quadraticCurveTo(-8, 0, -3, -15);
          ctx.quadraticCurveTo(0, -24, 3, -15);
          ctx.quadraticCurveTo(8, 0, 7, 11);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();
          ctx.fillStyle = '#ff4fd8';
          ctx.fillRect(-6, -7, 12, 3);
          ctx.fillRect(-6, -1, 12, 3);
          ctx.restore();
        }});
      }}

      function drawBall(pos, shot) {{
        const glow = ctx.createRadialGradient(pos.x - 8, pos.y - 8, 4, pos.x, pos.y, ballRadius + 12);
        glow.addColorStop(0, '#ff85e7');
        glow.addColorStop(0.5, '#8d4dff');
        glow.addColorStop(1, 'rgba(99,243,255,0.2)');
        ctx.fillStyle = glow;
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, ballRadius + 8, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = '#2d155d';
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, ballRadius, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#63f3ff';
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.fillStyle = 'rgba(255,255,255,0.18)';
        ctx.beginPath();
        ctx.arc(pos.x - 7, pos.y - 6, 4, 0, Math.PI * 2);
        ctx.arc(pos.x + 2, pos.y - 9, 4, 0, Math.PI * 2);
        ctx.arc(pos.x + 8, pos.y - 1, 4, 0, Math.PI * 2);
        ctx.fill();

        liveSpeed.textContent = shot.speed_mps.toFixed(2) + ' m/s';
        liveAngle.textContent = shot.entry_angle_deg.toFixed(2) + '°';
        liveEnergy.textContent = shot.impact_energy_j.toFixed(0) + ' J';
      }}

      function drawHUD(shot) {{
        ctx.save();
        ctx.fillStyle = 'rgba(9, 8, 23, 0.74)';
        ctx.strokeStyle = 'rgba(99,243,255,.3)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.roundRect(22, 20, 290, 100, 18);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = '#ffe66d';
        ctx.font = '700 18px Inter, Arial';
        ctx.fillText(`ROLL ${{shot.roll_number}}`, 40, 48);
        ctx.fillStyle = '#e8f6ff';
        ctx.font = '15px Inter, Arial';
        ctx.fillText(`pins before: ${{shot.standing_before}}`, 40, 73);
        ctx.fillText(`pins down: ${{shot.knocked}}`, 40, 95);
        ctx.fillText(`pins after: ${{shot.standing_after}}`, 40, 117);
        ctx.restore();
      }}

      function render(now) {{
        if (!lastFrameTime) lastFrameTime = now;
        const dt = Math.min((now - lastFrameTime) / 1000, 0.03);
        lastFrameTime = now;
        drawBackground();
        drawLane();

        const shot = shots[animationState.rollIndex];
        if (!shot) {{
          drawPins();
          return;
        }}

        if (animationState.t === 0 && !impactTriggered) {{
          resetRackForNextShot(shot);
        }}

        animationState.t = Math.min(animationState.t + dt * 0.42, 1);
        const pos = getBallPos(shot, animationState.t);

        if (animationState.t > 0.86 && !impactTriggered) {{
          triggerImpact(shot);
        }}

        updatePins(dt);
        drawPins();
        drawBall(pos, shot);
        drawHUD(shot);

        if (animationState.t >= 1) {{
          rollPause += dt;
          if (rollPause > 1.05) {{
            rollPause = 0;
            animationState.rollIndex += 1;
            animationState.t = 0;
          }}
        }}

        requestAnimationFrame(render);
      }}

      requestAnimationFrame(render);
    </script>
    """

    return retro_shell("Neon Lanes - Frame Replay", body, script)



def viz_response(skill: float, seed: int, viz_scope: str, is_last_frame: bool | None) -> Response:
    if viz_scope == "frame":
        return viz_response_frame(skill, seed, bool(is_last_frame))
    return viz_response_game(skill, seed)


@app.route("/", methods=["GET"])
def index():
    try:
        mode = request.args.get("mode")
        if mode not in {"frame", "game", "viz"}:
            raise ValueError("mode must be one of: frame, game, viz")

        skill = parse_skill(request.args.get("skill"))
        seed = parse_seed(request.args.get("seed"))

        if mode == "frame":
            is_last_frame = parse_is_last_frame(request.args.get("isLastFrame"))
            return jsonify(simulate_frame(skill, seed, is_last_frame))

        if mode == "game":
            return jsonify(simulate_game(skill, seed))

        viz_scope = parse_viz_scope(request.args.get("vizScope"))
        is_last_frame = parse_is_last_frame(request.args.get("isLastFrame", "0")) if viz_scope == "frame" else None
        return viz_response(skill, seed, viz_scope, is_last_frame)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
