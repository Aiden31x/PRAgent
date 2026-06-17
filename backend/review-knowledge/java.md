# Java Review Checklist

Apply these checks in addition to the core rubric. Each item describes a concrete pitfall
to look for in Java code; flag it when you see the bad pattern in the diff.

---

## Optional Misuse

**Flag `Optional.get()` called without a preceding `isPresent()` or `ifPresent()` check.**
This throws `NoSuchElementException` at runtime — functionally equivalent to a null dereference.

```java
// BAD
Optional<User> user = repo.findById(id);
return user.get().getName();   // NoSuchElementException if empty

// GOOD — use the functional API
return repo.findById(id)
    .map(User::getName)
    .orElse("Unknown");

// GOOD — or throw a domain exception
return repo.findById(id)
    .orElseThrow(() -> new UserNotFoundException(id));
```

**Also flag `Optional` used as a method parameter or as a field type.**
`Optional` is designed for return values only. Using it as a parameter forces callers to
wrap values needlessly; as a field it causes serialization problems.

```java
// BAD
public void process(Optional<String> name) { ... }
private Optional<String> email;   // field

// GOOD
public void process(String name) { ... }  // use @Nullable or overloads
private String email;                     // nullable field, document with @Nullable
```

---

## Field Injection (`@Autowired` on Fields)

**Flag `@Autowired` applied directly to fields in Spring beans.**
Field injection makes the class harder to unit-test (requires reflection or a Spring context
to inject), hides how many dependencies a class has, and prevents fields from being `final`.

```java
// BAD
@Service
public class UserService {
    @Autowired
    private UserRepository repo;   // hard to test, non-final
}

// GOOD — constructor injection
@Service
public class UserService {
    private final UserRepository repo;

    public UserService(UserRepository repo) {
        this.repo = repo;
    }
}
// With Lombok: @RequiredArgsConstructor on the class + private final fields
```

---

## `@Transactional` on Private Methods

**Flag `@Transactional` placed on a `private` method.**
Spring's AOP proxy only intercepts public method calls made from outside the bean. A
`@Transactional` annotation on a private method is silently ignored — no transaction is started.

```java
// BAD — transaction annotation is ignored
@Transactional
private void saveInternal(Order order) { ... }

// GOOD — make it package-private or public, or restructure
@Transactional
public void save(Order order) { ... }
```

**Also flag missing `readOnly = true` on query-only transaction methods.**
`@Transactional(readOnly = true)` tells the database driver to skip dirty-checking and
can improve performance significantly.

```java
// BAD
@Transactional
public User getUser(Long id) { return repo.findById(id).orElseThrow(); }

// GOOD
@Transactional(readOnly = true)
public User getUser(Long id) { return repo.findById(id).orElseThrow(); }
```

---

## JPA N+1 Queries

**Flag loops or stream operations that access a lazy-loaded collection on entities fetched
without an explicit JOIN or eager-load directive.**
This produces one SQL query per entity row — N+1 total queries — which destroys performance
at scale.

```java
// BAD — triggers N additional SELECT statements for orders
List<User> users = userRepo.findAll();   // 1 query
for (User u : users) {
    System.out.println(u.getOrders().size());  // 1 query each
}

// GOOD — use JOIN FETCH or @EntityGraph to load in one query
@Query("SELECT u FROM User u JOIN FETCH u.orders")
List<User> findAllWithOrders();

// Or with @EntityGraph
@EntityGraph(attributePaths = {"orders"})
List<User> findAll();
```

**Also flag `@OneToMany(fetch = FetchType.EAGER)` on collections** — EAGER fetching on
collections often causes Cartesian product joins and unpredictable performance.

---

## `@Data` on JPA Entities

**Flag Lombok `@Data` on `@Entity` classes.**
`@Data` generates `equals()` and `hashCode()` including all fields. For JPA entities this
causes two problems:
1. Accessing any field in `equals`/`hashCode` can trigger a lazy load.
2. Hibernate uses `equals`/`hashCode` to track entities in its first-level cache — having
   them depend on mutable fields leads to subtle bugs when fields change during the session.

```java
// BAD
@Entity
@Data
public class User { ... }

// GOOD — use only @Getter/@Setter; define equals/hashCode based on ID only
@Entity
@Getter
@Setter
public class User {
    @Id private Long id;

    @Override
    public boolean equals(Object o) {
        if (!(o instanceof User)) return false;
        return id != null && id.equals(((User) o).id);
    }

    @Override
    public int hashCode() {
        return getClass().hashCode();  // constant — safe before id is assigned
    }
}
```

---

## `SimpleDateFormat` Is Not Thread-Safe

**Flag `SimpleDateFormat` stored as a `static` field or shared instance.**
`SimpleDateFormat` maintains mutable parse/format state; concurrent use corrupts results.

```java
// BAD
private static final SimpleDateFormat SDF = new SimpleDateFormat("yyyy-MM-dd");

// GOOD — DateTimeFormatter is immutable and thread-safe (Java 8+)
private static final DateTimeFormatter DTF = DateTimeFormatter.ofPattern("yyyy-MM-dd");
```

---

## `HashMap` in a Multi-Threaded Context

