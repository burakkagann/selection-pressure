"""
SELECTION PRESSURE Configuration
================================
All simulation and rendering parameters with documented defaults.

Parameters are organized by subsystem. Module-level constants serve as the
active runtime values (toggled by keyboard in the exhibition).  The BoidParams
and PredatorParams dataclasses bundle behavioral parameters for injection into
simulation classes, enabling headless GA episodes with per-individual configs.
"""

import os
from dataclasses import dataclass, field

# ============================================================
# PARAMETERS - Tweak these to experiment!
# ============================================================

# --- Canvas ---
# Resolution of the simulation window.
# Higher = more space for boids to move, but heavier on GPU/CPU.
# Try: 1280x720 for lighter load, 2560x1440 for ultra-wide exhibitions.
WIDTH = 1920
HEIGHT = 1080

# --- Boids (Core Flocking) ---
# Number of boids in the simulation.
# More boids = denser flocks but heavier computation (O(n^2) distance checks).
# Sweet spot: 200-600. Above 800 may drop frames. Below 100 feels sparse.
NUM_BOIDS = 50

# SEPARATION_RADIUS: how close is "too close" — boids steer away within this range.
# Larger = boids keep more personal space, flock spreads out.
# Smaller = boids tolerate crowding, tighter formations.
# Try: 20 (tight swarms) to 80 (loose clouds).
SEPARATION_RADIUS = 80.0

# ALIGNMENT_RADIUS: boids within this range try to match heading/velocity.
# Larger = more coordinated large-scale movement (school of fish feel).
# Smaller = only immediate neighbors align, more chaotic.
# Try: 30 (fragmented groups) to 120 (massive coordinated waves).
ALIGNMENT_RADIUS = 60.0

# COHESION_RADIUS: boids within this range steer toward their group center.
# Larger = boids are attracted from farther away, forms bigger clusters.
# Smaller = only very nearby boids pull together, many small groups.
# Try: 50 (scattered) to 200 (one big flock).
COHESION_RADIUS = 75.0

# SEPARATION_WEIGHT: how aggressively boids avoid each other.
# Higher = stronger repulsion, boids bounce apart quickly.
# Lower = boids tolerate overlapping, denser core.
# Try: 0.5 (mush together) to 5.0 (explosive repulsion).
SEPARATION_WEIGHT = 6.5

# ALIGNMENT_WEIGHT: how strongly boids copy their neighbors' direction.
# Higher = more uniform streams, "marching" feel.
# Lower = boids keep their own heading, more turbulent.
# Try: 0.2 (independent) to 3.0 (synchronized rivers).
ALIGNMENT_WEIGHT = 1.0

# COHESION_WEIGHT: how strongly boids are pulled toward group center.
# Higher = tight ball-like clusters.
# Lower = loose, spread-out flocks.
# Try: 0.2 (scattered mist) to 2.0 (dense globules).
COHESION_WEIGHT = 0.2

# MAX_SPEED: absolute speed cap for each boid (pixels/frame).
# Higher = faster, more energetic motion (trails stretch longer).
# Lower = slow, meditative drift.
# Try: 1.5 (slow jellyfish) to 8.0 (frantic insects).
MAX_SPEED = 2.8

# MIN_SPEED: minimum speed floor (pixels/frame). Boids below this are boosted
# back up, preventing any boid from becoming stationary — especially useful for
# respawned boids at edges with no nearby neighbors to steer toward.
# 0 = disabled (boids can stop completely).
# Try: 0.3 (barely drifting) to 1.5 (always visibly moving).
MIN_SPEED = 0.5

# MAX_FORCE: maximum steering force per frame (acceleration cap).
# Higher = boids turn sharply, snappy reactions.
# Lower = boids turn gradually, smooth arcing paths.
# Try: 0.05 (slow graceful curves) to 0.4 (instant direction changes).
MAX_FORCE = 0.15

# --- Trails (Visual Persistence) ---
# TRAIL_FADE_RATE: overall fade multiplier applied per frame (0.0-1.0).
# Only used when per-channel fading is disabled (all three channel rates are equal).
# Try: 0.92 (short sparkles) to 0.995 (slow ghostly fading).
TRAIL_FADE_RATE = 0.975

# TRAIL_FADE_RGB: per-channel fade rates (R, G, B). Each channel fades independently.
# Red fading fastest and blue lingering creates a warm-to-cool trail color shift:
# fresh trails keep their original hue, aging trails drift toward blue/purple.
# Set all three equal to disable the effect (same as uniform TRAIL_FADE_RATE).
# Try: (0.96, 0.975, 0.985) warm->cool shift
#      (0.985, 0.96, 0.96)  cool->warm shift (red lingers)
#      (0.975, 0.975, 0.975) uniform fade (no color shift)
TRAIL_FADE_R = 0.970   # red fades fastest  -> trails lose warmth first
TRAIL_FADE_G = 0.975   # green fades at normal rate
TRAIL_FADE_B = 0.985   # blue lingers longest -> aging trails shift cool/purple

# GLOW_BASE_RADIUS: base pixel radius of each boid dot.
# Larger = fatter dots, more visible trails, painterly look.
# Smaller = fine dots, threadlike trails, delicate look.
# Try: 2 (fine threads) to 8 (thick brushstrokes).
GLOW_BASE_RADIUS = 4

