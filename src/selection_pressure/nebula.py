"""
SELECTION PRESSURE - Nebula Resource Fields
===========================================
Manages nebula gas clouds that serve as food sources for stars.

Stars must forage these clouds to maintain energy.  Clouds deplete when
fed upon and slowly regenerate, creating migration patterns and
natural congregation points.  Black holes tend to lurk near rich clouds,
creating the core tension: safety vs. starvation.

Each cloud is a 2D Gaussian density field that drifts slowly across
the canvas (toroidal wrapping).  All computation is vectorized NumPy.
"""

import numpy as np
from . import config as cfg


class NebulaField:
    """Collection of nebula gas clouds that stars consume for energy.

    Args:
        num_clouds: number of resource patches
        width, height: canvas dimensions (toroidal)
        rng: numpy random generator instance
    """

    def __init__(self, num_clouds, width, height, rng):
        self.num = num_clouds
        self.width = width
        self.height = height
        self.rng = rng

        # Cloud positions — avoid spawning too close to edges
        margin = 0.15
        self.positions = np.column_stack([
            rng.uniform(width * margin, width * (1 - margin), num_clouds),
            rng.uniform(height * margin, height * (1 - margin), num_clouds),
        ])

        # Current density level [min, max] — starts near full
        self.densities = np.full(num_clouds,
                                 cfg.NEBULA_CLOUD_MAX_DENSITY * 0.9)

        # Slow drift velocities (random direction, fixed slow speed)
        angles = rng.uniform(0, 2 * np.pi, num_clouds)
        self.drift_vel = np.column_stack([
            np.cos(angles) * cfg.NEBULA_CLOUD_DRIFT_SPEED,
            np.sin(angles) * cfg.NEBULA_CLOUD_DRIFT_SPEED,
        ])

        # Occasionally reverse drift direction for organic feel
        self._drift_change_interval = 600  # frames between direction tweaks
        self._drift_frame = 0

    def get_density_at(self, positions):
        """Return (N,) density experienced by each boid position.

        Sum of Gaussian contributions from all clouds, weighted by each
        cloud's current density level.  Uses toroidal shortest distance.

        Args:
            positions: (N, 2) boid positions

        Returns:
            (N,) float array of density values [0, ~max_density]
        """
        total = np.zeros(positions.shape[0], dtype=np.float64)
        sigma = cfg.NEBULA_CLOUD_RADIUS
        inv_2sig2 = 1.0 / (2.0 * sigma * sigma)

        for i in range(self.num):
            dx = positions[:, 0] - self.positions[i, 0]
            dy = positions[:, 1] - self.positions[i, 1]
            # Toroidal wrapping
            dx -= self.width * np.round(dx / self.width)
            dy -= self.height * np.round(dy / self.height)
            dist_sq = dx * dx + dy * dy
            # Gaussian falloff weighted by cloud density
            contrib = self.densities[i] * np.exp(-dist_sq * inv_2sig2)
            total += contrib

        return total

    def get_nearest_cloud_direction(self, positions):
        """Return (N, 2) unit vectors pointing toward the best nearby cloud.

        "Best" = highest density-weighted attractiveness considering both
        distance and current density.  Stars prefer close, rich clouds.

        Args:
            positions: (N, 2) boid positions

        Returns:
            (N, 2) unit direction vectors (zero if no clouds nearby)
        """
        n = positions.shape[0]
        best_score = np.full(n, -1.0)
        best_dx = np.zeros(n)
        best_dy = np.zeros(n)

        for i in range(self.num):
            dx = self.positions[i, 0] - positions[:, 0]
            dy = self.positions[i, 1] - positions[:, 1]
            # Toroidal wrapping
            dx -= self.width * np.round(dx / self.width)
            dy -= self.height * np.round(dy / self.height)
            dist = np.sqrt(dx * dx + dy * dy).clip(1e-10)

            # Attractiveness: density / distance (prefer close, rich clouds)
            score = self.densities[i] / (dist + 50.0)  # +50 softens near-field

            better = score > best_score
            best_score = np.where(better, score, best_score)
            best_dx = np.where(better, dx, best_dx)
            best_dy = np.where(better, dy, best_dy)

        # Normalize to unit vectors
        mag = np.sqrt(best_dx * best_dx + best_dy * best_dy).clip(1e-10)
        return np.column_stack([best_dx / mag, best_dy / mag])

    def deplete(self, positions):
        """Reduce cloud density based on feeding boids within radius.

        Each boid within feed_radius of a cloud center reduces that cloud's
        density.  Multiple boids feeding from the same cloud drain it faster.

        Args:
            positions: (N, 2) boid positions
        """
        feed_r = cfg.STAR_ENERGY_FEED_RADIUS

        for i in range(self.num):
            dx = positions[:, 0] - self.positions[i, 0]
            dy = positions[:, 1] - self.positions[i, 1]
            dx -= self.width * np.round(dx / self.width)
            dy -= self.height * np.round(dy / self.height)
            dist = np.sqrt(dx * dx + dy * dy)

            feeders = (dist < feed_r).sum()
            if feeders > 0:
                drain = feeders * cfg.NEBULA_CLOUD_DEPLETION_RATE
                self.densities[i] = max(cfg.NEBULA_CLOUD_MIN_DENSITY,
                                        self.densities[i] - drain)

    def regenerate(self):
        """Slowly restore cloud density toward max."""
        self.densities = np.minimum(
            cfg.NEBULA_CLOUD_MAX_DENSITY,
            self.densities + cfg.NEBULA_CLOUD_REGEN_RATE)

    def drift(self):
        """Move clouds slowly, wrapping toroidally."""
        self.positions += self.drift_vel
        self.positions[:, 0] %= self.width
        self.positions[:, 1] %= self.height

        # Occasionally nudge drift direction for organic movement
        self._drift_frame += 1
        if self._drift_frame >= self._drift_change_interval:
            self._drift_frame = 0
            # Small random rotation of drift vectors
            angle_nudge = self.rng.normal(0, 0.3, self.num)
            cos_a = np.cos(angle_nudge)
            sin_a = np.sin(angle_nudge)
            vx = self.drift_vel[:, 0]
            vy = self.drift_vel[:, 1]
            self.drift_vel[:, 0] = vx * cos_a - vy * sin_a
            self.drift_vel[:, 1] = vx * sin_a + vy * cos_a

    def step(self, boid_positions):
        """One frame: deplete from feeding boids, regenerate, drift."""
        self.deplete(boid_positions)
        self.regenerate()
        self.drift()
