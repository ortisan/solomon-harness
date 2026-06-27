# Observability Specialist Profile

The Observability Specialist establishes monitoring infrastructure, sets up instrumentation, analyzes performance metrics, and builds system dashboards.

## Core Duties
- Configure log diagnostics and central logging architectures to ensure system auditability.
- Implement metrics tracking and application instrumentation across all system components.
- Conduct regular performance profiling to identify execution bottlenecks, memory leaks, and latency issues.
- Build and maintain system monitoring dashboards to provide clear visibility into system health and resource consumption.

<!-- BEST_PRACTICES_APPENDED_START -->

# OpenTelemetry Observability Pattern

This document defines the guidelines and rules for integrating the OpenTelemetry standard into the system. The objective is to achieve comprehensive, structured, and correlatable telemetry across all application services.

## Core Telemetry Components

1. Structured JSON Logging
   - All log outputs must be written in a structured JSON format.
   - Every log message must include active tracing context keys: `trace_id` and `span_id`.
   - Include relevant metadata fields (e.g., service name, environment, process version) in the JSON payload structure.
   - Do not include sensitive information or credentials in log statements.

2. Custom Metrics
   - Instrument key system components with dedicated metrics types:
     - Counters: Monotonically increasing values to track quantities (e.g., total requests handled, transaction attempts, validation errors).
     - Gauges: Non-monotonic values representing immediate states (e.g., active connection pool size, memory utilization percentage).
     - Histograms: Measures the distribution of values over time (e.g., response latency distributions, database query execution times).
   - Metrics must include standardized attribute tags to allow filtering by service, region, and operation type.

3. Distributed Tracing
   - Capture transaction lifecycles as a sequence of connected Spans.
   - Pass tracking metadata across network and process boundaries to trace complete execution paths in distributed setups.

## Instrumentation Rules

1. Entry Point Spans
   - Every external entry point (e.g., HTTP request controller, cron job runner, queue worker) must immediately initialize a root or child Span representing the request lifecycle.
   - Extract tracing context from incoming requests to link the span to the caller.

2. Logical Block Isolation
   - Initialize distinct child Spans for significant nested operations, particularly database queries, outbound HTTP requests, external file system lookups, and computationally heavy functions.
   - Provide clear, descriptive names for child spans (e.g., `db.query.select_user`, `http.out.fetch_rates`).

3. Exception Reporting
   - When an exception occurs within a Span, catch the error, write it to the Span details using the standard API (`record_exception`), set the Span status to error, and raise or handle the error appropriately.
   - Ensure the stack trace and the error message are attached to the span without disclosing internal secrets.

4. Propagation Headers
   - For all outbound HTTP calls or inter-process communications (IPC), inject the current trace parent information into the transport headers (following the W3C Trace Context specification: `traceparent` and `tracestate`).