# SPEED_AFFECTS_SIZE: if True, slower boids appear slightly larger (lingering glow),
# faster boids appear slightly smaller (streaked look).
# False = all boids same size regardless of speed.
SPEED_AFFECTS_SIZE = True

# STREAK_LENGTH: maximum length of velocity streaks in pixels.
# Each boid is drawn as a short line along its velocity direction.
# Faster boids get longer streaks (up to this max), slow boids get short dashes.
# 0 = disable streaks (draw circles only, original behavior).
# Try: 0 (dots only) to 20 (long comet tails).
STREAK_LENGTH = 12

# STREAK_WIDTH: pixel thickness of velocity streak lines.
# Thicker = bolder painterly strokes. Thinner = fine thread-like trails.
# Try: 1 (hair-thin) to 4 (bold strokes).
STREAK_WIDTH = 2

# --- Bloom / Glow ---
# BLOOM_ENABLED: if True, a soft glow halo surrounds bright areas.
# Simulates light bleeding/scattering — makes boid flocks look like they radiate energy.
# The effect is screen-only (not baked into trails), so screenshots stay clean.
BLOOM_ENABLED = True

# BLOOM_INTENSITY: brightness multiplier for the glow layer (0.0-1.0).
# Higher = stronger, more visible bloom halo around flocks.
# Lower = subtle, barely perceptible warmth around bright spots.
# Try: 0.15 (barely there) to 0.6 (heavenly glow) to 1.0 (blown out).
BLOOM_INTENSITY = 0.45

# BLOOM_DOWNSCALE: factor by which the frame is shrunk before blur.
# Higher = wider, softer glow (more blurred). Lower = tighter, sharper halo.
# The blur radius is roughly BLOOM_DOWNSCALE pixels in each direction.
# Try: 2 (tight halo) to 4 (medium glow) to 8 (massive atmospheric bloom).
BLOOM_DOWNSCALE = 4

# --- Color Palette ---
# COLOR_CYCLES: how many times the palette loops over ~30 seconds.
# Higher = faster color cycling, more rainbow shimmer.
# Lower = slower, more gradual color transitions.
# Try: 1 (slow breathe) to 8 (rapid kaleidoscope).
COLOR_CYCLES = 8

# ACTIVE_PALETTE: which palette to start with (0-4). Switch live with keys 1-5.
ACTIVE_PALETTE = 0

# Each palette is a list of (R, G, B) keyframes that boids interpolate through.
# Add/remove colors or edit RGB values to create custom palettes.
# More keyframes = more color variety. Fewer = simpler gradients.
PALETTES = {
    0: [  # Warm -> Cool (default)
        (255, 120, 50), (255, 60, 90), (220, 50, 180),
        (130, 60, 255), (60, 120, 255), (50, 200, 180),
    ],
    1: [  # Sunset -> Midnight
        (255, 200, 50), (255, 130, 30), (255, 60, 60),
        (180, 30, 100), (80, 20, 120), (20, 10, 80),
    ],
    2: [  # Earth -> Ocean
        (180, 140, 60), (120, 160, 60), (60, 140, 80),
        (40, 160, 140), (30, 120, 180), (20, 60, 140),
    ],
    3: [  # Neon
        (255, 0, 100), (255, 0, 255), (100, 0, 255),
        (0, 200, 255), (0, 255, 150), (200, 255, 0),
    ],
    4: [  # Monochrome (white-blue)
        (255, 255, 255), (200, 220, 255), (150, 180, 255),
        (100, 140, 255), (150, 180, 255), (200, 220, 255),
    ],
}

PALETTE_NAMES = {
    0: "Warm->Cool", 1: "Sunset->Midnight", 2: "Earth->Ocean",
    3: "Neon", 4: "Monochrome",
}

# --- Flow Field (Curl Noise) ---
# NOISE_INFLUENCE: how much the invisible wind field pushes boids.
# 0.0 = pure flocking only. Higher = more organic swirling drift.
# Try: 0.0 (pure boids) to 2.0 (wind dominates flocking).
NOISE_INFLUENCE = 0.7

# NOISE_SCALE: spatial frequency of the noise pattern.
# Smaller = broader, sweeping wind currents (ocean-like).
# Larger = tighter, more turbulent local eddies.
# Try: 0.001 (huge gentle waves) to 0.01 (tight chaotic swirls).
NOISE_SCALE = 0.003

# NOISE_SPEED: how fast the flow field evolves over time.
# Higher = wind changes rapidly, more energetic motion.
# Lower = slow-shifting currents, meditative feel.
# Try: 0.005 (glacial) to 0.08 (stormy).
NOISE_SPEED = 0.05

# --- Attractor (Invisible Orbiting Magnet) ---
# ATTRACTOR_ENABLED: if True, an invisible point orbits the center and gently
# pulls all boids toward it, keeping the flock roughly centered.
# False = boids drift freely (may spread out and wrap around edges).
ATTRACTOR_ENABLED = True

# ATTRACTOR_STRENGTH: how hard the attractor pulls boids toward it.
# Higher = boids cluster tightly around the orbit path.
# Lower = gentle nudge, boids still roam freely.
# Try: 0.002 (barely noticeable) to 0.05 (strong gravitational pull).
ATTRACTOR_STRENGTH = 0.005

