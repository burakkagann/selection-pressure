"""
GPU black holes (moderngl): the 'particle' style.

Renders each predator as an N-body style glowing particle accretion disk
(analytic Keplerian orbits, no self-gravity), additive with a warm colour ramp
and a dark evacuated centre, and composites it into the pygame scene: darken a
halo of the galaxy around the hole, add the particle glow, stamp a dark centre.
The predators' simulation is untouched; only their live state (position, mass,
lunge) is read.

Adapted from lechebs/nbody (MIT License, Copyright (c) 2026 Luca Ballone);
see THIRD_PARTY_NOTICES.md.

If moderngl is missing or the GL context or a shader fails to initialise,
``available`` stays False and the app falls back to the 2D 'classic' style.

Coordinates: GL is bottom-left-origin; surfaces are flipped on upload and
readback and predator y is flipped so the two conventions agree.
"""

from __future__ import annotations

import numpy as np
import pygame

from . import config

try:
    import moderngl
except Exception as exc:  # pragma: no cover - depends on the platform
    moderngl = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

STYLES = ("particle",)
MAX_HOLES = 3  # matches app.MAX_BLACK_HOLES
HALO_CACHE_SIZE = 32  # halo masks kept; each is at most a few MB


# ---- Particle pass: each point orbits its hole; warm additive colour ramp ----
_PD_VERTEX_SRC = """
#version 330
in float a_rnorm;   // pre-concentrated radial param 0..1 (0 inner, 1 outer)
in float a_phase;   // orbital phase offset
in float a_seed;    // 0..1 per-particle random
uniform float uTime;
uniform vec2  uCenter;      // hole center, GL pixel coords
uniform vec2  uRes;
uniform float uInner;       // px
uniform float uOuter;       // px
uniform float uIncl;        // radians, 0 = face-on
uniform float uThickness;   // vertical scatter fraction
uniform float uSpin;
out float vT;
out float vBright;
void main() {
    float r = uInner + (uOuter - uInner) * a_rnorm;
    float t = a_rnorm;
    float omega = uSpin * pow(r, -1.5) * 600.0;
    float ang = a_phase + uTime * omega;
    float yj = (a_seed - 0.5) * 2.0 * uThickness * r * (1.0 - 0.6 * t);
    vec3 p = vec3(r * cos(ang), yj, r * sin(ang));
    float c = cos(uIncl), s = sin(uIncl);
    vec3 pr = vec3(p.x, p.y * c - p.z * s, p.y * s + p.z * c);
    vec2 scr = uCenter + pr.xy;
    gl_Position = vec4((scr / uRes) * 2.0 - 1.0, 0.0, 1.0);
    gl_PointSize = 1.5;
    vT = t;
    vBright = (pow(1.0 - t, 1.7) + 0.10) * (0.75 + 0.25 * (pr.z / uOuter + 0.5));
}
"""

_PD_FRAGMENT_SRC = """
#version 330
in float vT;
in float vBright;
uniform vec3 uColHot;
uniform vec3 uColMid;
uniform vec3 uColCool;
uniform float uBrightness;
out vec4 f;
vec3 ramp(float t) {
    if (t < 0.5) return mix(uColHot, uColMid, t / 0.5);
    return mix(uColMid, uColCool, (t - 0.5) / 0.5);
}
void main() {
    vec2 d = gl_PointCoord - vec2(0.5);
    float fall = exp(-dot(d, d) * 9.0);
    f = vec4(ramp(vT) * vBright * fall * uBrightness, 1.0);
}
"""


