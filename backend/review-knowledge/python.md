# Python Review Checklist

Apply these checks in addition to the core rubric. Each item describes a concrete pitfall
to look for; flag it when you see the bad pattern in the diff.

---

## Mutable Default Arguments

**Flag any function with a mutable default (list, dict, set).**
The mutable object is created once at function definition time and shared across every call.

```python
# BAD — items=[] is the same list object on every call
def add_item(item, items=[]):
    items.append(item)
    return items

add_item(1)  # [1]
add_item(2)  # [1, 2] — not [2] as the caller expects
```

Fix: use `= None` and initialise inside the body, or use `dataclasses.field(default_factory=list)`.

---

## Mutable Class Attributes

**Flag mutable objects declared at class scope, not in `__init__`.**
They are shared across all instances; one instance mutating the list/dict corrupts all others.

```python
# BAD
class User:
    permissions = []   # shared across every User instance

# GOOD
class User:
    def __init__(self):
        self.permissions = []
```

---

## Closure Variable Capture in Loops

**Flag lambdas or nested functions that reference a loop variable without capturing it by value.**

```python
# BAD — all lambdas return the final value of i (2)
funcs = [lambda: i for i in range(3)]
[f() for f in funcs]  # [2, 2, 2]

# GOOD — capture the value at creation time
funcs = [lambda i=i: i for i in range(3)]
```

Also applies to `def` inside a loop that captures the loop variable.

---

## Bare and Overly Broad Except Clauses

**Flag `except:` (no type) and `except Exception: pass`.**
- A bare `except:` swallows `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit`.
- `except Exception: pass` hides all bugs silently.

```python
# BAD
try:
    result = risky()
except:            # catches KeyboardInterrupt!
    pass

except Exception:  # swallows everything silently
    pass

# GOOD
except (ValueError, IOError) as e:
    logger.error("Failed: %s", e)
    raise
```

Always catch the narrowest exception type that makes sense, log it, and either handle it
meaningfully or re-raise.

---

## Missing Exception Chaining

**Flag `raise NewError(...)` inside an except block without `from e`.**
This loses the original traceback, making debugging significantly harder.

```python
# BAD — original APIError stacktrace is gone
except APIError as e:
    raise RuntimeError("API failed")

# GOOD — chain preserves the cause
except APIError as e:
    raise RuntimeError("API failed") from e
```

---

## Blocking Calls Inside Async Functions

**Flag synchronous blocking calls used inside `async def` functions.**
They block the entire event loop, defeating the purpose of async.

Common offenders:
- `time.sleep(n)` → use `await asyncio.sleep(n)`
- `requests.get(url)` → use `aiohttp` or `httpx` with `await`
- `open(path).read()` → use `aiofiles` or `loop.run_in_executor`
- Any `socket` or DB call using a sync driver

```python
# BAD
async def fetch():
    time.sleep(2)          # blocks event loop
    return requests.get(url).text  # sync I/O

# GOOD
async def fetch():
    await asyncio.sleep(2)
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()
```

---

## asyncio.CancelledError Must Be Re-Raised

**Flag any `except` that catches `asyncio.CancelledError` (or the broad `Exception` that
would include it) and does NOT re-raise.**
Swallowing `CancelledError` breaks task cancellation and causes hangs.

```python
# BAD
async def worker():
    try:
        await do_work()
    except Exception:      # traps CancelledError!
        pass

# GOOD
async def worker():
    try:
        await do_work()
    except asyncio.CancelledError:
        await cleanup()
        raise              # always re-raise
    except Exception as e:
        logger.error(e)
```

---

## Missing Type Annotations on Public Functions

**Flag public functions (no leading `_`) that are missing parameter or return type annotations.**
Un-annotated public APIs prevent static analysis from catching type errors at call sites.

```python
# BAD
def process_data(data, count):
    return data[:count]

# GOOD
def process_data(data: str, count: int) -> str:
    return data[:count]
```

Also flag the use of bare `Any` in type annotations — prefer `unknown`-equivalent patterns
using `object` or `Union` with a type guard.

---

## `is` Used for Value Comparison

**Flag `is` used to compare non-singleton values (strings, integers, lists, etc.).**
`is` checks object identity, not equality. Python caches small integers (−5 to 256) and
interned strings, so it can appear to work — but silently breaks on values outside that range.

