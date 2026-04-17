"""
SELECTION PRESSURE Simulation
=============================
Pure-numpy boid flocking and black hole predator logic.

No pygame dependency — this module can run headless for batch evaluation
(e.g. genetic algorithm fitness episodes).  All behavioral parameters are
read from injectable BoidParams / PredatorParams dataclass instances,
falling back to defaults that match the config module constants.

Key design for GA integration:
    - Pass custom BoidParams / PredatorParams to constructors
    - Optionally pass per_boid_params dict with numpy arrays for per-entity genomes
    - After N steps, read simulation state (positions, velocities, speeds,
      total_consumed, kill_count) for fitness evaluation
    - Instantiate fresh objects per episode — no global state leaks between runs
"""

import numpy as np
import config as cfg
from config import BoidParams, PredatorParams

# Optional modules — imported lazily so the simulation works headless.
try:
    from nebula import NebulaField
except ImportError:
    NebulaField = None



# ============================================================
# CURL NOISE (flow field)
# ============================================================

def curl_noise(x, y, t, scale, speed):
    """Curl noise for organic flow.

    Returns (N, 2) array of velocity contributions.  Pure math — no side
    effects, no global state.

    Args:
        x, y: boid position arrays (N,)
        t: time (frame number)
        scale: spatial frequency of the noise pattern
        speed: temporal evolution rate
    """
    eps = 1.0
    s = scale
    sp = speed

    def potential(px, py):
        return (
            np.sin(px * s + t * sp * 0.7) *
            np.cos(py * s * 0.8 + t * sp) +
            0.5 * np.sin(px * s * 1.6 + t * sp * 1.3) *
            np.cos(py * s * 2.1 - t * sp * 0.9) +
            0.3 * np.sin(px * s * 3.0 - t * sp * 0.5) *
            np.cos(py * s * 2.7 + t * sp * 1.1)
        )

    dpdy = (potential(x, y + eps) - potential(x, y - eps)) / (2 * eps)
    dpdx = (potential(x + eps, y) - potential(x - eps, y)) / (2 * eps)
    return np.stack([dpdy, -dpdx], axis=1)


# ============================================================
# BOIDS SIMULATION
# ============================================================

