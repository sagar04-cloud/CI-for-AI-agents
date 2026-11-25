# DoneGate v0.1.0 Release Checklist

Follow these steps in order to publish DoneGate to GitHub and PyPI:

1. **Verify package & repo names are available**
   - Confirm `donegate` is unclaimed on PyPI: `https://pypi.org/project/donegate/`
   - Confirm GitHub repo `https://github.com/sagar04-cloud/CI-for-AI-agents` is ready.

2. **Configure PyPI Trusted Publishing (OIDC, no stored API tokens)**
   - Log in to PyPI -> *Your Account* -> *Publishing* -> *Add a new pending publisher*.
   - PyPI Project Name: `donegate`
   - Owner: `sagar04-cloud`
   - Repository name: `CI-for-AI-agents`
   - Workflow name: `release.yml`
   - Environment name: `pypi`
   - In GitHub Repo Settings -> *Environments*, create an environment named `pypi`.

3. **Create GitHub labels**
   - `good first issue`, `bug`, `new-language-profile`, `new-integration`

4. **Commit and push to GitHub**
   ```bash
   git add .
   git commit -m "feat: DoneGate v0.1.0 initial release"
   git branch -M main
   git remote add origin https://github.com/sagar04-cloud/CI-for-AI-agents.git
   git push -u origin main
   ```

5. **Wait for `CI` workflow to turn green** across Linux/macOS/Windows and Python 3.11/3.12/3.13.

6. **Tag and trigger release**
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```
   This triggers `.github/workflows/release.yml` to build, publish to PyPI via OIDC, and create the GitHub Release.

7. **Verify install on a clean machine**
   ```bash
   pipx install donegate   # or: uvx donegate --help
   donegate version
   ```