# ATTRACTOR_ORBIT_RADIUS: how far from center the attractor point travels.
# Larger = wider orbit, pulls flock across more of the canvas.
# Smaller = tight orbit near center, flock stays compact.
# Try: 100 (tight center) to 600 (sweeping edge-to-edge).
ATTRACTOR_ORBIT_RADIUS = 300

# ATTRACTOR_ORBITS: how many full circles the attractor completes per ~30s cycle.
# Higher = faster orbiting, flock chases more actively.
# Lower = slow lazy orbit, subtle drift.
# Try: 0.5 (very slow) to 5 (rapid spinning).
ATTRACTOR_ORBITS = 2

# --- Black Hole Predator (Autonomous Hunter) ---
# BLACK_HOLE_ENABLED: if True, predator(s) chase boid clusters and "consume" them.
# Creates dramatic flee-scatter-regroup dynamics.
BLACK_HOLE_ENABLED = True

# NUM_BLACK_HOLES: how many independent predators roam the canvas.
# More = more chaos, boids constantly fleeing in different directions.
# Try: 1 (single threat) to 4 (overwhelming predation).
NUM_BLACK_HOLES = 1

# BLACK_HOLE_SPEED: cruising speed of predator (pixels/frame).
# Should be close to but slightly below MAX_SPEED so boids can barely escape.
# Higher = relentless hunter. Lower = lazy prowler boids can outrun.
# Try: 2.0 (slow stalker) to 4.5 (nearly as fast as boids).
BLACK_HOLE_SPEED = 2.5

# BLACK_HOLE_MAX_FORCE: predator steering agility (acceleration cap).
# Higher = tighter turns, can corner boids better.
# Lower = wide sweeping turns, boids can dodge.
# Try: 0.05 (clumsy) to 0.2 (razor-sharp turns).
BLACK_HOLE_MAX_FORCE = 0.12

# BLACK_HOLE_SIGHT_RADIUS: how far the predator can "see" boids to chase.
# Larger = predator locks onto distant clusters, always hunting.
# Smaller = predator only reacts to nearby boids, more idle wandering.
# Try: 200 (nearsighted) to 800 (eagle-eyed).
BLACK_HOLE_SIGHT_RADIUS = 400.0

# BLACK_HOLE_FLEE_RADIUS: boids within this distance start steering away.
# Larger = boids react earlier, predator rarely catches anyone.
# Smaller = boids notice late, more dramatic last-second escapes.
# Try: 80 (late reaction) to 250 (early warning system).
BLACK_HOLE_FLEE_RADIUS = 120.0

# BLACK_HOLE_FLEE_WEIGHT: strength of the flee steering force (multiplied by MAX_FORCE).
# Higher = boids bolt away harder, faster scattering.
# Lower = gentle avoidance, boids curve away slowly.
# Try: 0.5 (casual dodge) to 5.0 (explosive scatter).
BLACK_HOLE_FLEE_WEIGHT = 2.0

# BLACK_HOLE_PANIC_RADIUS: inner danger zone — boids here apply extra-strong flee.
# This is the "oh no" zone where boids go into overdrive.
# Try: 20 (tiny death zone) to 80 (wide panic area).
BLACK_HOLE_PANIC_RADIUS = 40.0

# BLACK_HOLE_PANIC_WEIGHT: strength of panic flee (multiplied by MAX_FORCE).
# Higher = boids near predator shoot away like a shockwave.
# Lower = panic zone is only slightly stronger than normal flee.
# Try: 3.0 (moderate urgency) to 12.0 (instant explosion outward).
BLACK_HOLE_PANIC_WEIGHT = 6.0

# BLACK_HOLE_CONSUME_RADIUS: boids closer than this are "eaten" and respawned at edges.
# Larger = predator eats more easily, more respawning.
# Smaller = boids must almost touch the predator to be consumed.
# Try: 8 (surgical strikes) to 30 (vacuum cleaner).
BLACK_HOLE_CONSUME_RADIUS = 25.0

# BLACK_HOLE_LUNGE_RADIUS: when a cluster is within this range, predator may lunge.
# Larger = lunges triggered from farther away, more frequent bursts.
# Smaller = predator only lunges at very close clusters.
# Try: 100 (close-range pounce) to 300 (long-range charge).
BLACK_HOLE_LUNGE_RADIUS = 180.0

# BLACK_HOLE_LUNGE_SPEED: burst speed during a lunge (pixels/frame).
# Must be > MAX_SPEED for the predator to actually catch fleeing boids.
# Try: 4.5 (barely faster) to 8.0 (lightning strike).
BLACK_HOLE_LUNGE_SPEED = 4.0

# BLACK_HOLE_LUNGE_DURATION: how many frames the lunge burst lasts.
# Longer = sustained chase. Shorter = quick stab.
# Try: 15 (quick jab) to 80 (prolonged pursuit).
BLACK_HOLE_LUNGE_DURATION = 40

# BLACK_HOLE_LUNGE_COOLDOWN: frames of rest after a lunge before another can start.
# Longer = more breathing room for boids between attacks.
# Shorter = relentless repeated lunges.
# Try: 40 (aggressive) to 300 (patient hunter).
BLACK_HOLE_LUNGE_COOLDOWN = 120

# BLACK_HOLE_SEPARATION_RADIUS: distance at which predators repel each other.
# Keeps multiple predators spread across the canvas instead of clumping.
# Larger = predators maintain wider territory. Smaller = can get closer.
# Try: 150 (close quarters OK) to 600 (own half of the screen each).
BLACK_HOLE_SEPARATION_RADIUS = 950.0

