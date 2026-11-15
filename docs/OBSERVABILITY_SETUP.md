# Observability setup (disabled by default)

## OpenLIT

Self-hosted OpenLIT may be added later for tracing agent, LLM, and tool calls.
No exporter is enabled in this repository by default.

## Sentry

`sentry-python` may be added to Python workers and Kaggle jobs for exceptions
and traces. No DSN is configured and no events are sent by default.

## Required scrubbing before enablement

- Exclude API keys, tokens, Authorization headers, and environment variable values.
- Exclude private filesystem paths.
- Review `observability/scrubbing.py` before changing any exporter from disabled to enabled.
