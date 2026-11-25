# Future Ideas & Good First Issues

Ideas outside the current scope of DoneGate v0.1.0 are captured here to avoid scope creep.

## Potential Enhancements
- Optional LLM planner module (`donegate plan "<goal>"`) to draft `done.yaml` from a natural language goal.
- Web dashboard (`donegate ui`) reading `.donegate/state.json` and `.donegate/events.log`.
- GitHub Action (`sagar04-cloud/donegate-action`) for PR-level contract verification.
- OpenTelemetry trace export for `.donegate/events.log`.
- Additional language profiles: Elixir (Mix), Scala (sbt), Swift (SwiftPM), Zig, C/C++ (CMake/CTest).
- Additional agent integrations: Aider, OpenHands, Windsurf, Continue.dev.

## Good First Issues
- Add a `swift` language profile in `profiles/swift.yaml` with `Package.swift` detection.
- Add an `elixir` language profile in `profiles/elixir.yaml` with `mix.exs` detection.
- Add a `pytest --junitxml` example in `examples/`.
- Improve `donegate doctor` hints for Windows Scoop/Chocolatey/winget toolchains.
- Add JSON Schema `$id` and richer descriptions to `donegate export --schema`.