# BLACK_HOLE_SEPARATION_WEIGHT: how strongly predators push each other away.
# Higher = predators firmly avoid each other's territory.
# Lower = predators may drift near each other occasionally.
# Try: 0.2 (gentle suggestion) to 1.5 (hard territorial boundary).
BLACK_HOLE_SEPARATION_WEIGHT = 0.5

# BLACK_HOLE_VOID_RADIUS: visual size of the black center drawn for the predator (px).
# Purely cosmetic — does not affect simulation behavior.
# Try: 15 (small dot) to 60 (imposing void).
BLACK_HOLE_VOID_RADIUS = 30

# BLACK_HOLE_RING_RADIUS: visual size of the "event horizon" ring around the void (px).
# Purely cosmetic. Should be larger than VOID_RADIUS.
# Try: VOID_RADIUS + 10 to VOID_RADIUS + 30.
BLACK_HOLE_RING_RADIUS = 45

# BLACK_HOLE_RING_COLOR: RGB color of the event horizon ring.
# Try: (255, 0, 0) for menacing red, (0, 255, 255) for sci-fi cyan.
BLACK_HOLE_RING_COLOR = (80, 0, 120)

# BLACK_HOLE_FEAR_COLOR_SHIFT: if True, boids near predators shift toward red,
# creating a visual "fear" effect. False = boids keep their palette color.
BLACK_HOLE_FEAR_COLOR_SHIFT = True

# --- Black Hole Appearance Enhancements ---
# Toggle each layer individually to test, or combine for the full M87* effect.

# PHOTON_RING_ENABLED: replaces the thin purple ring with multi-layered
# concentric glow rings in warm astrophysical colors.  Outer rings are faint
# deep red, inner rings are white-hot.  Creates the iconic "ring of fire."
PHOTON_RING_ENABLED = False

# ACCRETION_GLOW_ENABLED: persistent ring of warm light orbiting the void.
# Always visible (not just when boids are consumed).  One side is brighter
# (Doppler beaming), slowly rotating.  Makes the black hole feel alive.
ACCRETION_GLOW_ENABLED = True

# PHOTON_SPHERE_ENABLED: thin bright white rim right at the void edge.
# Simulates the photon sphere where light orbits before falling in.
# A subtle but powerful detail that sells the black hole illusion.
PHOTON_SPHERE_ENABLED = True

# BLACK_HOLE_HALO_RADIUS: how far the light-dimming effect extends from center (px).
# Trails within this radius are gradually darkened each frame, as if light is
# being pulled into the void. Should be larger than RING_RADIUS.
# Try: 60 (tight edge darkening) to 200 (wide gravitational shadow).
BLACK_HOLE_HALO_RADIUS = 120

# BLACK_HOLE_HALO_STRENGTH: brightness retention at the inner edge (0.0-1.0).
# Each frame, trail pixels near the void are multiplied by this factor.
# Lower = faster drain (light gets swallowed quickly).
# Higher = subtle dimming (gentle gravitational pull on light).
# Try: 0.80 (aggressive drain) to 0.95 (gentle shadow).
BLACK_HOLE_HALO_STRENGTH = 0.92

# --- Accretion Disk (Spiral Consumption Effect) ---
# ACCRETION_ENABLED: if True, consumed boids briefly spiral around the black hole
# as glowing particles before fading, instead of vanishing instantly.
# Creates a visible "matter being swallowed" effect with persistent spiral trails.
ACCRETION_ENABLED = True

# ACCRETION_LIFETIME: how many frames each spiral particle lives.
# Longer = more sustained spiral trails. Shorter = quick flash of orbit.
# Try: 30 (quick swirl) to 90 (dramatic extended spiral).
ACCRETION_LIFETIME = 60

# ACCRETION_SPIN_SPEED: base angular velocity (radians/frame) at the starting radius.
# Particles spin faster as they spiral inward (angular momentum conservation).
# Higher = faster orbiting. Lower = slow graceful arcs.
# Try: 0.08 (slow orbit) to 0.25 (rapid spinning).
ACCRETION_SPIN_SPEED = 0.15

# ACCRETION_INFALL_RATE: how quickly particles spiral inward (pixels/frame radius shrink).
# Higher = fast collapse into the void. Lower = particles linger at distance.
# Try: 0.3 (slow drift) to 1.5 (rapid infall).
ACCRETION_INFALL_RATE = 0.7

# --- Gravitational Lensing ---
# LENS_ENABLED: if True, the pixel field around each black hole is visually
# warped inward, simulating how gravity bends light near a massive object.
# Trails and bloom light curve toward the void. Screen-only effect — does not
# accumulate on trail_surface, so screenshots stay clean.
LENS_ENABLED = True

# LENS_RADIUS: how far (px) the lensing distortion extends from center.
# Pixels beyond this radius are unaffected. Larger = wider gravity well.
# Should be >= HALO_RADIUS for visual consistency.
# Try: 100 (tight warp) to 200 (wide gravity well) to 300 (massive distortion).
LENS_RADIUS = 180

# LENS_STRENGTH: maximum pixel displacement at the inner edge (px).
# Higher = more dramatic bending. At the void boundary, pixels are shifted
# inward by this many pixels. Displacement falls off to zero at LENS_RADIUS.
# Try: 10 (subtle shimmer) to 30 (dramatic warp) to 60 (extreme funhouse).
LENS_STRENGTH = 30

