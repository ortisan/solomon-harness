# Error Handling and Problem Details

Centralize error handling so the domain defines each failure once, a single handler per transport renders it, and the wire format is chosen only at the boundary. Domain and adapter code throws or returns one typed error model; never let a request handler hand-build an error response inline, because scattered `try/catch`-to-JSON blocks drift apart and leak internals. This is the canonical error reference for the harness; the `rest_api_implementation` skill defers HTTP error shaping to it.

## The domain error model (protocol-agnostic)

One internal representation, free of any transport concept. It carries a stable machine-readable `kind`, a human message, optional structured `details` (field violations), and a cause chain. Status codes live nowhere in here.

```python
from enum import Enum

class Kind(str, Enum):
    NOT_FOUND = "NOT_FOUND"; VALIDATION = "VALIDATION"; CONFLICT = "CONFLICT"
    UNAUTHENTICATED = "UNAUTHENTICATED"; PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"; UNAVAILABLE = "UNAVAILABLE"; INTERNAL = "INTERNAL"

class FieldViolation:
    def __init__(self, field: str, message: str):
        self.field, self.message = field, message

class AppError(Exception):
    def __init__(self, kind: Kind, message: str,
                 details: list[FieldViolation] | None = None,
                 cause: Exception | None = None):
        super().__init__(message)
        self.kind, self.message, self.details = kind, message, details or []
        self.__cause__ = cause      # preserve the chain for server-side logging
```

The boundary maps `kind` to each protocol through one table. This is the single source of truth, and it is the grpc-gateway standard mapping (`runtime.HTTPStatusFromCode`) read in reverse, so HTTP and gRPC stay consistent.

| Kind | HTTP | gRPC code |
| --- | --- | --- |
| NOT_FOUND | 404 | NOT_FOUND (5) |
| VALIDATION | 422 (or 400) | INVALID_ARGUMENT (3) |
| CONFLICT | 409 | ALREADY_EXISTS (6) / ABORTED (10) |
| UNAUTHENTICATED | 401 | UNAUTHENTICATED (16) |
| PERMISSION_DENIED | 403 | PERMISSION_DENIED (7) |
| RATE_LIMITED | 429 | RESOURCE_EXHAUSTED (8) |
| UNAVAILABLE | 503 | UNAVAILABLE (14) |
| INTERNAL | 500 | INTERNAL (13) |

## Centralized capture: one filter per transport

Domain and adapter code throws typed errors; exactly one registered handler per transport catches them and produces the response. Requests never serialize errors themselves.

```typescript
@Catch(AppError)                          // register: app.useGlobalFilters(new AppErrorFilter())
export class AppErrorFilter implements ExceptionFilter {
  catch(err: AppError, host: ArgumentsHost) {
    const res = host.switchToHttp().getResponse();
    const { status, body } = toProblem(err);
    res.status(status).type('application/problem+json').json(body);
  }
}
```

```java
@RestControllerAdvice
class AppErrorAdvice {
  @ExceptionHandler(AppException.class)
  ProblemDetail handle(AppException ex) {                 // Spring Boot 3 built-in RFC 9457 type
    ProblemDetail pd = ProblemDetail.forStatusAndDetail(statusFor(ex.kind()), ex.getMessage());
    pd.setType(URI.create("https://errors.example.com/" + ex.kind()));
    pd.setProperty("traceId", Span.current().getSpanContext().getTraceId());
    return pd;       // @RestControllerAdvice serializes it as application/problem+json
  }
}
```

```python
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:        # FastAPI
    status, body = to_problem(exc, instance=str(request.url.path))
    return JSONResponse(status, content=body, media_type="application/problem+json")
app.add_exception_handler(AppError, app_error_handler)
```

```javascript
app.use((err, req, res, next) => {        // Express: 4-arg signature; register LAST, after routes
  const { status, body } = toProblem(err);
  res.status(status).type('application/problem+json').json(body);
});
```

```csharp
builder.Services.AddProblemDetails();
app.UseExceptionHandler();                 // ASP.NET Core (.NET 8+): emits RFC 9457 ProblemDetails

public sealed class AppExceptionHandler : IExceptionHandler {
    public async ValueTask<bool> TryHandleAsync(HttpContext ctx, Exception ex, CancellationToken ct) {
        if (ex is not AppException app) return false;          // let the next handler try
        var (status, problem) = ToProblem(app);
        ctx.Response.StatusCode = status;
        await ctx.Response.WriteAsJsonAsync(problem, "application/problem+json", ct);
        return true;
    }
}
```

