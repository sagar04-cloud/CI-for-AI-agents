# Future Ideas & Good First Issues

Ideas outside the current scope of DoneGate v1.1 are captured here to avoid scope creep.

## Potential Enhancements
- PR comment bot posting DoneGate check & scope summaries directly on GitHub Pull Requests.
- IDE extensions (VS Code / JetBrains) rendering `.donegate/state.json` and scope violations inline.
- Diff-line-aware `no_new_lint_errors` (comparing exact changed lines rather than total error count).
- Remote/team artifact store for `.donegate/events.log` replay across CI runners.

## Good First Issues
- Add a Haskell (`stack.yaml` / `*.cabal`) language profile in `profiles/haskell.yaml`.
- Add a Kotlin Multiplatform / Gradle Kotlin DSL example in `examples/`.
- Add a `vhs` tape script in `docs/demo.tape` to auto-generate the terminal demo GIF.
- Add shell completion setup instructions (`donegate --install-completion`) to `README.md`.
