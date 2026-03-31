# Written Explanation: Deterministic Bowling Simulation Engine

## Overview

For this project, I built a deterministic bowling simulation engine that is accessed through one public URL and changes behavior depending on the query parameter `mode`. The three supported modes are `frame`, `game`, and `viz`. The main idea behind the project is that the URL should behave like a stateless function:

`output = f(mode, skill, seed, ...)`

This means that if the same inputs are used multiple times, the output should be identical every time. That requirement is what makes the project more than just a small game. It turns the program into a reproducible simulation engine that could be used for repeated analysis, tournament testing, or statistical experiments.

I also designed the project so that the simulation engine is separate from the visualization layer. The bowling logic generates rolls and scores, while the visualization only presents those results in a more readable form. Because of that separation, the same engine can return JSON for analysis in `frame` and `game` mode while also powering a retro neon visualization in `viz` mode.

## Skill Model

One of the most important design choices in the project was deciding how to map a skill value in `[0,1]` to bowling performance. I wanted a model that was easy to explain but still coherent enough to produce believable results. I chose to model bowling at the pin level rather than directly generating a frame total. In my engine, each standing pin has some probability of being knocked down on a given roll, and that probability depends on the bowler's skill.

The basic formula is:

`per_pin_probability = 0.10 + 0.78 * skill`

This gives even a low-skill bowler some chance of knocking down pins, while a high-skill bowler will usually knock down more pins per roll. As skill increases, the expected number of pins knocked down increases too. That naturally raises strike likelihood, improves spare conversion, and increases total score.

I also included a small bonus on second and third rolls. The reasoning is that follow-up shots are often easier in real bowling because fewer pins remain and the target becomes more focused. Instead of treating every roll exactly the same, the engine gives a modest bonus on later attempts, especially when fewer pins are standing. This helps the model reflect spare conversion in a simple way without adding unnecessary complexity.

I think this was a good design choice because it obeys bowling rules naturally. The engine never knocks down more pins than are actually standing, and the second roll only acts on the pins left after the first roll. That makes the simulation logical and keeps the model grounded in the structure of bowling itself.

## How Randomness Is Implemented

The simulation is stochastic, so randomness is necessary, but it also has to be reproducible. To make that happen, I used Python's seeded random number generator. For each request, the code creates a random generator one time using the supplied seed. After that, all random values are drawn sequentially from that same generator.

This matters most in `game` mode. The correct approach is to seed once at the beginning of the game and then simulate all 10 frames in order. I specifically avoided the common mistake of re-seeding inside each frame. If the program re-seeded repeatedly with the same seed, it could accidentally create repeated or unrealistic frames. By seeding once and then drawing values in sequence, the game behaves randomly but still remains perfectly reproducible.

In `frame` mode, the engine seeds once and simulates exactly one frame. In `game` mode, the engine seeds once and simulates all 10 frames. In both cases, the randomness is controlled entirely by the seed.

## How Seed Affects Behavior

The seed is the reason the engine is deterministic. If the same values for `mode`, `skill`, `seed`, and any other required parameters are used, the output will be identical every time. For example, if someone calls:

`/?mode=game&skill=0.75&seed=42`

multiple times, the exact same rolls, frame scores, and total score will appear every time. If the seed changes, then the sequence of random draws changes, and the game changes as well.

This creates the balance the assignment is asking for. The model is still random in the sense that different seeds produce different games, but it is controlled randomness rather than uncontrolled randomness. That is important for scientific integrity, reproducibility, and fair comparisons. It also means that the engine could be used to estimate strike rates, spare rates, average scores, or tournament outcomes in a repeatable way.

## Frame Simulation Design

In `frame` mode, the engine simulates exactly one frame and returns JSON. The required inputs are `mode=frame`, `skill`, `seed`, and `isLastFrame`. I made sure the frame simulation follows official bowling constraints.

If `isLastFrame=0`, the engine simulates a normal frame. The player gets one roll, and if that roll is a strike, the frame ends immediately. Otherwise, the engine simulates a second roll using only the pins still standing. No third roll is allowed.

If `isLastFrame=1`, the engine uses 10th-frame rules. A third roll is allowed only if it is earned. A strike on the first roll earns two bonus rolls, and a spare across the first two rolls earns one bonus roll. If neither happens, the frame ends after two rolls. This matches official bowling rules.

I also made sure not to include `frame_score` in normal frame mode output, because strike and spare bonuses depend on future rolls. Those bonuses belong in full-game scoring, not in a stand-alone frame simulation.

## Full Game Simulation Design

In `game` mode, the engine simulates all 10 frames sequentially using one seeded random generator. It first generates the rolls frame by frame and then applies official bowling scoring.

The scoring rules are standard. An open frame is scored as the sum of its rolls. A spare is scored as 10 plus the next one roll. A strike is scored as 10 plus the next two rolls. For the 10th frame, any earned bonus rolls are already part of the frame itself, so the frame score is simply the sum of the rolls in that frame.

The JSON output contains `total_score` and exactly 10 frame objects. Each frame includes `frame_number`, `rolls`, `frame_score`, and `cumulative_score`. That structure makes the response both assignment-compliant and easy to use for later statistical analysis.

## Design Decisions and Assumptions

I made several choices to keep the system logical and consistent.

First, I used a per-pin probability model instead of directly generating totals for each frame. I think this is more coherent because it automatically respects bowling constraints. A roll can never knock down more pins than are standing, and follow-up rolls naturally depend on previous rolls.

Second, I added a modest bonus to later rolls to reflect easier spare attempts. This is still a simplification, but it captures an important part of bowling performance without making the engine too complicated.

Third, I intentionally kept the engine simpler than a fully physical simulation. The assignment emphasizes determinism, legal scoring, API compliance, and logical consistency more than perfect realism. Because of that, I focused on building an engine that is believable, reproducible, and easy to explain rather than trying to create a full biomechanics model of bowling.

Another assumption is that skill acts as one overall performance variable. I did not create separate hidden variables for power, accuracy, spin, or mental composure. Instead, I treated skill as a single number that influences pin knockdown probability and spare conversion in a consistent way.

## Additional Features

Beyond the required JSON API, I added a visualization mode with a retro neon nighttime bowling aesthetic. This does not change the engine itself. It is only a presentation layer built on top of the same deterministic simulation results.

The full-game visualization shows a readable scoreboard with official frame scores and cumulative totals. I also added a frame-level animated replay inside `viz` mode. That replay includes an animated ball, a full pin rack, lane styling, and a frame scoreboard. To make the replay feel more realistic, I included simplified real-world style inputs such as release offset, hook, speed, entry angle, and an impact phase.

I want to be clear that this is still not a full rigid-body physics engine. The animation is a deterministic browser-based replay meant to look believable, not an exact real-world mechanics simulation. Still, it uses the same simulated frame result as the API, so it stays consistent with the underlying engine.

## Conclusion

Overall, this project is a deterministic simulation engine exposed as a small sports analytics API. The same inputs always produce the same outputs, different seeds produce different simulations, and the scoring follows official bowling rules. The skill model is simple but coherent, the randomness is controlled through a seed, and the visualization layer remains separate from the simulation logic.

Bowling is the context of the assignment, but the real product is the engine itself. That is why determinism, legal behavior, reproducibility, and logical consistency were the main priorities in my design.
