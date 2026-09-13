"""Rate ONE brain efficiently on the full-population matchmaker.

Fixed-seed proposing (MINE + 4 info-optimal full-pool complements via
matchmake.propose logic) with slot rotation (MINE cycles F0-F4) for
position control, duplicate-field assert (deterministic games must not
repeat: same field -> same game -> zero information + inflates ratings),
and tip-of-master compliance (elo_field.bot_cmd + master_map: HEAD engine/
runner/map, worktree brains only). After: verify no cross-run duplicates
(count records + exact field+scores match) before judging (>=15g).
Usage: PYTHONPATH=src:benchmarks python benchmarks/rate_brain.py <name-sha> <N> <SEED>
"""
import json, sys, time, random
from pathlib import Path
sys.path.insert(0, "src"); sys.path.insert(0, "benchmarks")
from runner.main import run_game
from elo_field import ensure_worktree, update, sha_of, bot_cmd, ensure_master_engine, master_map
from matchmake import pool, ratings, info_score, brain_hash
from openskill.models import BradleyTerryFull
ensure_master_engine()  # tip-of-master engine/runner (methodology)
from engine.config import GameConfig  # noqa: E402 (main-tip)
cfg = GameConfig.from_dict(master_map())
py = sys.executable
MINE = sys.argv[1]          # e.g. aggressive-629c059 (code-commit name)
N = int(sys.argv[2])
SEED = int(sys.argv[3]) if len(sys.argv) > 3 else 0
m = BradleyTerryFull()
elo = ratings()
# Twin exclusion (methodology): same-content brains (renames/reseeds) in one
# field measure slots, not brains (mirror matches went 4-3 on pure position
# noise). Exclude every pool entry whose package content-hash == MINE's.
_mine_name, _mine_commit = MINE.rsplit("-", 1)
_mine_hash = brain_hash(sha_of(_mine_commit), _mine_name)
_hash_cache: dict[str, str | None] = {}
def _content_hash(spec: str):
    if spec not in _hash_cache:
        try:
            nm, cm = spec.rsplit("-", 1)
            _hash_cache[spec] = brain_hash(sha_of(cm), nm)
        except Exception:
            _hash_cache[spec] = None
    return _hash_cache[spec]
cands = [c for c in pool() if c != MINE and _content_hash(c) != _mine_hash]
print(f"twin-exclusion: {len(pool())} pool -> {len(cands)} candidates (mine hash {_mine_hash})")
rng = random.Random(SEED)
def cmd(spec):
    name, commit = spec.rsplit("-", 1)
    return bot_cmd(name, sha_of(commit))
fh = open("benchmarks/elo_games.jsonl", "a")
seen_fields = set()
seen_ckeys = set()
# Global dedup (methodology): seed from DB history so no grind ever replays
# ANY historical field (the x27/x21 mirror-repeat epidemic: info-optimal
# reconverges on played fields across runs; within-run sets don't catch it).
# Slot-sensitive (slot-swaps are different games); content-keyed too.
try:
    _hist = open("benchmarks/elo_games.jsonl").read().splitlines()
except FileNotFoundError:
    _hist = []
for _ln in _hist:
    try:
        _g = json.loads(_ln)
        _f = {int(s): n for s, n in _g["field"].items()}
        seen_fields.add(tuple(_f[s] for s in range(5)))
        seen_ckeys.add(tuple((_f[s].rsplit("-", 1)[0], _content_hash(_f[s])) for s in range(5)))
    except Exception:
        continue
print(f"global-dedup: {len(seen_fields)} historical fields banned")
for i in range(N):
    # fixed-seed propose: MINE + 4 info-optimal full-pool complements.
    # Skip-seen (methodology): info-optimal converges on one best field
    # (deterministic replay = zero info); ban seen complement sets and
    # descend the info ranking (stays strong). Exhaustion stops gracefully.
    field = None
    banned = set()
    for attempt in range(12):
        field_names = [MINE]
        rest = [c for c in cands if c not in field_names and c not in banned]
        if len(rest) < 4:
            break
        while len(field_names) < 5 and rest:
            scored = sorted(rest, key=lambda k: -info_score(m, field_names + [k], elo))
            eps = min(0.9, 0.2 + 0.07 * attempt)
            pick = scored[0] if rng.random() < 1 - eps else rng.choice(scored[:min(3, len(scored))])
            field_names.append(pick)
            rest = [c for c in rest if c != pick]
        # rotate MINE through slots (position control); opponents fill rest in order
        slot = i % 5
        opps = [x for x in field_names if x != MINE]
        field = {}
        oi = 0
        for s in range(5):
            if s == slot:
                field[s] = MINE
            else:
                field[s] = opps[oi]; oi += 1
        key = tuple(field[s] for s in range(5))
        # Content-based dup check (methodology): same NAMES twice is rare;
        # the real recurrence is same-CONTENT twins replaying the identical
        # deterministic game (h2h triple-count lesson).
        ckey = tuple((field[s].rsplit("-", 1)[0], _content_hash(field[s])) for s in range(5))
        if key not in seen_fields and ckey not in seen_ckeys:
            break
        banned.update(opps)
        field = None
    if field is None:
        print(f"game {i}: pool exhausted (all top fields seen), stopping early")
        break
    seen_fields.add(key); seen_ckeys.add(ckey)
    cmds = {s: cmd(spec) for s, spec in field.items()}
    scores = run_game(cfg, cmds, None)
    sc = {s: float(scores.get(s, 0)) for s in range(5)}
    update(elo, field, sc)
    ranked = sorted(sc, key=lambda s: -sc[s])
    desc = " ".join(f"{field[s]}:{round(sc[s])}" for s in ranked)
    mp = next(k+1 for k, s in enumerate(ranked) if field[s] == MINE)
    print(f"g{i} [mineF{slot}]: {desc}  [mine {mp}th]", flush=True)
    fh.write(json.dumps({"ts": time.time(),
                         "field": {s: field[s] for s in range(5)},
                         "scores": sc}) + "\n")
fh.close()
json.dump(elo, open("benchmarks/elos.json", "w"), indent=1)
v = elo.get(MINE, {})
print(f"{MINE}: ord {v.get('mu',0)-3*v.get('sigma',8.33):.1f} mu {v.get('mu',0):.1f} g {v.get('games',0)}")
print("ratings saved")