# LENS_FALLOFF: exponent controlling how displacement falls off with distance.
# 1.0 = linear falloff (gentle, wide curve)
# 2.0 = quadratic (most light bending happens close to the hole)
# 0.5 = square root (even distribution, wider visible effect)
# Try: 1.5 (natural gravity-like) to 2.5 (concentrated near void).
LENS_FALLOFF = 1.5

# --- Galaxy Background (Precomputed at Startup) ---
# A static star field + nebula fog rendered behind boid trails.
# Computed once — zero per-frame cost except one surface blit.
# Demonstrates knowledge transfer from Modules 1, 2, 3, 4, 6, 8.
GALAXY_BG_ENABLED = True

# Star Field (Module 2.1.4: Stars — Gaussian clusters, brightness variation)
# Distant stars: single-pixel dim background scattered uniformly.
NUM_STARS_DISTANT = 2000
# Medium stars: Gaussian-clustered around galactic centers, 1-2 px.
NUM_STARS_MEDIUM = 400
# Bright stars: scattered foreground with 3x3 cross pattern + glow.
NUM_STARS_BRIGHT = 40
# Mega stars: very bright with multi-pixel Gaussian glow halos.
NUM_STARS_MEGA = 8

# Galactic cluster centers as (x_frac, y_frac, spread_frac).
# Coordinates are fractions of WIDTH/HEIGHT for resolution independence.
# spread_frac = Gaussian sigma as fraction of the smaller canvas dimension.
STAR_CLUSTER_CENTERS = [
    (0.35, 0.45, 0.15),   # Primary galactic center
    (0.70, 0.30, 0.10),   # Secondary cluster
    (0.55, 0.75, 0.08),   # Small satellite cluster
]

# Nebula Fog (Module 6.1.1: Perlin Noise concepts — smooth organic patterns)
# Maximum per-channel brightness for nebula pixels.
# Keep low (30-50) so nebula doesn't overwhelm boid trails.
NEBULA_MAX_BRIGHTNESS = 60
# Base grid size for noise generation (larger = broader fog structures).
NEBULA_GRID_SIZE = 48
# Number of noise layers composited for richer detail.
NEBULA_OCTAVES = 8

# Nebula tint colors — each generates a separate noise layer.
# (Module 1.1.1: RGB channel manipulation, additive color mixing)
NEBULA_COLORS = [
    (30, 10, 50),    # Deep purple
    (20, 30, 60),    # Deep blue
    (50, 15, 35),    # Dark pink/magenta
    (40, 25, 10),    # Warm amber
]

# Twinkle Effect (Module 8: Animation & Time — sine-wave brightness)
TWINKLE_ENABLED = True
# How many stars twinkle. Kept small for performance.
TWINKLE_COUNT = 25
# Brightness oscillation fraction (+/- this amount). 0.15 = +/- 15%.
TWINKLE_AMPLITUDE = 0.15
# (min, max) frequency in Hz for sine oscillation per star.
TWINKLE_SPEED_RANGE = (0.3, 1.2)

# --- Tiered Collective Behavior ---
# Two tiers of collective response based on LOCAL neighbor density:
#
# Tier 1 — Defensive Swirl (bait ball):
#   When a boid has >= DEFENSIVE_LOCAL_THRESHOLD neighbors nearby,
#   it enters defensive mode: tangential swirl around predators,
#   extra cohesion, silver shimmer visuals.
#
# Tier 2 — Quorum Fortress:
#   When a boid has >= QUORUM_THRESHOLD neighbors nearby, it enters
#   fortress mode: dense stationary cluster, halved energy drain,
#   blue-white pulse.  Overrides defensive swirl.
#
# Both tiers use QUORUM_SIGNAL_RADIUS for neighbor counting.
# Multiple independent clusters can form different tiers simultaneously.

DEFENSIVE_LOCAL_THRESHOLD = 80  # local neighbors for defensive swirl

# Defensive Formation visual + behavioral params
DEFENSIVE_COHESION_EXTRA = 0.04 # Extra pull toward local center of mass
DEFENSIVE_TANGENT_STRENGTH = 0.6   # Tangential swirl around predators
DEFENSIVE_TANGENT_RADIUS = 200.0   # Distance within which swirl applies
DEFENSIVE_SHIMMER_SPEED = 3.0      # Hz — silver flash oscillation
DEFENSIVE_SHIMMER_AMOUNT = 0.3     # Brightness oscillation range
DEFENSIVE_SILVER_BLEND = 0.25      # Blend toward silver color
DEFENSIVE_SILVER_COLOR = (220, 230, 255)
DEFENSIVE_STREAK_TIGHTEN = 0.7  # Streak width multiplier (<1 = thinner)

# --- Predator Evolution (Starvation + GA) ---
# PREDATOR_EVOLUTION_ENABLED: if True, predators that fail to catch boids
# will "starve" and respawn with mutated parameters cloned from the most
# successful surviving predator.  Creates an arms race where predators
# co-evolve alongside boids.
PREDATOR_EVOLUTION_ENABLED = True

# PREDATOR_STARVATION_FRAMES: frames without a kill before a predator starves.
# At 60 FPS, 600 = 10 seconds of unsuccessful hunting.
# Try: 300 (aggressive turnover) to 1200 (patient evaluation).
PREDATOR_STARVATION_FRAMES = 1800  # 30 seconds at 60 FPS

