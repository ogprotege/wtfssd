# UNMAINTAINED — not part of the wtfssd product

This directory holds a historical native menu bar experiment (SwiftUI
popover calling `wtfssd scan`).

**Product decision (2026-08-02, resource-ethical v2):** wtfssd is **CLI-only**.
Do not install this app for normal use. Do not add features here. Do not
document it as supported in README/COMMANDS.

Supported continuous monitoring (if any): one LaunchAgent via
`wtfssd optimize install-agent` (default hourly full `watch --once`).

See:

- `docs/superpowers/specs/2026-08-02-resource-ethical-v2.md`
- `COMMANDS.md`
