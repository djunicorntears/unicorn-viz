# Unicorn Viz Plan

## Status Legend

- `[todo]` not started
- `[doing]` actively in progress
- `[done]` completed
- `[decision]` needs product/architecture decision

## Phase 1 — Runtime, CLI, and Operational Foundations

- `[doing]` Audit the codebase for optimization opportunities, architectural inconsistencies, and cleanup candidates.
  Current findings:
  - runtime/logging/config/docs drift was present and has been corrected
  - repo hygiene still needs follow-up: tracked `.venv` / cache artifacts should be cleaned from version control in a dedicated pass
  - stale helper cleanup (for superseded audio-device logic) can be folded into a future cleanup PR
- `[done]` Add structured log output under `logs/`.
- `[done]` Add configurable log level via config and command line.
- `[done]` Add command-line overrides for common config values.
- `[done]` Add a robust `-h` / `--help` CLI entrypoint.
- `[done]` Update all documentation to reflect runtime/config/CLI behavior.

## Phase 2 — Platform and Display Support

- `[todo]` Add first-class Windows support.
  Notes:
  - windowing/input behavior
  - audio capture strategy on Windows
  - packaging/runtime dependency handling
- `[todo]` Add multi-monitor support.
  Notes:
  - cloned displays
  - extended/spread desktops
  - explicit monitor selection
  - fullscreen behavior per monitor
  - screenshot/recording implications
- `[todo]` Verify recent Ubuntu/Debian and Fedora compatibility matrix.
- `[todo]` Build a robust installer for supported Linux distributions.
- `[todo]` Evaluate packaging for Flatpak and Snap.

## Phase 3 — Assets and Media Expansion

- `[todo]` Add `assets/images/` support.
  Notes:
  - playlist-like loading behavior
  - splash-style animation/reactive presentation
- `[todo]` Add `assets/videos/` support for MP4 playback.
  Notes:
  - playlist integration
  - fullscreen scaling and transitions
  - audio sync policy
- `[todo]` Add `assets/sims/` support for IsaacLab/OpenUSD-style 3D animations.
  Notes:
  - playback/runtime format choice
  - audio sync hooks
  - GPU/runtime cost constraints

## Phase 4 — Product and Plugin Architecture

- `[todo]` Review and enhance each existing built-in effect before adding any new effects.
  Notes:
  - performance pass (GPU cost, allocations, frame budget)
  - consistency pass (parameters, naming, audio reactivity behavior)
  - visual polish pass (startup variance, transitions, readability)
  - documentation pass (effect-level options and expected behavior)
- `[decision]` Design external plugin loading for paid effect packs.
  Open questions:
  - local drop-in plugin directory vs hosted/cloud delivery
  - included effects vs third-party/paid effects separation
  - compatibility/version manifest format
  - licensing/entitlement enforcement model
  - security/trust boundary for executable plugin code
- `[todo]` Propose and prototype additional built-in effects and scene ideas.

## Feature Ideas to Explore

- `[todo]` Image playlist mode with shader-based transitions and audio-reactive treatment.
- `[todo]` Video-reactive overlays/effect compositing pipeline.
- `[todo]` Preset system for show setups (streaming, performance, ANSI-only, ambient, etc.).
- `[todo]` Scene scheduler with timed sections and transition choreography.
- `[todo]` Performance HUD / diagnostics overlay for FPS, frame time, audio source, and active transition.

## Delivery Strategy

- `[todo]` Start with the lowest-risk operational improvements first: logging, CLI, docs, and installer.
- `[todo]` Tackle platform/display support next: Windows and multi-monitor support affect many subsystems.
- `[todo]` Add media asset pipelines after runtime foundations are stable.
- `[decision]` Finalize plugin/commercial model before implementing paid-effect distribution.