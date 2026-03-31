from __future__ import annotations

from flask import Flask, jsonify, request, Response
from html import escape
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


def pin_probability(skill: float, standing_pins: int, attempt_number: int) -> float:
    """
    Map skill in [0,1] to per-pin knockdown probability.
    Higher skill means a better chance to clear pins.
    Fewer standing pins on later rolls gets a small accuracy bonus.
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
    for frame_index in range(9):
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
    first = "X" if rolls[0] == 10 else str(rolls[0])
    out.append(first)

    if len(rolls) >= 2:
        if rolls[0] == 10:
            out.append("X" if rolls[1] == 10 else str(rolls[1]))
        elif rolls[0] + rolls[1] == 10:
            out.append("/")
        else:
            out.append(str(rolls[1]))

    if len(rolls) == 3:
        if rolls[1] == 10 and rolls[0] == 10:
            out.append("X" if rolls[2] == 10 else str(rolls[2]))
        elif rolls[0] != 10 and rolls[0] + rolls[1] == 10:
            out.append("X" if rolls[2] == 10 else str(rolls[2]))
        elif rolls[1] != 10 and rolls[1] + rolls[2] == 10 and rolls[0] == 10:
            out.append("/")
        else:
            out.append(str(rolls[2]))

    return " ".join(out)


def viz_response(skill: float, seed: int) -> Response:
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

    html = f"""
    <!doctype html>
    <html lang=\"en\">
    <head>
      <meta charset=\"utf-8\">
      <title>Bowling Visualization</title>
      <style>
        body {{ font-family: Arial, sans-serif; margin: 2rem; color: #1f2937; }}
        h1 {{ margin-bottom: 0.3rem; }}
        .meta {{ margin-bottom: 1rem; }}
        table {{ border-collapse: collapse; width: 100%; max-width: 900px; }}
        th, td {{ border: 1px solid #d1d5db; padding: 0.7rem; text-align: center; }}
        th {{ background: #eff6ff; }}
        .score {{ font-size: 1.2rem; font-weight: 700; margin: 1rem 0; }}
        code {{ background: #f3f4f6; padding: 0.1rem 0.3rem; border-radius: 4px; }}
      </style>
    </head>
    <body>
      <h1>Bowling Visualization</h1>
      <div class=\"meta\">Mode: <code>viz</code> | Skill: <code>{game['skill']}</code> | Seed: <code>{game['seed']}</code></div>
      <div class=\"score\">Total score: {game['total_score']}</div>
      <table>
        <thead>
          <tr>
            <th>Frame</th>
            <th>Rolls</th>
            <th>Frame Score</th>
            <th>Cumulative Score</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
      <p>This visualization uses the same deterministic simulation engine as the JSON API.</p>
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")


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

        return viz_response(skill, seed)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