# PREDATOR_EXPLOSION_BOIDS: number of new boids spawned when a predator
# explodes from starvation.  They burst outward from the explosion center.
# Try: 30 (subtle pop) to 200 (dramatic population spike).
PREDATOR_EXPLOSION_BOIDS = 12

# PREDATOR_MUTATION_SIGMA: Gaussian mutation sigma as fraction of each
# parameter's default value when evolving a new predator.
# Try: 0.03 (conservative) to 0.15 (wild variation).
PREDATOR_MUTATION_SIGMA = 0.08

# --- Evolution (Death-Based Continuous GA) ---
# EVOLUTION_ENABLED: if True, each predator kill triggers selection + mutation.
# Dead boids are reborn with mutated genes from a fit survivor.
# False = boids respawn with default params (original behavior).
EVOLUTION_ENABLED = True

# EVOLUTION_COLOR_MODE: if True, boids are colored by lineage_id instead of
# the cycling palette.  Successful lineages spread — you watch one color
# take over the flock.  Toggle with E key.
EVOLUTION_COLOR_MODE = True

# MUTATION_SIGMA_FRAC: Gaussian mutation sigma as a fraction of each
# parameter's default value.  Controls how far a child can drift from parent.
# 0.05 = conservative (barely visible after hundreds of selections).
# 0.12 = moderate (visible drift within ~100 selections).
# 0.20 = aggressive (rapid exploration, high diversity).
# Try: 0.08 (slow but steady) to 0.20 (wild variation).
MUTATION_SIGMA_FRAC = 0.15

# MUTATION_SIGMA_DECAY: per-selection decay for mutation sigma.
# Gradually reduces exploration as the population converges.
# At 0.9998, after 1000 selections sigma is 82% of initial.
MUTATION_SIGMA_DECAY = 0.99998
# MUTATION_SIGMA_MIN_FRAC: floor for decayed sigma (fraction of default).
# Prevents mutation from becoming negligible.
MUTATION_SIGMA_MIN_FRAC = 0.03

# TOURNAMENT_SIZE: number of candidates sampled for tournament selection.
# Larger = stronger selection pressure (fittest almost always wins).
# Smaller = more random, preserves diversity longer.
# Try: 3 (weak, diverse) to 10 (strong, fast convergence).
TOURNAMENT_SIZE = 4

# Fitness weights (scored on living boids at each death event)
# Higher weights = that factor matters more for parent selection.
# Survival and predator distance are the strongest evolutionary signals
# because they directly measure "did this boid's genes help it stay alive?"
FITNESS_WEIGHT_SURVIVAL = 1.5    # frames alive since last respawn (reduced from 2.0)
FITNESS_WEIGHT_NEIGHBORS = 0.5   # number of boids within cohesion_radius
FITNESS_WEIGHT_SPEED = 0.3       # current speed as fraction of max_speed
FITNESS_WEIGHT_PREDATOR_DIST = 1.5  # reward safe (but not hiding) distance
FITNESS_WEIGHT_COHESION = 0.8    # reward boids with nearby neighbors (counters separation drift)
FITNESS_ISOLATION_PENALTY = 0.5  # penalty for boids with zero neighbors

# Predator distance scoring: optimal distance range (pixels).
# Too close = about to die.  Too far = hiding at edges (boring).
# Boids within this band get full predator-distance fitness.
FITNESS_PREDATOR_OPTIMAL_MIN = 150.0
FITNESS_PREDATOR_OPTIMAL_MAX = 500.0

# --- Population Control (Carrying Capacity) ---
# POPULATION_TARGET: ideal population count. Explosion boid count scales
# relative to this — full count when below, linearly to zero at 2x target.
# This prevents runaway growth from repeated black hole starvation events
# WITHOUT killing survivors (evolution fitness is fully preserved).
# 0 = disabled (explosions always spawn PREDATOR_EXPLOSION_BOIDS).
# Try: 150 (tight control) to 400 (generous cap).
POPULATION_TARGET = 800

# --- Periodic Culling (accelerates boid evolution) ---
# Every CULL_INTERVAL_FRAMES, evaluate all boids and replace the bottom
# CULL_BOTTOM_FRACTION with mutated offspring of top performers.
# Genome-only replacement — position/velocity unchanged, no visual disruption.
# 0 = disabled (evolution only via death-based selection).
CULL_INTERVAL_FRAMES = 7200   # every 2 minutes at 60 FPS
CULL_BOTTOM_FRACTION = 0.02   # replace bottom 2% with offspring of fittest

# --- Periodic Spawning (steady population growth) ---
# Spawns new boids at regular intervals with evolved genes from fit parents.
# This provides predictable, gradual growth independent of predator dynamics.
# Growth stops when POPULATION_TARGET is reached.
PERIODIC_SPAWN_ENABLED = True
PERIODIC_SPAWN_INTERVAL = 2700  # frames between spawns (45 sec at 60 FPS)
PERIODIC_SPAWN_COUNT = 3        # boids per spawn event

# --- Animation ---
# TARGET_FPS: target frames per second. 60 = smooth. 30 = lighter on CPU.
# The actual FPS depends on your hardware and NUM_BOIDS.
TARGET_FPS = 60

# SEED: random seed for reproducible initial positions/velocities.
# Change to get a different starting arrangement. Same seed = same start.
SEED = 42