class BoidsSimulation:
    """Vectorized boids with toroidal wrapping and injectable parameters.

    Args:
        num_boids: number of boids
        width, height: canvas dimensions (toroidal boundaries)
        seed: random seed for reproducible initialization
        params: BoidParams instance (None = global defaults)
        per_boid_params: dict mapping parameter names to numpy arrays of
            shape (num_boids,) for per-entity genomes.  Overrides scalar
            values from params for the corresponding parameter.

    Observable state for fitness evaluation:
        positions    — (N, 2) float array
        velocities   — (N, 2) float array
        speeds       — (N,) float array
        total_consumed — int, cumulative boids eaten across all predators
        _bh_dist     — (N,) min distance to nearest predator (after step)
    """

    def __init__(self, num_boids, width, height, seed=42,
                 params=None, per_boid_params=None):
        self.params = params or BoidParams()
        self.per_boid_params = per_boid_params or {}
        self.rng = np.random.default_rng(seed)
        rng = self.rng
        self.num = num_boids
        self.width = width
        self.height = height
        self.total_consumed = 0  # cumulative boids eaten (fitness metric)

        self.positions = np.column_stack([
            rng.uniform(0, width, num_boids),
            rng.uniform(0, height, num_boids)
        ])

        angles = rng.uniform(0, 2 * np.pi, num_boids)
        speed = rng.uniform(1.0, self.params.max_speed * 0.6, num_boids)
        self.velocities = np.column_stack([
            np.cos(angles) * speed,
            np.sin(angles) * speed
        ])

        self.phase_offsets = rng.uniform(0, 1, num_boids)
        self.speeds = np.full(num_boids, 2.0)
        self._bh_dist = None  # populated by step() when predators present

        # --- Evolution tracking ---
        self.lineage_ids = rng.integers(0, 1000, size=num_boids).astype(np.int32)
        self._next_lineage_id = 1000  # counter for unique new lineages
        self.birth_frame = np.zeros(num_boids, dtype=np.int64)
        self.birth_flashes = []  # [(x, y, age), ...] cyan ring pulses

        # Initialize per-boid genome arrays with small random perturbation
        if cfg.EVOLUTION_ENABLED and not self.per_boid_params:
            for field_name, default, lo, hi in cfg.GENOME_FIELDS:
                sigma = abs(default) * cfg.MUTATION_SIGMA_FRAC
                vals = default + rng.normal(0, sigma, num_boids)
                self.per_boid_params[field_name] = np.clip(vals, lo, hi)

        # --- Nebula resource fields (ecosystem) ---
        self.nebula = None
        if cfg.NEBULA_FIELDS_ENABLED and NebulaField is not None:
            self.nebula = NebulaField(
                cfg.NUM_NEBULA_CLOUDS, width, height, rng)

        # --- Star energy (metabolism) ---
        self.energy = np.full(num_boids, cfg.STAR_ENERGY_INITIAL)

        # --- Tiered collective behavior state ---
        self.in_defensive = np.zeros(num_boids, dtype=bool)
        self.in_quorum = np.zeros(num_boids, dtype=bool)
        self.quorum_neighbors = np.zeros(num_boids, dtype=np.int32)

        self._last_mean_fitness = 0.0  # cached from last fitness computation
        self.mutation_sigma_mult = 1.0  # decays over time for sigma annealing
        self.selections = 0            # total selection events (for tracking)

    def _p(self, name):
        """Get parameter: per-boid array if set, else scalar from params.

        For scalar params, numpy broadcasting handles (N, N) comparisons
        naturally.  For per-boid arrays of shape (N,), the caller may need
        to reshape to (N, 1) for correct axis broadcasting in pairwise ops.
        """
        if name in self.per_boid_params:
            return self.per_boid_params[name]
        return getattr(self.params, name)

    def add_boids(self, count, frame_num=0):
        """Add new boids at random edge positions without resetting."""
        rng = self.rng
        n = count

        # Spawn at random screen edges (same as respawn logic)
        new_pos = np.empty((n, 2))
        edges = rng.integers(0, 4, n)
        for j in range(n):
            if edges[j] == 0:
                new_pos[j] = [rng.uniform(0, self.width), 0]
            elif edges[j] == 1:
                new_pos[j] = [self.width, rng.uniform(0, self.height)]
            elif edges[j] == 2:
                new_pos[j] = [rng.uniform(0, self.width), self.height]
            else:
                new_pos[j] = [0, rng.uniform(0, self.height)]

        # Velocity toward center
        center = np.array([self.width / 2, self.height / 2])
        directions = center - new_pos
        directions /= np.linalg.norm(directions, axis=1, keepdims=True) + 1e-10
        speed = rng.uniform(1.0, self.params.max_speed * 0.5, n)
        new_vel = directions * speed[:, np.newaxis]

        self.positions = np.vstack([self.positions, new_pos])
        self.velocities = np.vstack([self.velocities, new_vel])
        self.phase_offsets = np.concatenate([
            self.phase_offsets, rng.uniform(0, 1, n)])
        self.speeds = np.concatenate([self.speeds, np.full(n, 2.0)])

        # Energy + collective state for new boids
        self.energy = np.concatenate([
            self.energy, np.full(n, cfg.STAR_ENERGY_INITIAL)])
        self.in_defensive = np.concatenate([
            self.in_defensive, np.zeros(n, dtype=bool)])
        self.in_quorum = np.concatenate([
            self.in_quorum, np.zeros(n, dtype=bool)])
        self.quorum_neighbors = np.concatenate([
            self.quorum_neighbors, np.zeros(n, dtype=np.int32)])

        # Lineage: each new boid gets a unique ID (wrapped to 0-999)
        new_ids = np.arange(
            self._next_lineage_id, self._next_lineage_id + n, dtype=np.int32) % 1000
        self._next_lineage_id += n
        self.lineage_ids = np.concatenate([self.lineage_ids, new_ids])
        self.birth_frame = np.concatenate([
            self.birth_frame, np.full(n, frame_num, dtype=np.int64)])

        # Genome: initialize with small perturbation from defaults
        if cfg.EVOLUTION_ENABLED and self.per_boid_params:
            for field_name, default, lo, hi in cfg.GENOME_FIELDS:
                sigma = abs(default) * cfg.MUTATION_SIGMA_FRAC
                new_vals = default + rng.normal(0, sigma, n)
                self.per_boid_params[field_name] = np.concatenate([
                    self.per_boid_params[field_name],
                    np.clip(new_vals, lo, hi)])

        self.num += n
        self._bh_dist = None  # invalidate stale predator distances

    def remove_boids(self, count):
        """Remove boids (youngest first) without resetting."""
        count = min(count, self.num - 10)  # keep at least 10
        if count <= 0:
            return
        # Remove the youngest boids (highest birth_frame)
        remove_idx = np.argsort(self.birth_frame)[-count:]
        keep_mask = np.ones(self.num, dtype=bool)
        keep_mask[remove_idx] = False

        self.positions = self.positions[keep_mask]
        self.velocities = self.velocities[keep_mask]
        self.phase_offsets = self.phase_offsets[keep_mask]
        self.speeds = self.speeds[keep_mask]
        self.lineage_ids = self.lineage_ids[keep_mask]
        self.birth_frame = self.birth_frame[keep_mask]
        self.energy = self.energy[keep_mask]
        self.in_defensive = self.in_defensive[keep_mask]
        self.in_quorum = self.in_quorum[keep_mask]
        self.quorum_neighbors = self.quorum_neighbors[keep_mask]

        if self.per_boid_params:
            for field_name in self.per_boid_params:
                self.per_boid_params[field_name] = \
                    self.per_boid_params[field_name][keep_mask]

        self.num = self.positions.shape[0]
        self._bh_dist = None  # invalidate stale predator distances

    def step(self, frame_num, predators=None):
        """Advance simulation by one frame.

        Args:
            frame_num: current frame index (used for noise / attractor time)
            predators: list of BlackHolePredator instances, or None
        """
        p = self.params  # shorthand for readability

        # Use float32 for pairwise arrays — halves memory bandwidth
        # (N=500: 1MB vs 2MB per array; N=1000: 4MB vs 8MB)
        pos_f32 = self.positions.astype(np.float32)
        dx = pos_f32[:, np.newaxis, 0] - pos_f32[np.newaxis, :, 0]
        dy = pos_f32[:, np.newaxis, 1] - pos_f32[np.newaxis, :, 1]
        w_f32 = np.float32(self.width)
        h_f32 = np.float32(self.height)
        dx -= w_f32 * np.round(dx / w_f32)
        dy -= h_f32 * np.round(dy / h_f32)
        dist = np.sqrt(dx * dx + dy * dy)

        # Helper: reshape per-boid arrays to (N,1) for row-wise broadcast.
        # Scalars pass through unchanged (numpy broadcasting handles it).
        def _col(name):
            v = self._p(name)
            if isinstance(v, np.ndarray) and v.ndim == 1:
                return v[:, np.newaxis]
            return v

        # Separation — each boid's own separation_radius applies to its row
        sep_mask = (dist < _col('separation_radius')) & (dist > 0)
        sep_w = np.where(sep_mask, 1.0 / (dist ** 2 + 1e-10), 0)
        sep_weight = self._p('separation_weight')
        if isinstance(sep_weight, np.ndarray):
            sep_weight = sep_weight[:, np.newaxis]
        separation = np.stack([
            (sep_w * dx).sum(axis=1),
            (sep_w * dy).sum(axis=1)
        ], axis=1) * sep_weight

        # Alignment
        align_mask = (dist < _col('alignment_radius')) & (dist > 0)
        align_count = align_mask.sum(axis=1, keepdims=True).clip(1)
        avg_vel = np.stack([
            (align_mask * self.velocities[:, 0][np.newaxis, :]).sum(axis=1),
            (align_mask * self.velocities[:, 1][np.newaxis, :]).sum(axis=1)
        ], axis=1) / align_count
        align_weight = self._p('alignment_weight')
        if isinstance(align_weight, np.ndarray):
            align_weight = align_weight[:, np.newaxis]
        alignment = (avg_vel - self.velocities) * align_weight

        # Cohesion
        coh_mask = (dist < _col('cohesion_radius')) & (dist > 0)
        coh_count = coh_mask.sum(axis=1, keepdims=True).clip(1)
        coh_weight = self._p('cohesion_weight')
        if isinstance(coh_weight, np.ndarray):
            coh_weight = coh_weight[:, np.newaxis]
        cohesion = np.stack([
            -(np.where(coh_mask, dx, 0)).sum(axis=1),
            -(np.where(coh_mask, dy, 0)).sum(axis=1)
        ], axis=1) / coh_count * coh_weight

        accel = separation + alignment + cohesion

        # Curl noise
        flow = None
        if p.noise_influence > 0:
            flow = curl_noise(
                self.positions[:, 0], self.positions[:, 1], frame_num,
                p.noise_scale, p.noise_speed)
            accel += flow * p.noise_influence

        # Attractor
        if p.attractor_enabled:
            total_f = p.target_fps * 30
            att_speed = 2 * np.pi * p.attractor_orbits / total_f
            t = frame_num * att_speed
            ax = self.width / 2 + p.attractor_orbit_radius * np.cos(t)
            ay = self.height / 2 + p.attractor_orbit_radius * np.sin(t * 0.7)

            adx = ax - self.positions[:, 0]
            ady = ay - self.positions[:, 1]
            adx -= self.width * np.round(adx / self.width)
            ady -= self.height * np.round(ady / self.height)
            adist = np.sqrt(adx ** 2 + ady ** 2).clip(1e-10)
            pull = p.attractor_strength * np.tanh(adist / 200)
            accel[:, 0] += adx / adist * pull
            accel[:, 1] += ady / adist * pull

        # --- Chemotaxis: steer toward nebula resource clouds ---
        if (cfg.CHEMOTAXIS_ENABLED and cfg.NEBULA_FIELDS_ENABLED
                and self.nebula is not None):
            gradient_dir = self.nebula.get_nearest_cloud_direction(
                self.positions)
            chem_str = self._p('chemotaxis_strength')
            # Hungry stars steer harder (desperation foraging)
            if cfg.STAR_ENERGY_ENABLED:
                hunger = np.clip(
                    1.0 - self.energy / cfg.STAR_ENERGY_LOW_THRESHOLD, 0, 1)
                if isinstance(chem_str, np.ndarray):
                    effective = chem_str * (1.0 + hunger * cfg.CHEMOTAXIS_HUNGER_MULT)
                else:
                    effective = chem_str * (1.0 + hunger * cfg.CHEMOTAXIS_HUNGER_MULT)
            else:
                effective = chem_str
            if isinstance(effective, np.ndarray):
                accel += gradient_dir * effective[:, np.newaxis]
            else:
                accel += gradient_dir * effective

        # --- Tiered collective behavior (local density sensing) ---
        # Uses same neighbor counting for both tiers.
        # Tier 1 — Defensive swirl: DEFENSIVE_LOCAL_THRESHOLD <= neighbors < quorum
        # Tier 2 — Quorum fortress: neighbors >= quorum_threshold
        if cfg.QUORUM_ENABLED:
            quorum_mask = (dist < cfg.QUORUM_SIGNAL_RADIUS) & (dist > 0)
            self.quorum_neighbors = quorum_mask.sum(axis=1).astype(np.int32)

            # Hungry boids break from fortress (but not from defensive)
            if cfg.STAR_ENERGY_ENABLED:
                too_hungry = self.energy < cfg.QUORUM_BREAK_ENERGY
            else:
                too_hungry = np.zeros(self.num, dtype=bool)

            # Per-boid quorum threshold (evolvable) for tier 2
            q_thresh = self._p('quorum_threshold')
            above_quorum = self.quorum_neighbors >= q_thresh
            above_defensive = self.quorum_neighbors >= cfg.DEFENSIVE_LOCAL_THRESHOLD

            # Tier 2: quorum fortress (hungry boids break out)
            self.in_quorum = above_quorum & ~too_hungry
            # Tier 1: defensive swirl (between defensive threshold and quorum)
            self.in_defensive = above_defensive & ~self.in_quorum

            # Fortress effects: extra cohesion toward local center of mass
            if np.any(self.in_quorum):
                q_idx = np.where(self.in_quorum)[0]
                for idx in q_idx:
                    neighbors = quorum_mask[idx]
                    if neighbors.sum() > 0:
                        n_dx = -dx[idx][neighbors].mean()
                        n_dy = -dy[idx][neighbors].mean()
                        accel[idx, 0] += n_dx * cfg.QUORUM_FORTRESS_COHESION
                        accel[idx, 1] += n_dy * cfg.QUORUM_FORTRESS_COHESION

            # Defensive effects: extra cohesion toward local center of mass
            if np.any(self.in_defensive):
                d_idx = np.where(self.in_defensive)[0]
                for idx in d_idx:
                    neighbors = quorum_mask[idx]
                    if neighbors.sum() > 0:
                        n_dx = -dx[idx][neighbors].mean()
                        n_dy = -dy[idx][neighbors].mean()
                        accel[idx, 0] += n_dx * cfg.DEFENSIVE_COHESION_EXTRA
                        accel[idx, 1] += n_dy * cfg.DEFENSIVE_COHESION_EXTRA

        # Compute predator distances (flee applied AFTER flock clamp)
        has_predators = predators is not None and len(predators) > 0
        # Track minimum distance to ANY predator (for fear color + speed boost)
        min_bh_dist = np.full(self.num, np.inf)

        # Limit flock forces (per-boid max_force when evolving)
        max_force_arr = self._p('max_force')
        force_mag = np.sqrt(accel[:, 0] ** 2 + accel[:, 1] ** 2)
        over_limit = force_mag > max_force_arr
        if np.any(over_limit):
            scale = np.where(over_limit, max_force_arr / force_mag.clip(1e-10), 1.0)
            accel *= scale[:, np.newaxis]

        # Black hole flee — applied AFTER flock clamp so it overrides formation
        if has_predators:
            for pred in predators:
                pp = pred.params  # predator's behavioral params
                bh_dx = self.positions[:, 0] - pred.position[0]
                bh_dy = self.positions[:, 1] - pred.position[1]
                bh_dx -= self.width * np.round(bh_dx / self.width)
                bh_dy -= self.height * np.round(bh_dy / self.height)
                bh_dist = np.sqrt(bh_dx ** 2 + bh_dy ** 2).clip(1e-10)
                bh_ux = bh_dx / bh_dist
                bh_uy = bh_dy / bh_dist

                min_bh_dist = np.minimum(min_bh_dist, bh_dist)

                # Mass-scaled radii (bigger black hole = wider influence)
                mass_r = pred._mass_scale(cfg.BH_MASS_RADIUS_EXPONENT)
                eff_flee_r = pp.flee_radius * mass_r
                eff_panic_r = pp.panic_radius * mass_r
                eff_consume_r = pp.consume_radius * mass_r

                # Outer flee
                flee_mask = bh_dist < eff_flee_r
                flee_t = np.where(flee_mask,
                                  1.0 - bh_dist / eff_flee_r, 0)
                flee_str = flee_t * pp.flee_weight * p.max_force
                accel[:, 0] += bh_ux * flee_str
                accel[:, 1] += bh_uy * flee_str

                # Inner panic
                panic_mask = bh_dist < eff_panic_r
                panic_t = np.where(panic_mask,
                                   1.0 - bh_dist / eff_panic_r, 0)
                panic_str = panic_t * pp.panic_weight * p.max_force
                accel[:, 0] += bh_ux * panic_str
                accel[:, 1] += bh_uy * panic_str

                # Consume (mass-scaled radius)
                consumed = bh_dist < eff_consume_r
                if np.any(consumed):
                    consume_idx = np.where(consumed)[0]
                    for idx in consume_idx:
                        pred.flashes.append([
                            self.positions[idx, 0], self.positions[idx, 1],
                            255, 200, 100, 0
                        ])
                        # Spawn accretion particle that spirals into the void
                        if pp.accretion_enabled:
                            bdx = self.positions[idx, 0] - pred.position[0]
                            bdy = self.positions[idx, 1] - pred.position[1]
                            a = float(np.arctan2(bdy, bdx))
                            r = max(float(np.sqrt(bdx**2 + bdy**2)),
                                    pp.consume_radius * 2.0)
                            pred.accretion.append([
                                a, r, r, 255, 180, 60, 0
                            ])
                    n_eaten = int(consumed.sum())
                    self.total_consumed += n_eaten
                    pred.kill_count += n_eaten
                    pred.total_kills += n_eaten
                    pred.frames_since_last_kill = 0
                    # Mass gain from feeding
                    if cfg.ACCRETION_HUNGER_ENABLED:
                        pred.mass = min(cfg.BH_MASS_MAX,
                                        pred.mass + n_eaten * cfg.BH_MASS_GAIN_PER_KILL)

                    # --- Evolution: select parent, mutate, write genome ---
                    if cfg.EVOLUTION_ENABLED and self.per_boid_params:
                        living_mask = ~consumed
                        self._evolve_dead_boids(
                            consume_idx, living_mask, frame_num, dist)

                    edges = self.rng.integers(0, 4, n_eaten)
                    for j, idx in enumerate(consume_idx):
                        if edges[j] == 0:
                            self.positions[idx] = [
                                self.rng.uniform(0, self.width), 0]
                        elif edges[j] == 1:
                            self.positions[idx] = [
                                self.width, self.rng.uniform(0, self.height)]
                        elif edges[j] == 2:
                            self.positions[idx] = [
                                self.rng.uniform(0, self.width), self.height]
                        else:
                            self.positions[idx] = [
                                0, self.rng.uniform(0, self.height)]
                        # Reset energy on respawn
                        self.energy[idx] = cfg.STAR_ENERGY_INITIAL
                        self.in_defensive[idx] = False
                        self.in_quorum[idx] = False
                        # Record birth flash at spawn point
                        self.birth_flashes.append([
                            self.positions[idx, 0],
                            self.positions[idx, 1], 0])
                        self.birth_frame[idx] = frame_num
                        center = np.array([self.width / 2, self.height / 2])
                        direction = center - self.positions[idx]
                        direction /= np.linalg.norm(direction) + 1e-10
                        ms = self._p('max_speed')
                        boid_ms = ms[idx] if isinstance(ms, np.ndarray) else ms
                        self.velocities[idx] = direction * boid_ms * 0.5

        self._bh_dist = min_bh_dist if has_predators else None

        # Update velocity
        self.velocities += accel
        self.speeds = np.sqrt(
            self.velocities[:, 0] ** 2 + self.velocities[:, 1] ** 2)

        # Fleeing boids get a speed boost, others capped at per-boid max_speed
        max_speed_arr = self._p('max_speed')
        if has_predators:
            flee_r = predators[0].params.flee_radius
            flee_boost = np.where(min_bh_dist < flee_r, 1.15, 1.0)
        else:
            flee_boost = np.ones(self.num)
        effective_max = max_speed_arr * flee_boost
        over_speed = self.speeds > effective_max
        if np.any(over_speed):
            scale = np.where(
                over_speed, effective_max / self.speeds.clip(1e-10), 1.0)
            self.velocities *= scale[:, np.newaxis]
            self.speeds = np.minimum(self.speeds, effective_max)

        # Enforce per-boid minimum speed — no stationary boids (vectorized)
        min_speed_arr = self._p('min_speed')
        min_speed_scalar = (min_speed_arr.min() if isinstance(
            min_speed_arr, np.ndarray) else min_speed_arr)
        if min_speed_scalar > 0:
            under_speed = self.speeds < min_speed_arr
            if np.any(under_speed):
                under_idx = np.where(under_speed)[0]
                if isinstance(min_speed_arr, np.ndarray):
                    ms_vals = min_speed_arr[under_idx]
                else:
                    ms_vals = np.full(len(under_idx), min_speed_arr)
                near_zero = self.speeds[under_idx] < 1e-6
                if np.any(near_zero):
                    nz_idx = under_idx[near_zero]
                    angles = self.rng.uniform(0, 2 * np.pi, len(nz_idx))
                    nz_ms = ms_vals[near_zero]
                    self.velocities[nz_idx, 0] = np.cos(angles) * nz_ms
                    self.velocities[nz_idx, 1] = np.sin(angles) * nz_ms
                    self.speeds[nz_idx] = nz_ms
                has_speed = ~near_zero
                if np.any(has_speed):
                    hs_idx = under_idx[has_speed]
                    hs_ms = ms_vals[has_speed]
                    scale = hs_ms / self.speeds[hs_idx]
                    self.velocities[hs_idx] *= scale[:, np.newaxis]
                    self.speeds[hs_idx] = hs_ms

        # Age birth flashes
        self.birth_flashes = [
            [f[0], f[1], f[2] + 1] for f in self.birth_flashes if f[2] < 15]

        # --- Defensive swirl: tangential velocity around predators ---
        if has_predators and np.any(self.in_defensive):
            for pred in predators:
                pdx = self.positions[:, 0] - pred.position[0]
                pdy = self.positions[:, 1] - pred.position[1]
                pdx -= self.width * np.round(pdx / self.width)
                pdy -= self.height * np.round(pdy / self.height)
                pdist = np.sqrt(pdx**2 + pdy**2).clip(1e-10)
                # Only defensive boids within tangent radius
                in_range = self.in_defensive & (pdist < cfg.DEFENSIVE_TANGENT_RADIUS)
                if np.any(in_range):
                    # Tangential: 90 degree rotation of radial unit vector
                    tan_ux = -pdy / pdist
                    tan_uy = pdx / pdist
                    # Strength falls off with distance
                    strength = ((1.0 - pdist / cfg.DEFENSIVE_TANGENT_RADIUS)
                                * cfg.DEFENSIVE_TANGENT_STRENGTH)
                    strength = np.where(in_range, strength, 0.0)
                    self.velocities[:, 0] += tan_ux * strength
                    self.velocities[:, 1] += tan_uy * strength

        # --- Quorum fortress speed reduction ---
        if cfg.QUORUM_ENABLED and np.any(self.in_quorum):
            q_scale = np.where(self.in_quorum,
                               cfg.QUORUM_FORTRESS_SPEED_MULT, 1.0)
            self.velocities *= q_scale[:, np.newaxis]
            self.speeds *= q_scale

        # Re-clamp speeds after defensive/quorum modifications
        if np.any(self.in_defensive) or np.any(self.in_quorum):
            max_spd = self._p('max_speed')
            self.speeds = np.sqrt(
                self.velocities[:, 0]**2 + self.velocities[:, 1]**2)
            over = self.speeds > max_spd
            if np.any(over):
                scale = np.where(over, max_spd / self.speeds.clip(1e-10), 1.0)
                self.velocities *= scale[:, np.newaxis]
            self.speeds = np.minimum(self.speeds, max_spd)

        # Update position
        self.positions += self.velocities
        self.positions[:, 0] %= self.width
        self.positions[:, 1] %= self.height

        # --- Star energy metabolism ---
        if cfg.STAR_ENERGY_ENABLED:
            # Passive energy drain (halved when in fortress quorum)
            drain = cfg.STAR_ENERGY_DRAIN_RATE
            if cfg.QUORUM_ENABLED:
                drain_arr = np.where(self.in_quorum,
                                     drain * cfg.QUORUM_ENERGY_DRAIN_MULT,
                                     drain)
            else:
                drain_arr = drain
            self.energy -= drain_arr

            # Feeding: stars within range of nebula clouds gain energy
            if self.nebula is not None:
                density = self.nebula.get_density_at(self.positions)
                feeding = density > 0.05
                self.energy[feeding] += (cfg.STAR_ENERGY_FEED_RATE
                                         * density[feeding])

            self.energy = np.clip(self.energy, 0, cfg.STAR_ENERGY_MAX)

        # --- Nebula cloud step (deplete, regenerate, drift) ---
        if self.nebula is not None:
            self.nebula.step(self.positions)

        # Periodic culling: replace bottom N% with offspring of top performers
        if (cfg.EVOLUTION_ENABLED and cfg.CULL_INTERVAL_FRAMES > 0
                and self.per_boid_params
                and frame_num > 0
                and frame_num % cfg.CULL_INTERVAL_FRAMES == 0):
            self._periodic_cull(frame_num, dist)

        # Periodic spawning: steady population growth toward target
        if (cfg.PERIODIC_SPAWN_ENABLED
                and self.num < cfg.POPULATION_TARGET
                and frame_num > 0
                and frame_num % cfg.PERIODIC_SPAWN_INTERVAL == 0):
            spawn_n = min(cfg.PERIODIC_SPAWN_COUNT,
                          cfg.POPULATION_TARGET - self.num)
            if spawn_n > 0:
                old_num = self.num
                self.add_boids(spawn_n, frame_num)
                # Evolve the newly added boids from fit parents
                if cfg.EVOLUTION_ENABLED and self.per_boid_params:
                    # Recompute distance matrix with new population size
                    ps = self.positions.astype(np.float32)
                    sdx = ps[:, np.newaxis, 0] - ps[np.newaxis, :, 0]
                    sdy = ps[:, np.newaxis, 1] - ps[np.newaxis, :, 1]
                    sdx -= np.float32(self.width) * np.round(
                        sdx / np.float32(self.width))
                    sdy -= np.float32(self.height) * np.round(
                        sdy / np.float32(self.height))
                    spawn_dist = np.sqrt(sdx * sdx + sdy * sdy)
                    all_alive = np.ones(self.num, dtype=bool)
                    fitness = self._compute_fitness(
                        all_alive, frame_num, spawn_dist)
                    for i in range(old_num, self.num):
                        parent_a = self._select_parent(fitness, [])
                        parent_b = self._select_parent(fitness, [])
                        if parent_a is None:
                            continue
                        if parent_b is None or parent_b == parent_a:
                            parent_b = parent_a
                        eff_sigma = (cfg.MUTATION_SIGMA_FRAC
                                     * self.mutation_sigma_mult)
                        for fn, default, lo, hi in cfg.GENOME_FIELDS:
                            arr = self.per_boid_params[fn]
                            base = (arr[parent_a]
                                    if self.rng.random() < 0.5
                                    else arr[parent_b])
                            sigma = abs(default) * eff_sigma
                            arr[i] = np.clip(
                                base + self.rng.normal(0, sigma), lo, hi)
                        if fitness[parent_a] >= fitness[parent_b]:
                            self.lineage_ids[i] = self.lineage_ids[parent_a]
                        else:
                            self.lineage_ids[i] = self.lineage_ids[parent_b]

    # ----------------------------------------------------------
    # Evolution helpers
    # ----------------------------------------------------------

    def _compute_fitness(self, living_mask, frame_num, dist_matrix):
        """Score all living boids.  Returns (N,) array (dead boids get -inf)."""
        fitness = np.full(self.num, -np.inf)
        live = np.where(living_mask)[0]
        if len(live) == 0:
            return fitness

        # 1. Survival duration (frames since last respawn)
        survival = (frame_num - self.birth_frame[live]).astype(np.float64)
        # Normalize: log scale so early survival matters more than endurance
        survival_score = np.log1p(survival)
        survival_score /= survival_score.max() + 1e-10

        # 2. Neighbor count (within each boid's cohesion radius)
        coh_r = self._p('cohesion_radius')
        if isinstance(coh_r, np.ndarray):
            coh_r_live = coh_r[live, np.newaxis]
        else:
            coh_r_live = coh_r
        # dist_matrix rows for living boids, all columns
        live_dist = dist_matrix[live]
        neighbor_count = ((live_dist < coh_r_live) & (live_dist > 0)).sum(axis=1)
        neighbor_score = neighbor_count.astype(np.float64)
        neighbor_score /= neighbor_score.max() + 1e-10

        # 3. Speed as fraction of per-boid max_speed
        ms = self._p('max_speed')
        if isinstance(ms, np.ndarray):
            speed_frac = self.speeds[live] / (ms[live] + 1e-10)
        else:
            speed_frac = self.speeds[live] / (ms + 1e-10)
        speed_score = np.clip(speed_frac, 0, 1.5)
        speed_score /= speed_score.max() + 1e-10

        # 4. Predator distance — reward boids in the optimal band
        if self._bh_dist is not None:
            pd = self._bh_dist[live]
            opt_min = cfg.FITNESS_PREDATOR_OPTIMAL_MIN
            opt_max = cfg.FITNESS_PREDATOR_OPTIMAL_MAX
            # 1.0 inside band, falls off linearly outside
            pred_score = np.where(
                pd < opt_min, pd / (opt_min + 1e-10),
                np.where(pd > opt_max,
                         np.clip(1.0 - (pd - opt_max) / opt_max, 0, 1),
                         1.0))
        else:
            pred_score = np.ones(len(live))

        # 5. Energy level — reward well-fed boids (successful foragers)
        if cfg.STAR_ENERGY_ENABLED:
            energy_score = self.energy[live].copy()
            emax = energy_score.max() + 1e-10
            energy_score /= emax
        else:
            energy_score = np.ones(len(live))

        # 6. Cohesion reward — counter-pressure against separation drift
        # Boids with neighbors get a bonus; isolated boids get a penalty
        has_neighbors = neighbor_count > 0
        cohesion_score = np.where(has_neighbors,
                                  neighbor_count.astype(np.float64),
                                  0.0)
        cohesion_score /= cohesion_score.max() + 1e-10
        isolation_penalty = np.where(has_neighbors, 0.0,
                                     cfg.FITNESS_ISOLATION_PENALTY)

        # Weighted sum
        w = cfg
        total = (w.FITNESS_WEIGHT_SURVIVAL * survival_score
                 + w.FITNESS_WEIGHT_NEIGHBORS * neighbor_score
                 + w.FITNESS_WEIGHT_SPEED * speed_score
                 + w.FITNESS_WEIGHT_PREDATOR_DIST * pred_score
                 + w.FITNESS_WEIGHT_ENERGY * energy_score
                 + w.FITNESS_WEIGHT_COHESION * cohesion_score
                 - isolation_penalty)
        fitness[live] = total
        self._last_mean_fitness = float(total.mean()) if len(live) > 0 else 0.0
        return fitness

    def _select_parent(self, fitness, dead_indices):
        """Tournament selection among living boids (fitness > -inf)."""
        alive_idx = np.where(fitness > -np.inf)[0]
        if len(alive_idx) == 0:
            return None
        k = min(cfg.TOURNAMENT_SIZE, len(alive_idx))
        candidates = self.rng.choice(alive_idx, size=k, replace=False)
        best = candidates[np.argmax(fitness[candidates])]
        return best

    def _evolve_dead_boids(self, dead_indices, living_mask,
                           frame_num, dist_matrix):
        """For each dead boid, pick two parents, crossover + mutate genome."""
        fitness = self._compute_fitness(
            living_mask, frame_num, dist_matrix)

        for idx in dead_indices:
            parent_a = self._select_parent(fitness, dead_indices)
            if parent_a is None:
                continue
            parent_b = self._select_parent(fitness, dead_indices)
            if parent_b is None or parent_b == parent_a:
                parent_b = self._select_parent(fitness, dead_indices)
            if parent_b is None:
                parent_b = parent_a  # fallback to cloning

            # Uniform crossover + Gaussian mutation
            effective_sigma = cfg.MUTATION_SIGMA_FRAC * self.mutation_sigma_mult
            for field_name, default, lo, hi in cfg.GENOME_FIELDS:
                arr = self.per_boid_params[field_name]
                # 50/50 chance of taking from parent A or B
                base_val = (arr[parent_a] if self.rng.random() < 0.5
                            else arr[parent_b])
                sigma = abs(default) * effective_sigma
                child_val = base_val + self.rng.normal(0, sigma)
                arr[idx] = np.clip(child_val, lo, hi)

            # Lineage follows dominant (higher fitness) parent
            if fitness[parent_a] >= fitness[parent_b]:
                self.lineage_ids[idx] = self.lineage_ids[parent_a]
            else:
                self.lineage_ids[idx] = self.lineage_ids[parent_b]

            # Decay mutation sigma
            self.selections += 1
            min_mult = cfg.MUTATION_SIGMA_MIN_FRAC / cfg.MUTATION_SIGMA_FRAC
            self.mutation_sigma_mult = max(
                min_mult,
                self.mutation_sigma_mult * cfg.MUTATION_SIGMA_DECAY)

    def _periodic_cull(self, frame_num, dist_matrix):
        """Replace bottom CULL_BOTTOM_FRACTION of boids with mutated top offspring.

        Genome-only replacement — positions and velocities stay unchanged.
        No birth flashes, no respawn. The boid just gets new behavioral genes.
        """
        n_cull = max(1, int(self.num * cfg.CULL_BOTTOM_FRACTION))
        if n_cull < 1 or self.num < 20:
            return

        # Score everyone (all alive for periodic cull)
        all_alive = np.ones(self.num, dtype=bool)
        fitness = self._compute_fitness(all_alive, frame_num, dist_matrix)

        # Bottom N by fitness
        sorted_idx = np.argsort(fitness)
        cull_idx = sorted_idx[:n_cull]
        # Top half as parent pool
        top_half = sorted_idx[self.num // 2:]

        for idx in cull_idx:
            # Tournament select two parents from top half
            k = min(cfg.TOURNAMENT_SIZE, len(top_half))
            cands_a = self.rng.choice(top_half, size=k, replace=False)
            parent_a = cands_a[np.argmax(fitness[cands_a])]
            cands_b = self.rng.choice(top_half, size=k, replace=False)
            parent_b = cands_b[np.argmax(fitness[cands_b])]

            # Uniform crossover + mutate genome
            effective_sigma = cfg.MUTATION_SIGMA_FRAC * self.mutation_sigma_mult
            for field_name, default, lo, hi in cfg.GENOME_FIELDS:
                arr = self.per_boid_params[field_name]
                base_val = (arr[parent_a] if self.rng.random() < 0.5
                            else arr[parent_b])
                sigma = abs(default) * effective_sigma
                child_val = base_val + self.rng.normal(0, sigma)
                arr[idx] = np.clip(child_val, lo, hi)

            # Lineage from dominant parent + reset birth frame
            if fitness[parent_a] >= fitness[parent_b]:
                self.lineage_ids[idx] = self.lineage_ids[parent_a]
            else:
                self.lineage_ids[idx] = self.lineage_ids[parent_b]
            self.birth_frame[idx] = frame_num

    # ----------------------------------------------------------
    # Predator starvation — explosion boid spawn + predator GA
    # ----------------------------------------------------------

    def _add_explosion_boids(self, count, center_x, center_y, frame_num):
        """Spawn boids radiating outward from an explosion center.

        Unlike add_boids (edge spawn, toward center), these burst outward
        from a point — visually matching the predator death explosion.
        """
        rng = self.rng
        n = count

        # All boids start at the explosion center
        new_pos = np.full((n, 2), [center_x, center_y], dtype=np.float64)

        # Velocities: random directions radiating outward, varied speeds
        angles = rng.uniform(0, 2 * np.pi, n)
        speed = rng.uniform(self.params.max_speed * 0.4,
                            self.params.max_speed * 1.0, n)
        new_vel = np.column_stack([np.cos(angles) * speed,
                                   np.sin(angles) * speed])

        self.positions = np.vstack([self.positions, new_pos])
        self.velocities = np.vstack([self.velocities, new_vel])
        self.phase_offsets = np.concatenate([
            self.phase_offsets, rng.uniform(0, 1, n)])
        self.speeds = np.concatenate([self.speeds, speed])

        # Energy + collective state for explosion boids
        self.energy = np.concatenate([
            self.energy, np.full(n, cfg.STAR_ENERGY_INITIAL)])
        self.in_defensive = np.concatenate([
            self.in_defensive, np.zeros(n, dtype=bool)])
        self.in_quorum = np.concatenate([
            self.in_quorum, np.zeros(n, dtype=bool)])
        self.quorum_neighbors = np.concatenate([
            self.quorum_neighbors, np.zeros(n, dtype=np.int32)])

        # Lineage: each new explosion boid gets a unique ID (wrapped to 0-999)
        new_ids = np.arange(
            self._next_lineage_id, self._next_lineage_id + n, dtype=np.int32) % 1000
        self._next_lineage_id += n
        self.lineage_ids = np.concatenate([self.lineage_ids, new_ids])
        self.birth_frame = np.concatenate([
            self.birth_frame, np.full(n, frame_num, dtype=np.int64)])

        # Genome: initialize with small perturbation from defaults
        if cfg.EVOLUTION_ENABLED and self.per_boid_params:
            for field_name, default, lo, hi in cfg.GENOME_FIELDS:
                sigma = abs(default) * cfg.MUTATION_SIGMA_FRAC
                new_vals = default + rng.normal(0, sigma, n)
                self.per_boid_params[field_name] = np.concatenate([
                    self.per_boid_params[field_name],
                    np.clip(new_vals, lo, hi)])

        self.num += n
        self._bh_dist = None

    def check_predator_starvation(self, predators, frame_num):
        """Check all predators for starvation, handle death + respawn.

        Returns list of explosion events: [[x, y, 0], ...] for rendering.
        Each starved predator:
          1. Spawns PREDATOR_EXPLOSION_BOIDS radiating from its position
          2. Respawns at a random screen edge with evolved parameters
          3. Resets all predators' kill_counts (evaluation window resets)
        """
        if not cfg.PREDATOR_EVOLUTION_ENABLED:
            return []

        explosions = []
        rng = self.rng

        for i, pred in enumerate(predators):
            if not pred.starved:
                continue

            ex, ey = float(pred.position[0]), float(pred.position[1])
            explosions.append([ex, ey, 0])

            # 1. Spawn explosion boids (scaled by carrying capacity)
            spawn_count = cfg.PREDATOR_EXPLOSION_BOIDS
            if cfg.POPULATION_TARGET > 0 and spawn_count > 0:
                ratio = self.num / cfg.POPULATION_TARGET
                if ratio >= 2.0:
                    spawn_count = 0
                elif ratio > 1.0:
                    spawn_count = int(spawn_count * (2.0 - ratio))
            if spawn_count > 0:
                self._add_explosion_boids(spawn_count, ex, ey, frame_num)

            # 2. Evolve predator params
            others = [p for j, p in enumerate(predators) if j != i]
            if others:
                # Clone from best surviving predator (highest kill_count)
                best = max(others, key=lambda p: p.kill_count)
                new_params = _mutate_predator_params(best.params, rng)
            else:
                # Only predator — mutate from defaults
                new_params = _mutate_predator_params(PredatorParams(), rng)
            pred.params = new_params

            # 3. Respawn at random screen edge
            edge = rng.integers(0, 4)
            if edge == 0:
                pred.position = np.array(
                    [rng.uniform(0, self.width), 0.0], dtype=np.float64)
            elif edge == 1:
                pred.position = np.array(
                    [float(self.width), rng.uniform(0, self.height)],
                    dtype=np.float64)
            elif edge == 2:
                pred.position = np.array(
                    [rng.uniform(0, self.width), float(self.height)],
                    dtype=np.float64)
            else:
                pred.position = np.array(
                    [0.0, rng.uniform(0, self.height)], dtype=np.float64)

            # Reset velocity toward center
            center = np.array([self.width / 2, self.height / 2])
            direction = center - pred.position
            direction /= np.linalg.norm(direction) + 1e-10
            pred.velocity = direction * pred.params.speed * 0.5

            # Reset predator state
            pred.starved = False
            pred.frames_since_last_kill = 0
            pred.generation += 1
            pred.mass = cfg.BH_MASS_INITIAL  # reset mass on respawn
            pred.lunge_timer = 0
            pred.cooldown_timer = 0
            pred.lunging = False

            print(f"  [BLACK HOLE STARVED] #{i} exploded at ({ex:.0f}, {ey:.0f})"
                  f" -> respawned with mutated params"
                  f" | +{spawn_count} stars"
                  f" | pop={self.num}")

        # Reset all predators' kill_counts after any starvation event
        if explosions:
            for pred in predators:
                pred.kill_count = 0

        return explosions


def _mutate_predator_params(source_params, rng):
    """Create a new PredatorParams with Gaussian-mutated genome fields.

    Non-genome fields (flee_radius, panic_weight, etc.) are copied unchanged.
    """
    from dataclasses import asdict
    kwargs = asdict(source_params)

    for field_name, default, lo, hi in cfg.PREDATOR_GENOME_FIELDS:
        val = getattr(source_params, field_name)
        sigma = abs(default) * cfg.PREDATOR_MUTATION_SIGMA
        mutated = val + rng.normal(0, sigma)
        # lunge_duration and lunge_cooldown are ints
        if isinstance(default, int):
            mutated = int(round(mutated))
        kwargs[field_name] = max(lo, min(hi, mutated))

    return PredatorParams(**kwargs)


# ============================================================
# BLACK HOLE PREDATOR
# ============================================================

class BlackHolePredator:
    """Autonomous predator that chases dense boid clusters with lunge bursts.

    Args:
        width, height: canvas dimensions (toroidal boundaries)
        start_pos: (x, y) initial position, or None for default
        seed: random seed
        params: PredatorParams instance (None = global defaults)

    Observable state for fitness evaluation:
        position   — (2,) float array
        velocity   — (2,) float array
        kill_count — int, cumulative boids consumed
        lunging    — bool, whether currently in a lunge burst
    """

    def __init__(self, width, height, start_pos=None, seed=123, params=None):
        self.params = params or PredatorParams()
        rng = np.random.default_rng(seed)
        self.width = width
        self.height = height
        if start_pos is not None:
            self.position = np.array(start_pos, dtype=np.float64)
        else:
            self.position = np.array(
                [width * 0.25, height * 0.25], dtype=np.float64)
        self.velocity = rng.uniform(-0.5, 0.5, 2)
        self.flashes = []
        self.accretion = []      # spiraling particles from consumed boids
        self.lunge_timer = 0     # >0 means currently lunging
        self.cooldown_timer = 0  # >0 means lunge on cooldown
        self.lunging = False
        self.kill_count = 0      # boids consumed this evaluation window
        self.total_kills = 0     # lifetime boids consumed (never reset)
        self.generation = 0      # how many times this predator has respawned
        self.frames_since_last_kill = 0  # starvation counter (reset on kill)
        self.starved = False     # set True when starvation threshold reached

        # Accretion hunger: mass that grows/shrinks with feeding
        self.mass = cfg.BH_MASS_INITIAL

    def _mass_scale(self, exponent):
        """Return mass^exponent if accretion hunger is enabled, else 1.0."""
        if cfg.ACCRETION_HUNGER_ENABLED:
            return self.mass ** exponent
        return 1.0

    def step(self, boid_positions, other_predators=None, sim=None):
        """Move toward nearest dense cluster, with lunge bursts."""
        pp = self.params

        dx = boid_positions[:, 0] - self.position[0]
        dy = boid_positions[:, 1] - self.position[1]
        dx -= self.width * np.round(dx / self.width)
        dy -= self.height * np.round(dy / self.height)
        dist = np.sqrt(dx ** 2 + dy ** 2).clip(1e-10)

        # Target: weighted centroid of visible boids
        visible = dist < pp.sight_radius
        if np.any(visible):
            weights = np.where(visible, 1.0 / dist, 0)
            total_w = weights.sum()
            target_dx = (weights * dx).sum() / total_w
            target_dy = (weights * dy).sum() / total_w
        else:
            target_dx = self.width / 2 - self.position[0]
            target_dy = self.height / 2 - self.position[1]

        # Check lunge trigger: cluster within lunge radius, not on cooldown
        closest_dist = dist.min()
        if (self.lunge_timer <= 0 and self.cooldown_timer <= 0
                and closest_dist < pp.lunge_radius):
            nearby = (dist < pp.lunge_radius).sum()
            if nearby >= 5:
                self.lunge_timer = pp.lunge_duration
                self.lunging = True

        # Tick timers
        if self.lunge_timer > 0:
            self.lunge_timer -= 1
            if self.lunge_timer <= 0:
                self.lunging = False
                self.cooldown_timer = pp.lunge_cooldown
        elif self.cooldown_timer > 0:
            self.cooldown_timer -= 1

        # Current speed limit (mass-scaled: heavier = slower)
        base_speed = pp.lunge_speed if self.lunging else pp.speed
        current_speed = base_speed * self._mass_scale(cfg.BH_MASS_SPEED_EXPONENT)
        if self.lunging:
            current_speed *= self._mass_scale(cfg.BH_MASS_LUNGE_SPEED_EXPONENT)
        current_force = (pp.max_force * (1.8 if self.lunging else 1.0)
                         * self._mass_scale(cfg.BH_MASS_FORCE_EXPONENT))

        # Chase steering
        target_dist = np.sqrt(target_dx ** 2 + target_dy ** 2) + 1e-10
        desired_vx = target_dx / target_dist * current_speed
        desired_vy = target_dy / target_dist * current_speed
        steer_x = desired_vx - self.velocity[0]
        steer_y = desired_vy - self.velocity[1]

        steer_mag = np.sqrt(steer_x ** 2 + steer_y ** 2)
        if steer_mag > current_force:
            steer_x = steer_x / steer_mag * current_force
            steer_y = steer_y / steer_mag * current_force

        self.velocity[0] += steer_x
        self.velocity[1] += steer_y

        # Predator-predator separation: repel from other predators
        if other_predators:
            for other in other_predators:
                sep_dx = self.position[0] - other.position[0]
                sep_dy = self.position[1] - other.position[1]
                sep_dx -= self.width * np.round(sep_dx / self.width)
                sep_dy -= self.height * np.round(sep_dy / self.height)
                sep_dist = np.sqrt(sep_dx ** 2 + sep_dy ** 2) + 1e-10
                if sep_dist < pp.separation_radius:
                    sep_t = 1.0 - sep_dist / pp.separation_radius
                    sep_force = sep_t * pp.separation_weight * current_force
                    self.velocity[0] += (sep_dx / sep_dist) * sep_force
                    self.velocity[1] += (sep_dy / sep_dist) * sep_force

        # Speed cap
        speed = np.sqrt(self.velocity[0] ** 2 + self.velocity[1] ** 2)
        if speed > current_speed:
            self.velocity *= current_speed / speed

        self.position += self.velocity
        self.position[0] %= self.width
        self.position[1] %= self.height

        # Starvation counter — incremented each frame, reset on kill
        self.frames_since_last_kill += 1
        if (cfg.PREDATOR_EVOLUTION_ENABLED
                and self.frames_since_last_kill >= cfg.PREDATOR_STARVATION_FRAMES):
            self.starved = True

        # Mass decay: lose mass when not eating (after grace period)
        if cfg.ACCRETION_HUNGER_ENABLED:
            if self.frames_since_last_kill > cfg.BH_MASS_DECAY_GRACE:
                self.mass = max(cfg.BH_MASS_MIN,
                                self.mass - cfg.BH_MASS_DECAY_RATE)

    def age_flashes(self):
        """Age flash effects and remove expired ones."""
        self.flashes = [f for f in self.flashes if f[5] < 12]
        for f in self.flashes:
            f[5] += 1

    def step_accretion(self):
        """Update accretion disk particles — spiral inward with increasing speed."""
        pp = self.params
        # Particle format: [angle, radius, initial_radius, r, g, b, age]
        alive = []
        for particle in self.accretion:
            particle[6] += 1  # age
            if particle[6] >= pp.accretion_lifetime or particle[1] <= 2:
                continue
            # Angular momentum conservation: spin faster as radius shrinks
            spin = pp.accretion_spin_speed * (particle[2] / max(particle[1], 1.0))
            particle[0] += spin   # angle
            particle[1] -= pp.accretion_infall_rate  # radius shrinks
            alive.append(particle)
        self.accretion = alive