**Flag `HashMap` (or `HashSet`, `ArrayList`) used as a shared mutable field in a bean
or static context that is accessed from multiple threads.**
`HashMap` is not thread-safe; concurrent modification can cause infinite loops (Java 7) or
data loss.

```java
// BAD
private final Map<String, User> cache = new HashMap<>();  // shared, multi-threaded

// GOOD
private final Map<String, User> cache = new ConcurrentHashMap<>();
```

---

## Catching `Throwable` or `Exception` Too Broadly

**Flag catch blocks that catch `Throwable`, `Error`, or `Exception` without a compelling
documented reason.**
- Catching `Error` traps `OutOfMemoryError`, `StackOverflowError` — rarely recoverable.
- Catching `Exception` in service or repository layers silently absorbs checked exceptions
  that callers need to handle.

```java
// BAD
try {
    userService.create(user);
} catch (Exception e) {
    e.printStackTrace();   // swallowed; caller doesn't know it failed
    return null;
}

// GOOD — catch specific, throw domain exceptions
try {
    userService.create(user);
} catch (DataIntegrityViolationException e) {
    throw new DuplicateUserException(user.getEmail(), e);
}
```

---

## `System.out.println` in Production Code

**Flag any `System.out.println`, `System.err.println`, or `e.printStackTrace()` in
non-test source files.**
These bypass your logging framework's level filtering, formatting, and routing. They cannot
be turned off without recompilation.

```java
// BAD
System.out.println("Processing user: " + userId);
e.printStackTrace();

// GOOD
log.info("Processing user: {}", userId);
log.error("Failed to process user {}", userId, e);
```

Use `@Slf4j` (Lombok) or `LoggerFactory.getLogger(getClass())`.

---

## String Comparison with `==`

**Flag `==` or `!=` used to compare `String` objects.**
`==` compares object references, not content. String literals may be interned by the JVM
and appear to work, but dynamically constructed strings will not match.

```java
// BAD
if (status == "active") { ... }
if (response.getStatus() != "OK") { ... }

// GOOD
if ("active".equals(status)) { ... }       // null-safe pattern
if (!"OK".equals(response.getStatus())) { ... }
```

---

## Hardcoded Configuration Values

**Flag secret keys, URLs, or environment-specific values hardcoded in source files.**
These leak into version control and make environment-specific deployment impossible without
recompilation.

```java
// BAD
private String apiKey = "sk_live_abc123";
private String dbUrl  = "jdbc:postgresql://prod-db:5432/mydb";

// GOOD — externalise via @ConfigurationProperties
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(String apiKey, int timeout) {}
```

---

## Unclosed Resources

**Flag I/O resources (`InputStream`, `Connection`, `PreparedStatement`, `ResultSet`,
`HttpClient`, etc.) that are opened but not closed in a `finally` block or try-with-resources.**
A resource leak can exhaust file descriptors or connection pool slots under load.

```java
// BAD
Connection conn = dataSource.getConnection();
PreparedStatement ps = conn.prepareStatement(sql);
// ... if an exception occurs, conn and ps are never closed

// GOOD — try-with-resources guarantees close() on exit
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(sql)) {
    // ...
}
```

---

## Missing Null Checks Before Method Calls

**Flag method calls on values that may be `null` without a preceding null check**, especially:
- Return values of repository methods that don't return `Optional`
- Method parameters that accept `Object` or are not annotated `@NonNull`
- Values deserialized from external input (JSON, form data)

---

## `@Builder` Without Required Field Validation

**Flag Lombok `@Builder` on classes with required fields that lack validation.**
`@Builder` allows the caller to omit any field silently; the object is created in an
invalid state with no compile-time error.

```java
// BAD — id can be omitted: Order.builder().note("hi").build()
@Builder
public class Order {
    private String id;    // required, but builder allows skipping it
    private String note;
}

// GOOD — validate in a compact constructor (record) or @Builder post-processing
@Builder
public class Order {
    private final String id;
    private final String note;

    // Custom static factory that enforces required fields
    public static Order of(String id) {
        return Order.builder().id(Objects.requireNonNull(id, "id required")).build();
    }
}
```

---

## Review Checklist Summary

- [ ] `Optional.get()` never called without a presence check; `Optional` not used as parameter/field
- [ ] Constructor injection used instead of `@Autowired` field injection
- [ ] `@Transactional` only on public methods; read-only queries use `readOnly = true`
- [ ] No N+1 queries (loop accessing lazy collection); EAGER fetch on collections is flagged
- [ ] `@Data` not on `@Entity` classes; entities have ID-based `equals`/`hashCode`
- [ ] `SimpleDateFormat` not shared; use `DateTimeFormatter`
- [ ] Shared mutable maps/sets use concurrent variants (`ConcurrentHashMap`)
- [ ] `Exception`/`Throwable` not caught broadly without justification
- [ ] No `System.out.println` or `e.printStackTrace()` in production code
- [ ] Strings compared with `.equals()`, not `==`
- [ ] No hardcoded secrets or environment-specific URLs
- [ ] All I/O resources use try-with-resources
- [ ] `@Builder` classes with required fields validate them




these are testing changes for the pr agent 