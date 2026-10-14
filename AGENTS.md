# ALLSAFE development instructions

- This is a single-organization graduation-project prototype. Do not imply production readiness.
- Keep PhishCatch mobile support, Wazuh security integration, and our own Windows device-management agent in scope. ManageEngine integration and patch management are out of the first milestone.
- Work on a short-lived feature or fix branch from `develop`. Changes reach `develop` through pull requests; release changes reach `main` through a release pull request.
- Keep secrets, real employee data, model artifacts, and local databases out of Git.
- `packages/phishcatch` is an upstream Git submodule. Make and review upstream changes in its own repository, then update the pinned reference here. Never replace or flatten its Git history.
- Use typed Python and meaningful tests for authentication, enrollment, persistence, and authorization. Run the checks documented in the root README before claiming completion.
- Device credentials are device-specific. Never implement arbitrary remote-shell execution as a shortcut for device management.
- Prediction, verified training label, and model promotion are distinct operations. An incomplete scan must not be treated as proof that a URL is clean.
- Use Turkish for project documentation and English for identifiers and commit messages. Keep module boundaries explicit and document material architecture decisions.