## HTTP wire format: RFC 9457 Problem Details

RFC 9457 obsoletes RFC 7807; the media type (`application/problem+json`) and member names are unchanged, so existing 7807 bodies stay valid. Standard members: `type` (a URI identifying the problem class), `title` (stable summary of that type), `status` (the HTTP code, mirrored in the body), `detail` (this-occurrence explanation), `instance` (URI of the specific occurrence). Add extension members freely, such as `errors[]` for field violations and `traceId` for correlation. Select the status from the kind table; a 422 for validation and a 409 for a concurrency conflict beat a blanket 400.

```json
{
  "type": "https://errors.example.com/validation",
  "title": "Request validation failed",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "instance": "/orders/2f9a",
  "errors": [
    { "field": "quantity", "message": "must be >= 1" },
    { "field": "currency", "message": "unsupported value 'XYZ'" }
  ],
  "traceId": "0af7651916cd43dd8448eb211c80319c"
}
```

## gRPC wire format: google.rpc.Status

A gRPC error is a `google.rpc.Status` (`code`, `message`, `details`). The `code` is one of the canonical `grpc/codes` values from the table; `details` is a list of typed protobuf messages: `google.rpc.ErrorInfo` for the stable machine kind, `BadRequest` for field violations, `RetryInfo` to advise backoff. grpc-gateway maps these codes to HTTP with the same table, so one error reaches both transports coherently.

```go
st := status.New(codes.InvalidArgument, "request validation failed")
st, _ = st.WithDetails(
    &errdetails.ErrorInfo{Reason: "VALIDATION", Domain: "orders.example.com"},
    &errdetails.BadRequest{FieldViolations: []*errdetails.BadRequest_FieldViolation{
        {Field: "quantity", Description: "must be >= 1"}}},
    &errdetails.RetryInfo{RetryDelay: durationpb.New(2 * time.Second)},
)
return nil, st.Err()
```

## Other protocols

- GraphQL: failures go in the top-level `errors` array with a stable `extensions.code` (`NOT_FOUND`, `VALIDATION`). The HTTP response for the operation stays 200 even when fields fail; do not overload the transport status to signal a resolver error. Return partial `data` with `null` for the failed path.
- Async/message consumers: model the outcome as a typed result, not an exception escaping the loop. Distinguish retryable (`UNAVAILABLE`, `RATE_LIMITED`) from terminal (`VALIDATION`, `NOT_FOUND`): retry with backoff and a max-attempts cap, then route to a dead-letter queue with the error attached. A poison message must never block the partition.
- CLI: map the kind to a process exit code (0 success, 2 usage/validation, other non-zero per kind) and write structured error output to stderr, keeping stdout for clean program output.

## Rust: thiserror AppError with axum and tonic adapters

The recommended idiomatic pattern. A central enum with `thiserror` 2.x; `#[from]` conversions so `?` lifts infrastructure errors into it. Keep `anyhow` for internal context only and convert at the boundary. Crates: thiserror 2.x, axum 0.8.x, tonic 0.13.x, serde 1.x.