```python
# BAD
if x is 1000:   # False for some runtimes even when x == 1000
if name is "alice":

# GOOD
if x == 1000:
if name == "alice":
# CORRECT use of `is`: only for None, True, False singletons
if x is None:
```

---

## `__eq__` Without `__hash__`

**Flag classes that define `__eq__` but not `__hash__`.**
In Python 3, defining `__eq__` implicitly sets `__hash__ = None`, making instances
unhashable. This breaks use of instances as dict keys or in sets — often silently at
a distance from the class definition.

```python
# BAD
class Point:
    def __init__(self, x, y):
        self.x, self.y = x, y
    def __eq__(self, other):
        return (self.x, self.y) == (other.x, other.y)
    # __hash__ is now None — Point() can't be put in a set

# GOOD
class Point:
    def __eq__(self, other): ...
    def __hash__(self):
        return hash((self.x, self.y))
```

---

## SQLAlchemy Lazy-Load N+1 in Async Sessions

**Flag loops that access a relationship attribute on ORM objects fetched without eager loading.**
In an async SQLAlchemy session, accessing a lazy relationship outside the original query raises
`MissingGreenlet` or silently fires one SQL per row (N+1).

```python
# BAD — triggers N additional queries (or an error in async context)
users = await session.scalars(select(User))
for user in users:
    print(user.orders)   # lazy load — one query per user

# GOOD — eager load with joinedload or selectinload
stmt = select(User).options(selectinload(User.orders))
users = await session.scalars(stmt)
```

Also flag `relationship()` defined with `lazy="select"` (the default) on models used in
async code — it should be `lazy="raise"` or use explicit eager loading options.

---

## String Concatenation in a Loop

**Flag `result += str(item)` (or `result = result + ...`) inside a loop.**
Each concatenation copies the entire string: O(n²) overall.

```python
# BAD
result = ""
for item in large_list:
    result += str(item)   # O(n²)

# GOOD
result = "".join(str(item) for item in large_list)  # O(n)
```

---

## List Used for Membership Testing

**Flag `if item in large_list` when the list is built once and tested many times.**
List `in` is O(n) per lookup; converting to a set makes it O(1).

```python
# BAD — O(n) per lookup
if user_id in blocked_users_list:

# GOOD — O(1) lookup
blocked_set = set(blocked_users_list)
if user_id in blocked_set:
```

---

## Mock Assertion Typos (Tests)

**Flag `mock.assert_called_once()` or `mock.assert_called_with()` written as attribute
access rather than a call — specifically when the test passes unconditionally.**
`unittest.mock.Mock` auto-creates any attribute access, so a misspelled assertion like
`mock.assert_called_once` (without `()`) silently returns a new Mock object instead of
asserting anything.

```python
# BAD — this is always truthy; the assertion is never checked
mock_fn.assert_called_once    # missing ()

# GOOD
mock_fn.assert_called_once()
mock_fn.assert_called_with(expected_arg)
```

---

## Performance: Avoid `list.insert(0, item)` for Queue-Like Usage

**Flag `list.insert(0, item)` or `list.pop(0)` in hot paths.**
Both are O(n). Use `collections.deque` with `appendleft`/`popleft` (both O(1)) instead.

---

## Review Checklist Summary

- [ ] No mutable default arguments (`list`, `dict`, `set` as defaults)
- [ ] No mutable objects at class scope (moved to `__init__`)
- [ ] Loop closures capture variables by value, not by reference
- [ ] All `except` clauses catch specific types; none are silent
- [ ] `raise NewError from e` preserves exception chain
- [ ] No blocking calls (`time.sleep`, `requests`) inside `async def`
- [ ] `asyncio.CancelledError` is always re-raised
- [ ] Public functions have parameter and return type annotations
- [ ] `is` used only for `None`, `True`, `False` — never for value comparison
- [ ] Every class with `__eq__` also defines `__hash__`
- [ ] SQLAlchemy relationships use eager loading in async context
- [ ] String building in loops uses `"".join(...)` not `+=`
- [ ] Membership tests on large collections use `set`, not `list`
- [ ] Mock assertions in tests are called as methods (not just accessed as attributes)



thats how we make pragents be tested
