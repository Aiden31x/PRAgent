# Go Code Review Checklist

## Error Handling

- Every error return value must be checked — never assign to `_` unless explicitly intentional and documented.
- Wrap errors with context using `fmt.Errorf("doing X: %w", err)` or `errors.New`; avoid bare `return err` in deep call stacks.
- Use `errors.Is` / `errors.As` for sentinel and typed error comparisons; do not compare error strings directly.
- Prefer returning early on error over deeply nested `if err == nil` success paths.
- `defer` calls that can fail (e.g. `rows.Close()`, `resp.Body.Close()`) should log or surface the error — silently discarding is a bug.

## Concurrency & Goroutines

- Every goroutine must have a clear ownership and lifetime. Unstructured `go func()` spawning without a `WaitGroup`, `errgroup`, or context-based cancellation is a leak risk.
- Shared mutable state accessed from multiple goroutines must be protected — `sync.Mutex`, `sync.RWMutex`, or channel-based ownership.
- Channel operations that can block indefinitely should use a `select` with a context cancel or timeout arm.
- Avoid `time.Sleep` as a synchronisation primitive; prefer channels or `sync.WaitGroup`.
- `sync.WaitGroup.Add` must be called **before** the goroutine is spawned; calling `Add` inside the goroutine is a race.

## Resource Management

- HTTP response bodies must be read fully (`io.Discard`) or at least closed; otherwise the underlying TCP connection is not returned to the pool.
- Database `*sql.Rows` must always be closed and the `rows.Err()` checked after the loop.
- `context.WithCancel` / `WithTimeout` — the returned `CancelFunc` must be deferred immediately; forgetting it leaks resources even if the context expires.
- File handles opened with `os.Open` / `os.Create` must be closed with `defer f.Close()`.

## Package & Dependency Design

- Package names should be short, lowercase, single words — no `util`, `common`, or `helpers` mega-packages.
- Unexported identifiers are package-private by default; do not export types that are only used internally.
- Circular imports are a compile error — they usually indicate a need to extract a shared interface package.
- Prefer `internal/` packages to enforce access boundaries within a module.

## Interface & Type Design

- Interfaces should be defined at the point of **use** (consumer), not at the point of implementation (producer).
- Keep interfaces small — the `io.Reader` / `io.Writer` pattern is idiomatic. Large interfaces are hard to mock and hard to satisfy.
- Avoid empty interface (`interface{}` / `any`) in public API; use concrete types or typed generics (Go 1.18+).
- Struct embedding should be used for code reuse, not for simulating inheritance; be explicit about which methods are promoted.

## Performance

- Avoid unnecessary allocations in hot paths: pre-size slices with `make([]T, 0, n)` when capacity is known, and maps with `make(map[K]V, n)`.
- String concatenation in a loop should use `strings.Builder`, not `+=`.
- Large structs passed as function arguments should use pointers to avoid copying unless immutability is important.
- Profile before optimising — use `pprof` benchmarks rather than guessing.
- `sync.Pool` can amortise allocation cost for short-lived objects, but only after profiling confirms it is needed.

## Testing

- Table-driven tests are idiomatic — use `t.Run(tc.name, ...)` sub-tests for clear failure messages.
- Use `t.Parallel()` in independent sub-tests to speed up the suite.
- External dependencies (HTTP, DB) should be abstracted behind interfaces and mocked in unit tests; use `httptest.Server` for HTTP.
- `testify/assert` vs `testify/require` — use `require` when the test cannot continue if the assertion fails.
- Benchmark functions (`BenchmarkXxx`) should call `b.ResetTimer()` after setup and use `b.RunParallel` where appropriate.

## Security

- Never log sensitive data (tokens, passwords, PII) — even at `DEBUG` level.
- SQL queries must use parameterised statements (`db.QueryContext(ctx, "SELECT ... WHERE id = ?", id)`); never interpolate user input.
- HTTP handlers must validate and sanitise all input; use `net/http` middleware for auth, not ad-hoc checks inside handlers.
- Cryptographic operations must use `crypto/rand`, never `math/rand`, for secret generation.
- Outbound HTTP clients should set timeouts (`http.Client{Timeout: ...}`); the default zero timeout means no deadline.

## Code Style

- `gofmt` / `goimports` compliance is non-negotiable; CI should enforce it.
- Variable names should be short in small scopes (`i`, `n`, `err`) and descriptive in larger ones.
- Avoid `else` after a `return` — it adds nesting for no benefit.
- Exported symbols must have GoDoc comments; unexported symbols benefit from comments on non-obvious logic.
- Magic numbers should be named constants (`const maxRetries = 3`).