```rust
use thiserror::Error;
use axum::http::StatusCode;
use tonic::Code;

#[derive(Debug, Clone, serde::Serialize)]
pub struct FieldViolation { pub field: String, pub message: String }

#[derive(Debug, Error)]
pub enum AppError {
    #[error("{0} not found")]       NotFound(String),
    #[error("validation failed")]   Validation(Vec<FieldViolation>),
    #[error("conflict: {0}")]       Conflict(String),
    #[error("unauthenticated")]     Unauthenticated,
    #[error("permission denied")]   PermissionDenied,
    #[error("rate limited")]        RateLimited,
    #[error("service unavailable")] Unavailable,
    #[error(transparent)]           Db(#[from] sqlx::Error),         // ? from the data layer
    #[error(transparent)]           Internal(#[from] anyhow::Error), // anyhow stays internal
}

impl AppError {
    // the single mapping table: kind string, HTTP status, gRPC code
    fn meta(&self) -> (&'static str, StatusCode, Code) {
        use AppError::*;
        match self {
            NotFound(_)      => ("not_found", StatusCode::NOT_FOUND, Code::NotFound),
            Validation(_)    => ("validation", StatusCode::UNPROCESSABLE_ENTITY, Code::InvalidArgument),
            Conflict(_)      => ("conflict", StatusCode::CONFLICT, Code::AlreadyExists),
            Unauthenticated  => ("unauthenticated", StatusCode::UNAUTHORIZED, Code::Unauthenticated),
            PermissionDenied => ("permission_denied", StatusCode::FORBIDDEN, Code::PermissionDenied),
            RateLimited      => ("rate_limited", StatusCode::TOO_MANY_REQUESTS, Code::ResourceExhausted),
            Unavailable      => ("unavailable", StatusCode::SERVICE_UNAVAILABLE, Code::Unavailable),
            Db(_) | Internal(_) => ("internal", StatusCode::INTERNAL_SERVER_ERROR, Code::Internal),
        }
    }
}

#[derive(serde::Serialize)]
pub struct ProblemDetails {
    pub r#type: String,
    pub title: String,
    pub status: u16,
    #[serde(skip_serializing_if = "Option::is_none")] pub detail: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]    pub errors: Vec<FieldViolation>,
    pub trace_id: String,
}

impl axum::response::IntoResponse for AppError {
    fn into_response(self) -> axum::response::Response {
        let (kind, status, _) = self.meta();
        if status == StatusCode::INTERNAL_SERVER_ERROR {
            tracing::error!(error = ?self, "unhandled internal error"); // full detail to logs only
        }
        let errors = match &self { AppError::Validation(v) => v.clone(), _ => Vec::new() };
        let detail = (status != StatusCode::INTERNAL_SERVER_ERROR).then(|| self.to_string());
        let body = ProblemDetails {
            r#type: format!("https://errors.example.com/{kind}"),
            title: status.canonical_reason().unwrap_or("Error").into(),
            status: status.as_u16(), detail, errors,
            trace_id: current_trace_id(),                 // from the active tracing span
        };
        (status, [(axum::http::header::CONTENT_TYPE, "application/problem+json")],
         axum::Json(body)).into_response()
    }
}

impl From<AppError> for tonic::Status {
    fn from(err: AppError) -> Self {
        let (_, _, code) = err.meta();
        let msg = if code == Code::Internal { "internal error".into() } else { err.to_string() };
        tonic::Status::new(code, msg)
    }
}
```

## Go: Error struct with WriteProblem and a gRPC interceptor

A custom error type carrying `Kind`, message, and a wrapped cause; classify via `errors.As`, never by string-matching the message.

```go
package apperr

import (
    "errors"
    "fmt"
)

type Kind int

const (
    Internal Kind = iota
    NotFound
    Validation
    Conflict
    Unauthenticated
    PermissionDenied
    RateLimited
    Unavailable
)

func (k Kind) String() string {
    return [...]string{"internal", "not_found", "validation", "conflict",
        "unauthenticated", "permission_denied", "rate_limited", "unavailable"}[k]
}

type Error struct {
    Kind Kind
    Msg  string
    Err  error // wrapped cause; stays server-side
}

func (e *Error) Error() string {
    if e.Err != nil { return fmt.Sprintf("%s: %v", e.Msg, e.Err) }
    return e.Msg
}
func (e *Error) Unwrap() error { return e.Err }

func New(kind Kind, msg string) *Error               { return &Error{Kind: kind, Msg: msg} }
func Wrap(kind Kind, msg string, cause error) *Error { return &Error{Kind: kind, Msg: msg, Err: cause} }

func KindOf(err error) Kind { // classify any error; default Internal
    var e *Error
    if errors.As(err, &e) { return e.Kind }
    return Internal
}
```

