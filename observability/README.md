# Observability (not enabled by default)

OpenLIT and Sentry are documented here for future use. No events are sent by
default, and no secrets are committed.

## Scrubbing before enablement

Before enabling either exporter, configure scrubbing for:
- API keys and tokens
- Authorization headers
- environment variable values
- private filesystem paths
- request/response bodies containing secrets

See `observability/scrubbing.py` for the shared scrubbing helpers.
