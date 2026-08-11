# Rate Limiter Service

## Feature Objective

Implement a distributed rate-limiting service that enforces per-client request quotas across multiple API gateway instances, preventing abuse while maintaining low-latency request processing.

## User Stories

- **As a** platform operator, **I want** to configure rate limits per API key, **So that** I can protect backend services from traffic spikes and abuse.
- **As a** developer consuming the API, **I want** to receive clear rate-limit headers in every response, **So that** I can implement client-side back-off logic proactively.
- **As a** security engineer, **I want** rate-limit violations logged with client metadata, **So that** I can investigate potential abuse patterns.

## Business Rules

- BR-001: Each API key must have a configurable requests-per-minute (RPM) quota defaulting to 60 RPM.
- BR-002: Rate-limit counters must be consistent across all gateway instances within a 1-second synchronisation window.
- BR-003: Exceeding the quota must return HTTP 429 with a Retry-After header indicating the reset window.
- BR-004: Internal service-to-service calls authenticated via mTLS are exempt from rate limiting.

## Acceptance Criteria

### AC-001: Basic rate limiting
- **Given** an API key with a 60 RPM limit
- **When** the client sends the 61st request within a 1-minute window
- **Then** the service returns HTTP 429 with a `Retry-After` header

### AC-002: Rate limit headers
- **Given** any authenticated API request
- **When** the response is returned
- **Then** it includes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers

### AC-003: Internal service bypass
- **Given** a request authenticated via mTLS with a service certificate
- **When** the request is processed by the gateway
- **Then** rate-limit checks are skipped entirely

## Non-Functional Requirements

- **Performance**: 99th-percentile latency overhead from rate-limit checks must be below 5ms (p99 < 5ms)
- **Availability**: The rate limiter must degrade gracefully — if the counter store is unavailable, requests are allowed through with a logged warning
- **Scalability**: The solution must support at least 50,000 unique API keys without performance degradation

## Out of Scope

- Per-endpoint or per-route rate limiting (only per-API-key in this iteration)
- Admin UI for managing rate-limit configurations
- Real-time analytics dashboard for rate-limit metrics