# ============================================================
# DERIVED
# ============================================================

# Points to parent repo directory (screenshots saved at the repo root)
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============================================================
# INJECTABLE PARAMETER DATACLASSES
# ============================================================
# These bundle behavioral parameters into objects that can be passed to
# simulation classes.  Defaults match the module-level constants above.
# A future genetic algorithm can create per-individual BoidParams /
# PredatorParams with evolved values, and BoidsSimulation / BlackHolePredator
# will use them instead of the global defaults.

@dataclass
class BoidParams:
    """Behavioral parameters for boid flocking.

    Pass to BoidsSimulation to override global defaults.  For per-boid
    variation (GA genomes), pass arrays via BoidsSimulation.per_boid_params
    dict — keys match field names, values are numpy arrays of shape (N,).
    """
    # Core flocking
    separation_radius: float = SEPARATION_RADIUS
    alignment_radius: float = ALIGNMENT_RADIUS
    cohesion_radius: float = COHESION_RADIUS
    separation_weight: float = SEPARATION_WEIGHT
    alignment_weight: float = ALIGNMENT_WEIGHT
    cohesion_weight: float = COHESION_WEIGHT
    max_speed: float = MAX_SPEED
    min_speed: float = MIN_SPEED
    max_force: float = MAX_FORCE
    # Noise flow field
    noise_influence: float = NOISE_INFLUENCE
    noise_scale: float = NOISE_SCALE
    noise_speed: float = NOISE_SPEED
    # Attractor
    attractor_enabled: bool = ATTRACTOR_ENABLED
    attractor_strength: float = ATTRACTOR_STRENGTH
    attractor_orbit_radius: float = ATTRACTOR_ORBIT_RADIUS
    attractor_orbits: float = ATTRACTOR_ORBITS
    # Timing (used for attractor orbit speed calculation)
    target_fps: int = TARGET_FPS


@dataclass
class PredatorParams:
    """Behavioral parameters for a black hole predator.

    Pass to BlackHolePredator to override global defaults.  Each predator
    can have its own PredatorParams, enabling per-predator evolved strategies.
    """
    # Movement
    speed: float = BLACK_HOLE_SPEED
    max_force: float = BLACK_HOLE_MAX_FORCE
    sight_radius: float = BLACK_HOLE_SIGHT_RADIUS
    # Boid flee response (read by BoidsSimulation during flee calculation)
    flee_radius: float = BLACK_HOLE_FLEE_RADIUS
    flee_weight: float = BLACK_HOLE_FLEE_WEIGHT
    panic_radius: float = BLACK_HOLE_PANIC_RADIUS
    panic_weight: float = BLACK_HOLE_PANIC_WEIGHT
    consume_radius: float = BLACK_HOLE_CONSUME_RADIUS
    # Lunge attack
    lunge_radius: float = BLACK_HOLE_LUNGE_RADIUS
    lunge_speed: float = BLACK_HOLE_LUNGE_SPEED
    lunge_duration: int = BLACK_HOLE_LUNGE_DURATION
    lunge_cooldown: int = BLACK_HOLE_LUNGE_COOLDOWN
    # Predator-predator separation
    separation_radius: float = BLACK_HOLE_SEPARATION_RADIUS
    separation_weight: float = BLACK_HOLE_SEPARATION_WEIGHT
    # Accretion particles (visual, but computed in simulation step)
    accretion_enabled: bool = ACCRETION_ENABLED
    accretion_lifetime: int = ACCRETION_LIFETIME
    accretion_spin_speed: float = ACCRETION_SPIN_SPEED
    accretion_infall_rate: float = ACCRETION_INFALL_RATE


# ============================================================
# GENOME DEFINITION (fields evolved per boid)
# ============================================================
# Each entry: (field_name, default_value, min_bound, max_bound)
# min/max prevent degenerate values after mutation.

GENOME_FIELDS = [
    ('separation_weight', SEPARATION_WEIGHT, 0.5, 15.0),
    ('alignment_weight',  ALIGNMENT_WEIGHT,  0.05, 5.0),
    ('cohesion_weight',   COHESION_WEIGHT,   0.02, 3.0),
    ('separation_radius', SEPARATION_RADIUS, 10.0, 150.0),
    ('alignment_radius',  ALIGNMENT_RADIUS,  15.0, 150.0),
    ('cohesion_radius',   COHESION_RADIUS,   20.0, 250.0),
    ('max_speed',         MAX_SPEED,         1.5, 8.0),
    ('min_speed',         MIN_SPEED,         0.2, 3.0),
    ('max_force',         MAX_FORCE,         0.03, 0.4),
]

# ============================================================
# PREDATOR GENOME DEFINITION (fields evolved per predator)
# ============================================================
# Each entry: (field_name, default_value, min_bound, max_bound)
# Field names match PredatorParams dataclass attributes.

PREDATOR_GENOME_FIELDS = [
    ('speed',           BLACK_HOLE_SPEED,           2.0, 6.0),
    ('max_force',       BLACK_HOLE_MAX_FORCE,       0.05, 0.25),
    ('sight_radius',    BLACK_HOLE_SIGHT_RADIUS,    200.0, 800.0),
    ('lunge_speed',     BLACK_HOLE_LUNGE_SPEED,     4.0, 8.0),
    ('lunge_duration',  BLACK_HOLE_LUNGE_DURATION,  15, 80),
    ('lunge_cooldown',  BLACK_HOLE_LUNGE_COOLDOWN,  40, 300),
    ('consume_radius',  BLACK_HOLE_CONSUME_RADIUS,  10.0, 40.0),
]