class ShaderBlackHole:
    """Owns a standalone moderngl context and renders predators as GPU holes.

    Attributes:
        available: True only if the GL context and shaders initialised cleanly.
        error: why the renderer is unavailable, or None.
    """

    def __init__(self, width, height):
        self.width = int(width)
        self.height = int(height)
        self.available = False
        self.ctx = None
        self.error = None
        self.pd_vbo = None
        self._halo_cache = {}  # (reach, strength) -> dimming Surface
        self._pd_count = 0
        self._smooth_scale = {}  # id(pred) -> eased visual size multiplier

        if moderngl is None:
            self.error = f"moderngl could not be imported ({_IMPORT_ERROR})"
            return
        try:
            self._init_gl()
            self.available = True
        except Exception as exc:  # pragma: no cover - hardware/driver guard
            self.error = str(exc)
            self.close()

    @property
    def renderer_name(self):
        if not self.available:
            return ""
        return self.ctx.info.get("GL_RENDERER", "?")

    # ------------------------------------------------------------
    def _init_gl(self):
        self.ctx = moderngl.create_standalone_context()

        # --- Particle program + additive target ---
        self.pd_prog = self.ctx.program(
            vertex_shader=_PD_VERTEX_SRC, fragment_shader=_PD_FRAGMENT_SRC
        )
        self.pd_out_tex = self.ctx.texture((self.width, self.height), 3)
        self.pd_fbo = self.ctx.framebuffer(color_attachments=[self.pd_out_tex])
        self._build_particles(config.BH_PD_PARTICLE_COUNT)

    def _build_particles(self, count):
        """(Re)build the particle VBO with ``count`` orbiting particles."""
        count = int(max(1000, count))
        rng = np.random.default_rng(1)
        rnorm = rng.random(count) ** float(config.BH_PD_DENSITY_CONCENTRATION)
        phase = rng.random(count) * 2.0 * np.pi
        seed = rng.random(count)
        data = np.column_stack([rnorm, phase, seed]).astype("f4")
        if self.pd_vbo is not None:
            self.pd_vbo.release()
        self.pd_vbo = self.ctx.buffer(data.tobytes())
        self.pd_vao = self.ctx.vertex_array(
            self.pd_prog, [(self.pd_vbo, "1f4 1f4 1f4", "a_rnorm", "a_phase", "a_seed")]
        )
        self._pd_count = count

    # ------------------------------------------------------------
    @staticmethod
    def _set(prog, name, value):
        # The GLSL compiler drops unused uniforms, so a missing name is fine.
        try:
            prog[name].value = value
        except KeyError:
            pass

    def _visual_scale(self, pred, lunge_flag, lunge_amt):
        """Eased size multiplier (mass + lunge) for a predator.

        The target combines the mass-driven size (which the simulation bumps
        in discrete steps as the hole eats) and the lunge swell.  The rendered
        scale eases toward that target each frame so growth reads as an
        organic swell instead of a pop.
        """
        target = 1.0
        if config.ACCRETION_HUNGER_ENABLED:
            target *= pred.mass**config.BH_MASS_RADIUS_EXPONENT
        if lunge_flag and pred.lunging:
            target *= lunge_amt

        key = id(pred)
        prev = self._smooth_scale.get(key)
        if prev is None:
            cur = target  # first sighting: no jump-in
        else:
            alpha = min(1.0, max(0.005, float(config.BH_SCALE_SMOOTHING)))
            cur = prev + (target - prev) * alpha
        self._smooth_scale[key] = cur
        return cur

    def _prune_smooth(self, predators):
        """Drop eased-scale entries for predators that no longer exist."""
        live = {id(p) for p in predators}
        if len(self._smooth_scale) > len(live):
            self._smooth_scale = {k: v for k, v in self._smooth_scale.items() if k in live}

    # ------------------------------------------------------------
    def render(self, sim_surface, predators, frame):
        """Composite GPU black holes onto ``sim_surface`` in place.

        Returns True if anything was drawn.
        """
        if not self.available or not predators:
            return False
        if sim_surface.get_size() != (self.width, self.height):
            raise ValueError("surface size does not match the GPU renderer")
        with self.ctx:  # make this context current even if another one exists
            return self._render_particles(sim_surface, predators, frame)

    def _render_particles(self, sim_surface, predators, frame):
        holes = predators[:MAX_HOLES]
        H = self.height
        t = float(frame) / max(config.TARGET_FPS, 1)

        # Rebuild the particle buffer if the count changed.
        if int(config.BH_PD_PARTICLE_COUNT) != self._pd_count:
            self._build_particles(config.BH_PD_PARTICLE_COUNT)

        # --- Render all holes' particle disks into one additive FBO ---
        self.pd_fbo.use()
        self.ctx.viewport = (0, 0, self.width, H)
        self.pd_fbo.clear(0.0, 0.0, 0.0)
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (moderngl.ONE, moderngl.ONE)  # additive
        self.ctx.enable(moderngl.PROGRAM_POINT_SIZE)

        p = self.pd_prog
        self._set(p, "uRes", (float(self.width), float(H)))
        self._set(p, "uTime", t)
        self._set(p, "uIncl", float(np.radians(config.BH_PD_INCLINATION)))
        self._set(p, "uThickness", float(config.BH_PD_THICKNESS))
        self._set(p, "uSpin", float(config.BH_PD_SPIN))
        self._set(p, "uBrightness", float(config.BH_PD_BRIGHTNESS))
        self._set(p, "uColHot", tuple(config.BH_PD_COLOR_HOT))
        self._set(p, "uColMid", tuple(config.BH_PD_COLOR_MID))
        self._set(p, "uColCool", tuple(config.BH_PD_COLOR_COOL))
        self.ctx.enable(moderngl.PROGRAM_POINT_SIZE)
        self.ctx.blend_func = (moderngl.ONE, moderngl.ONE)  # additive
        vratio = max(0.05, np.cos(np.radians(config.BH_PD_INCLINATION)))  # disk squash

        self._prune_smooth(predators)
        for pred in holes:
            scale = self._visual_scale(
                pred, config.BH_PD_LUNGE_SCALE, config.BH_PD_LUNGE_SCALE_AMOUNT
            )
            inner = config.BH_PD_INNER * scale
            outer = config.BH_PD_OUTER * scale
            reach = outer * config.BH_PD_HALO_REACH
            cx = float(pred.position[0])
            cy = H - float(pred.position[1])  # GL bottom-origin
            px_cx = int(round(pred.position[0]))
            px_cy = int(round(pred.position[1]))

            # Render this hole's particle disk into the additive FBO.  Each hole
            # gets its own pass so overlapping holes never add a glow twice.
            self.pd_fbo.use()
            self.ctx.viewport = (0, 0, self.width, H)
            self.pd_fbo.clear(0.0, 0.0, 0.0)
            self.ctx.enable(moderngl.BLEND)
            self._set(p, "uCenter", (cx, cy))
            self._set(p, "uInner", inner)
            self._set(p, "uOuter", outer)
            self.pd_vao.render(mode=moderngl.POINTS, vertices=self._pd_count)
            self.ctx.disable(moderngl.BLEND)

            # 1) Darken a halo of the galaxy/trails so the disk pops.
            if config.BH_PD_HALO_STRENGTH < 1.0:
                halo = self._get_halo_surface(int(reach), config.BH_PD_HALO_STRENGTH)
                hr = halo.get_width() // 2
                sim_surface.blit(
                    halo, (px_cx - hr, px_cy - hr), special_flags=pygame.BLEND_RGB_MULT
                )

            # 2) Additive-blit the particle glow (sub-rect around the hole).
            gx = int(max(0, np.floor(cx - reach)))
            gx1 = int(min(self.width, np.ceil(cx + reach)))
            gy = int(max(0, np.floor(cy - reach)))
            gy1 = int(min(H, np.ceil(cy + reach)))
            if gx1 > gx and gy1 > gy:
                w, h = gx1 - gx, gy1 - gy
                data = self.pd_fbo.read(viewport=(gx, gy, w, h), components=3)
                glow = pygame.image.frombytes(data, (w, h), "RGB", True)
                sim_surface.blit(glow, (gx, H - (gy + h)), special_flags=pygame.BLEND_RGB_ADD)

            # 3) Stamp the opaque dark elliptical centre.
            dc = config.BH_PD_DARK_CENTER * inner
            ew = int(dc)
            eh = max(2, int(dc * vratio))
            if ew > 0 and eh > 0:
                pygame.draw.ellipse(
                    sim_surface, (0, 0, 0), (px_cx - ew, px_cy - eh, 2 * ew, 2 * eh)
                )

        return True

    def _get_halo_surface(self, reach, strength):
        """Cached circular multiply-gradient: dark at centre -> 1.0 at reach."""
        key = (reach, round(strength, 3))
        surf = self._halo_cache.pop(key, None)
        if surf is not None:
            self._halo_cache[key] = surf  # most recently used goes last
            return surf
        size = 2 * reach + 1
        xs = np.arange(size, dtype=np.float32) - reach
        yy, xx = np.meshgrid(xs, xs, indexing="ij")
        dist = np.sqrt(xx * xx + yy * yy)
        tt = np.clip(dist / max(reach, 1), 0.0, 1.0)
        s = tt * tt * (3.0 - 2.0 * tt)  # smoothstep: no hard seam at the rim
        factor = strength + (1.0 - strength) * s
        factor = np.where(dist <= reach, factor, 1.0)
        u8 = (factor * 255).astype(np.uint8)
        surf = pygame.Surface((size, size))
        px = pygame.surfarray.pixels3d(surf)
        px[:, :, 0] = u8.T
        px[:, :, 1] = u8.T
        px[:, :, 2] = u8.T
        del px
        self._halo_cache[key] = surf
        while len(self._halo_cache) > HALO_CACHE_SIZE:  # sizes change as holes feed
            self._halo_cache.pop(next(iter(self._halo_cache)))
        return surf

    # ------------------------------------------------------------
    def close(self):
        for name in (
            "pd_vao",
            "pd_vbo",
            "pd_out_tex",
            "pd_fbo",
            "pd_prog",
            "ctx",
        ):
            obj = getattr(self, name, None)
            try:
                if obj is not None:
                    obj.release()
            except Exception:
                pass
            setattr(self, name, None)
        self.available = False
