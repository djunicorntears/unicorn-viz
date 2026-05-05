"""
Raymarcher — SDF scene with sphere-tracing.
Morphing geometric shapes, fog, reflections, audio-reactive deformations.
Beat pulses a shockwave; bass blooms the SDF geometry.
"""
from __future__ import annotations

import moderngl

from unicornviz.effects.base import BaseEffect, AudioData

_VERT = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

_FRAG = """
#version 330
uniform float iTime;
uniform vec2  iResolution;
uniform float iBass;
uniform float iTreble;
uniform float iBeat;
uniform float iSpeed;

in  vec2 v_uv;
out vec4 fragColor;

#define MAX_STEPS 80
#define MAX_DIST  20.0
#define SURF_DIST 0.001

// ── SDFs ───────────────────────────────────────────────────────────────────
float sdSphere(vec3 p, float r) { return length(p) - r; }

float sdBox(vec3 p, vec3 b) {
    vec3 q = abs(p) - b;
    return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0);
}

float sdTorus(vec3 p, vec2 t) {
    vec2 q = vec2(length(p.xz) - t.x, p.y);
    return length(q) - t.y;
}

// Smooth union
float smin(float a, float b, float k) {
    float h = clamp(0.5 + 0.5*(b-a)/k, 0.0, 1.0);
    return mix(b, a, h) - k*h*(1.0-h);
}

// Rotation
mat2 rot2(float a) { float c=cos(a),s=sin(a); return mat2(c,-s,s,c); }

float scene(vec3 p) {
    float t = iTime * iSpeed;
    float bass  = iBass * 0.4;
    float shockwave = iBeat * exp(-length(p) * 1.5) * 0.3;

    // Spinning torus
    vec3 pt = p;
    pt.xz *= rot2(t * 0.7);
    pt.xy *= rot2(t * 0.4);
    float tor = sdTorus(pt, vec2(0.9 + bass, 0.25 + bass * 0.3));

    // Pulsing sphere cluster
    float sphs = 1e10;
    for (int i = 0; i < 5; i++) {
        float fi = float(i) / 5.0 * 6.28318;
        vec3 sc = vec3(cos(fi + t*0.5) * 1.4, sin(fi*2.0 + t*0.3)*0.5, sin(fi + t*0.5) * 1.4);
        sphs = smin(sphs, sdSphere(p - sc, 0.25 + bass * 0.2), 0.3);
    }

    // Central morphing box→sphere
    float morph = sin(t * 0.5) * 0.5 + 0.5;
    vec3 pb = p;
    pb.xy *= rot2(t * 0.3);
    pb.yz *= rot2(t * 0.2);
    float box = mix(sdBox(pb, vec3(0.5)), sdSphere(pb, 0.65), morph);
    box -= bass * 0.12;

    float d = smin(smin(tor, sphs, 0.5), box, 0.4);
    d += shockwave;

    // Infinite floor with bumps
    float floor_d = p.y + 2.0 + 0.06 * sin(p.x * 4.0 + t) * sin(p.z * 4.0 + t * 0.7);
    d = smin(d, floor_d, 0.3);

    return d;
}

vec3 normal(vec3 p) {
    vec2 e = vec2(0.001, 0.0);
    return normalize(vec3(
        scene(p + e.xyy) - scene(p - e.xyy),
        scene(p + e.yxy) - scene(p - e.yxy),
        scene(p + e.yyx) - scene(p - e.yyx)
    ));
}

float raymarch(vec3 ro, vec3 rd) {
    float d = 0.0;
    for (int i = 0; i < MAX_STEPS; i++) {
        vec3 p = ro + rd * d;
        float ds = scene(p);
        d += ds;
        if (ds < SURF_DIST || d > MAX_DIST) break;
    }
    return d;
}

vec3 palette(float t) {
    vec3 a = vec3(0.5);
    vec3 b = vec3(0.5);
    vec3 c = vec3(1.0, 0.7, 0.4);
    vec3 dd = vec3(0.00, 0.15, 0.20);
    return a + b * cos(6.28318 * (c*t + dd));
}

void main() {
    vec2 uv = v_uv * vec2(iResolution.x / iResolution.y, 1.0);
    float t = iTime * iSpeed;

    // Camera orbit
    vec3 ro = vec3(sin(t*0.25)*4.0, 1.5 + sin(t*0.1)*0.5, cos(t*0.25)*4.0);
    vec3 target = vec3(0.0, 0.0, 0.0);
    vec3 fwd = normalize(target - ro);
    vec3 right = normalize(cross(vec3(0,1,0), fwd));
    vec3 up = cross(fwd, right);
    vec3 rd = normalize(fwd + uv.x * right + uv.y * up);

    float d = raymarch(ro, rd);
    vec3 col = vec3(0.0);

    if (d < MAX_DIST) {
        vec3 p = ro + rd * d;
        vec3 n = normal(p);
        vec3 light = normalize(vec3(1.5, 2.5, 1.0));

        float diff = max(dot(n, light), 0.0);
        float spec = pow(max(dot(reflect(-light, n), -rd), 0.0), 32.0);
        float ao   = 1.0 - clamp(scene(p + n * 0.15) / 0.15, 0.0, 1.0) * 0.5;

        float dist_col = d / MAX_DIST;
        col = palette(dist_col + iTreble * 0.2 + iTime * 0.05);
        col *= diff * 0.8 + 0.2;
        col += spec * 0.4 * (0.8 + iBass * 0.4);
        col *= ao;

        // Fog
        float fog = exp(-d * 0.08);
        col = mix(vec3(0.02, 0.01, 0.04), col, fog);
    } else {
        // Background – starfield gradient
        col = vec3(0.01, 0.01, 0.03) + length(uv) * 0.02;
    }

    // Beat flash
    col += iBeat * 0.08 * vec3(0.5, 0.3, 1.0);

    // Vignette
    col *= 1.0 - 0.25 * dot(v_uv, v_uv);

    // Tone map
    col = col / (col + 0.8);
    col = pow(col, vec3(0.4545));   // gamma

    fragColor = vec4(col, 1.0);
}
"""


class Raymarcher(BaseEffect):
    NAME = "Raymarcher"
    AUTHOR = "unicorn-viz"
    TAGS = ["futuristic", "audio", "3d"]

    def _init(self) -> None:
        self.parameters = {"speed": 1.0}
        self._prog = self._make_program(_VERT, _FRAG)
        self._vao, self._vbo = self._fullscreen_quad()
        self._bass = 0.0
        self._treble = 0.0
        self._beat = 0.0

    def update(self, dt: float, audio: AudioData) -> None:
        super().update(dt, audio)
        self._bass = audio.bass
        self._treble = audio.treble
        if audio.beat > 0.5:
            self._beat = 1.0
        self._beat = max(0.0, self._beat - dt * 4.0)

    def render(self) -> None:
        self._prog["iTime"].value = self.time
        self._prog["iResolution"].value = (float(self.width), float(self.height))
        self._prog["iBass"].value = self._bass
        self._prog["iTreble"].value = self._treble
        self._prog["iBeat"].value = self._beat
        self._prog["iSpeed"].value = self.parameters["speed"]
        self._vao.render(moderngl.TRIANGLE_STRIP)

    def destroy(self) -> None:
        self._vao.release()
        self._vbo.release()
        self._prog.release()
