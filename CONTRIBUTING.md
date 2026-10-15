# Contributing

UHI aims to make personal AI useful to ordinary creators. Start with a focused problem, explain the expected behavior, and keep each contribution small enough to review.

This is a preparation snapshot of MIT-licensed UHI-owned source. Submit only code you own or have permission to contribute under the project's MIT terms. Explain the provenance and license of any borrowed material; do not copy third-party installations into the repository.

## Development

Use Python 3.10+ on a separate development machine or directory. The runtime uses the Python standard library; Node.js with its built-in test runner is optional for frontend tests. Follow the README's launch commands with a fresh absolute `UHI_DATA_DIR` outside the checkout and other runtime installations.

Run:

```sh
python3 -B -m unittest discover -s tests/uhi -p 'test_*.py'
node --test tests/uhi/frontend.test.cjs
```

The included tests use temporary state, mock model responses and an in-memory HTTP fixture. Keep external requests mocked. Never use real credentials, private data, shared agent systems or production services as fixtures. Do not enable social, Telegram, scheduling, installation or model-start features as an incidental test fix.

For a pull request, state the problem, resulting behavior, relevant test results and known limits. Add regression tests when they meaningfully demonstrate a security or behavior fix. Update user-facing documentation when capabilities change. Check staged files for data, secrets, symlinks and generated artifacts before committing.

Report sensitive vulnerabilities using SECURITY.md. Public issues are appropriate for ordinary bugs, questions and proposed improvements without private details.