```go
var httpStatus = map[apperr.Kind]int{
    apperr.NotFound: 404, apperr.Validation: 422, apperr.Conflict: 409,
    apperr.Unauthenticated: 401, apperr.PermissionDenied: 403, apperr.RateLimited: 429,
    apperr.Unavailable: 503, apperr.Internal: 500,
}
var grpcCode = map[apperr.Kind]codes.Code{
    apperr.NotFound: codes.NotFound, apperr.Validation: codes.InvalidArgument,
    apperr.Conflict: codes.AlreadyExists, apperr.Unauthenticated: codes.Unauthenticated,
    apperr.PermissionDenied: codes.PermissionDenied, apperr.RateLimited: codes.ResourceExhausted,
    apperr.Unavailable: codes.Unavailable, apperr.Internal: codes.Internal,
}

type problem struct {
    Type    string `json:"type"`
    Title   string `json:"title"`
    Status  int    `json:"status"`
    Detail  string `json:"detail,omitempty"`
    TraceID string `json:"traceId,omitempty"`
}

func WriteProblem(w http.ResponseWriter, r *http.Request, err error) {
    kind := apperr.KindOf(err)
    status := httpStatus[kind]
    detail := err.Error()
    if status >= 500 {
        log.Error().Err(err).Msg("internal error") // full detail to logs only
        detail = "An internal error occurred."      // sanitized for the client
    }
    w.Header().Set("Content-Type", "application/problem+json")
    w.WriteHeader(status)
    _ = json.NewEncoder(w).Encode(problem{
        Type:    "https://errors.example.com/" + kind.String(),
        Title:   http.StatusText(status),
        Status:  status,
        Detail:  detail,
        TraceID: traceIDFromContext(r.Context()),
    })
}

func ErrorInterceptor(ctx context.Context, req any, _ *grpc.UnaryServerInfo,
    handler grpc.UnaryHandler) (any, error) {
    resp, err := handler(ctx, req)
    if err == nil { return resp, nil }
    code := grpcCode[apperr.KindOf(err)]
    msg := err.Error()
    if code == codes.Internal { msg = "internal error" } // already logged/recorded on the span
    return nil, status.New(code, msg).Err()
}
```

## Security and observability

The boundary handler is the only place that decides what a client may see. Never return stack traces, internal hostnames, SQL, driver text, or secrets. For any 5xx, replace the cause with a generic detail and attach a correlation id, then log the full error and its chain server-side. Put the trace id in the response as `instance` or a `traceId` extension member so the client report ties back to your logs. Record the error on the active span (`span.record_exception(...)`, set span status to error) so the trace id in the response correlates with the trace and the log line. See the observability agent for span and OpenTelemetry setup.

## Common pitfalls

- Building error JSON inline in route handlers, so the shape drifts per endpoint. Route every failure through the one filter.
- Putting an HTTP status or gRPC code inside the domain error, coupling the core to a transport. Status lives only in the boundary mapping.
- Returning the raw exception message or stack for 5xx, leaking internals. Sanitize, and log the detail instead.
- A catch-all mapping every error to 500, erasing NOT_FOUND, VALIDATION, and CONFLICT. Classify by kind.
- Treating RFC 9457 as new and incompatible; it obsoletes 7807 with the same media type and members, so old bodies stay valid.
- Overloading the GraphQL HTTP status to signal a resolver failure; the operation returns 200 with the error in `errors[]`.
- gRPC errors as a bare `INTERNAL` with no `ErrorInfo`/`BadRequest` details, leaving clients unable to react.
- Classifying errors by string-matching the message instead of `errors.As`/`#[from]`/a typed kind.
- A response carrying a trace id that was never recorded on the span, so it correlates with nothing.
- Async consumers that retry terminal errors forever or dead-letter retryable ones; split retryable from terminal explicitly.

## Definition of done

- [ ] A single protocol-agnostic error model carries a stable `kind`, message, optional field-violation details, and a cause chain; no transport status appears inside it.
- [ ] One mapping table translates kind to {HTTP status, gRPC code} and is the only place statuses are decided.
- [ ] Every transport has exactly one centralized handler (filter/advice/middleware/interceptor); no handler serializes an error inline.
- [ ] HTTP errors are `application/problem+json` per RFC 9457 with correct `type`/`title`/`status`/`detail`/`instance` and a `traceId` extension; status is selected per kind.
- [ ] gRPC errors use the canonical code plus `ErrorInfo`/`BadRequest`/`RetryInfo` details; HTTP and gRPC stay consistent via the shared table.
- [ ] GraphQL keeps HTTP 200 and reports in `errors[]` with `extensions.code`; async consumers split retryable from terminal with a dead-letter path; CLI sets exit codes and structured stderr.
- [ ] Rust uses a `thiserror` `AppError` with `#[from]` conversions, an axum `IntoResponse` emitting `ProblemDetails`, and a `tonic::Status` adapter; anyhow context is converted at the boundary.
- [ ] Go uses an `Error` struct with `Unwrap`, `errors.As`-based classification, a `WriteProblem` HTTP helper, and a unary interceptor mapping kind to `codes.Code`.
- [ ] 5xx responses are sanitized; full detail is logged server-side; the response trace id is recorded on the active span.
- [ ] Tests cover each kind's status/code mapping, sanitization of internal errors, and that no handler builds a response outside the central path, with external services mocked.
