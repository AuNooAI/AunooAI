# KISSQL - Keep It Simple, Stupid Query Language

KISSQL is a simple but powerful query language designed for searching and filtering articles in the AunooAI semantic vector store.

## ✅ Implemented Features

- Natural language search with additional filtering capabilities
- Logical operators (AND, OR, NOT)
- Comparison operators (=, !=, >, >=, <, <=)
- Range operations (field=min..max)
- Set operations (has:field, in(a,b,c))
- Meta controls (sort:field[:asc|desc], limit:n, cluster:n, similar:id)
- Enhancement operations (boosting with ^, exact phrase with "")

## 🚧 Partially Implemented Features

- Proximity search with "phrase"~n (parsing implemented, execution needs improvement)

## Operators

### Basic Operators

- `=` / `equal` - equality (same as)
- `!=` / `not equal` - inequality (different from)
- `>` `>=` `<` `<=` - comparison operators

### Logic Operators

- `AND` - all terms must match
- `OR` - any term can match
- `NOT` - exclude following term

### Set Operations

- `in(a,b,c)` - field value must be in the given set
- `has:field` - field must exist
- `field=min..max` - range operation (inclusive)

### Pipe Operators

| Operator | Purpose | Default |
|----------|---------|---------|
| `| HEAD n`    | Keep only the first *n* results | `n = 100` |
| `| TAIL n`    | Keep only the last *n* results  | `n = 100` |
| `| SAMPLE n`  | Keep a random sample of *n* results | – |

Pipe operators are executed after all filtering and ranking. They are chainable, e.g.:

```text
"artificial intelligence" | HEAD 500 | SAMPLE 50
```

The above returns a random sample of 50 from the first 500 results.

## Meta Controls

- `sort:field[:asc|desc]` - sort results by field, e.g., `sort:publication_date:desc`
- `limit:n` - cap number of results, e.g., `limit:50`
- `similar:id` - find items similar to given id, e.g., `similar:abc123`
- `cluster=n` - restrict to cluster, e.g., `cluster=4`

## Enhancement

- `^n` - boost term weight, e.g., `AI^3`
- `"exact phrase"` - exact match, e.g., `"artificial intelligence"`
- `"near phrase"~5` - proximity, e.g., `"climate change"~3` (parsing only)

## Examples

1. Simple search:
   ```
   artificial intelligence
   ```

2. Search with filter:
   ```
   AI AND category="AI Business" sentiment=Positive
   ```

3. Search with advanced filters:
   ```
   AI NOT Google has:driver_type Score>=1.0
   ```

4. Search with meta controls:
   ```
   AI sort:publication_date:desc limit:50
   ```

5. Combining multiple features:
   ```
   "artificial intelligence"^3 AND category="AI Business" NOT price<10 sort:score:desc
   ```

6. Pipe operator:
   ```
   AGI | HEAD 20 | TAIL 5
   ```

## Usage in Code

```python
from app.kissql.parser import parse_query, parse_full_query

# Basic usage (compatible with existing code)
cleaned_text, metadata, extra = parse_query("AI AND category=business")

# Full structured query
query = parse_full_query("AI AND category=business")
print(query.text)  # "AI AND"
print(query.constraints)  # [Constraint(field='category', operator='=', value='business')]
```

## Execution

The `executor` module provides functionality to execute parsed queries:

```python
from app.kissql.parser import parse_full_query
from app.kissql.executor import execute_query

query = parse_full_query("AI AND category=business")
results = execute_query(query, top_k=100)
``` 