# ============================================================
# NEBULA RESOURCE FIELDS
# ============================================================
# Nebula gas clouds scattered across the canvas.  Stars must forage
# these clouds to maintain energy.  Clouds deplete under feeding
# pressure and slowly regenerate, creating migration patterns.

NEBULA_FIELDS_ENABLED = True
NUM_NEBULA_CLOUDS = 6           # number of resource patches
NEBULA_CLOUD_RADIUS = 200.0     # sigma of Gaussian density falloff (px)
NEBULA_CLOUD_MAX_DENSITY = 1.0  # peak density at center
NEBULA_CLOUD_REGEN_RATE = 0.002 # density recovery per frame
NEBULA_CLOUD_DEPLETION_RATE = 0.0005  # density lost per feeding boid per frame
NEBULA_CLOUD_MIN_DENSITY = 0.1  # floor — clouds never fully deplete
NEBULA_CLOUD_DRIFT_SPEED = 0.15 # slow drift (px/frame) to prevent camping

# --- Star Energy (Metabolism) ---
# Each star has an internal energy that depletes over time.
# Stars must overlap nebula clouds to feed.  Energy maps to brightness:
# starving stars dim and redden, well-fed stars blaze.
STAR_ENERGY_ENABLED = True
STAR_ENERGY_MAX = 1.0           # full energy
STAR_ENERGY_INITIAL = 0.7       # spawn energy
STAR_ENERGY_DRAIN_RATE = 0.0008 # passive drain per frame (~75s to empty)
STAR_ENERGY_FEED_RATE = 0.005   # energy gained per frame when inside nebula
STAR_ENERGY_FEED_RADIUS = 180.0 # must be within this distance of cloud center
STAR_ENERGY_LOW_THRESHOLD = 0.3 # below this: star dims, reddens, gets desperate
STAR_ENERGY_CRITICAL = 0.1      # below this: star is visibly dying

# Fitness weight for energy level (rewards successful foragers)
FITNESS_WEIGHT_ENERGY = 1.0

# --- Chemotaxis (gradient following toward nebula) ---
# Stars steer toward the nearest high-density cloud.  Hungry stars
# steer harder (desperation foraging).
CHEMOTAXIS_ENABLED = True
CHEMOTAXIS_STRENGTH = 0.08      # base steering force toward nearest nebula
CHEMOTAXIS_HUNGER_MULT = 3.0    # hungry stars steer this many times harder


# ============================================================
# QUORUM SENSING (collective fortress behavior)
# ============================================================
# When local star density exceeds a threshold, stars switch from
# individual foraging to collective fortress mode: tighter formation,
# reduced energy drain, but inability to reach food.  The tension
# between safety and starvation drives dynamic behavior.

QUORUM_ENABLED = True
QUORUM_SIGNAL_RADIUS = 150.0    # radius within which stars sense each other
QUORUM_THRESHOLD = 200          # min neighbors to trigger fortress mode (tier 2)
QUORUM_FORTRESS_COHESION = 0.06 # extra cohesion pull when in fortress
QUORUM_FORTRESS_SPEED_MULT = 0.7  # slow down in fortress (conserve energy)
QUORUM_ENERGY_DRAIN_MULT = 0.5  # fortress halves energy drain (safety bonus)
QUORUM_BREAK_ENERGY = 0.25      # energy below this forces break from fortress
QUORUM_VISUAL_PULSE = True      # fortress stars pulse in unison


# ============================================================
# ACCRETION HUNGER (Black Hole Mass Dynamics)
# ============================================================
# Black holes have a mass that changes based on feeding.  Eating stars
# increases mass (bigger, stronger pull, slower).  Starvation causes
# mass decay (nimbler but weaker).  Creates visible predator lifecycles.

ACCRETION_HUNGER_ENABLED = True
BH_MASS_INITIAL = 1.0          # starting mass multiplier
BH_MASS_MIN = 0.4              # minimum mass (nimble but weak)
BH_MASS_MAX = 2.5              # maximum mass (powerful but slow)
BH_MASS_GAIN_PER_KILL = 0.10   # mass gained per star consumed
BH_MASS_DECAY_RATE = 0.0003    # mass lost per frame when not eating
BH_MASS_DECAY_GRACE = 120      # frames after a kill before decay starts
# Scaling exponents: how mass affects behavior
BH_MASS_SPEED_EXPONENT = -0.5      # speed ~ mass^(-0.5): heavier = slower
BH_MASS_RADIUS_EXPONENT = 1.0      # radii ~ mass^(1.0): heavier = bigger (linear)
BH_MASS_FORCE_EXPONENT = 0.3       # steering ~ mass^(0.3)
BH_MASS_LUNGE_SPEED_EXPONENT = -0.3  # lunge speed penalty when heavy

# ============================================================
# ECOSYSTEM GENOME FIELDS (appended after constants are defined)
# ============================================================
# Evolved per-boid traits for nebula/quorum systems.
GENOME_FIELDS.extend([
    ('chemotaxis_strength', CHEMOTAXIS_STRENGTH, 0.01, 0.3),
    ('quorum_threshold',    float(QUORUM_THRESHOLD), 50.0, 400.0),
])
