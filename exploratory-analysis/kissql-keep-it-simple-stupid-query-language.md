---
description: >-
  KISSQL (pronounced kiss-Q-L) is a tiny, human-friendly search syntax that lets
  you mix natural-language keywords with power-user filters in a single line
cover: ../.gitbook/assets/KISSQL (1).png
coverY: 0
---

# KISSQL – Keep-It-Simple,Stupid! Query Language

KISSQL (pronounced kiss-Q-L) is a tiny, human-friendly search syntax that lets you mix natural-language keywords with power-user filters in a single line, no brackets, no JSON.

KISSQL is designed for searching and filtering articles in the AunooAI semantic topicmap store. The grammar is deliberately minimal so you can type queries straight into a search box without memorizing a full SQL dialect.

***

### Language Overview

KISSQL draws inspiration from search syntaxes such as Lucene and SQL while deliberately staying lightweight and friendly.

A query is composed of up to three ordered parts:

1. Free-text – plain words and quoted phrases that are matched through vector or keyword search.
2. Constraints – structured filters written as simple expressions (field = value, Score > 10, has:tag).
3. Post-filters (pipe operators) – result-trimming commands (| HEAD 100) that run after ranking.



The grammar is intentionally minimal:

| Category       | Syntax examples                      |
| -------------- | ------------------------------------ |
| Logic          | AND OR NOT                           |
| Comparison     | = != > >= < <=                       |
| Range          | field = 10..20                       |
| Existence      | has:field                            |
| Set / In-list  | in(a,b,c)                            |
| Meta controls  | sort:field:desc   limit:50 cluster=3 |
| Enhancement    | ^3 (boost)   "exact phrase"          |
| Pipe operators | \`                                   |

Parsing is whitespace-insensitive (except inside quotes).  Order of evaluation is:

| text search  ➜  constraints  ➜  ranking  ➜  pipe operators |
| ---------------------------------------------------------- |

This keeps the mental model simple – pipes never influence scoring, they only trim the final ranked list.\
Below you will find full operator tables, meta controls and examples.

### Operators

#### Basic Operators

* \= / equal - equality (same as)
* != / not equal - inequality (different from)
* \> >= < <= - comparison operators

#### Logic Operators

* AND - all terms must match
* OR - any term can match
* NOT - exclude following term

#### Set Operations

* in(a,b,c) - field value must be in the given set
* has:field - field must exist
* field=min..max - range operation (inclusive)

#### Pipe Operators

| Operator   | Purpose                           | Default |
| ---------- | --------------------------------- | ------- |
| `HEAD n`   | Keep only the first n results     | N = 100 |
| `TAIL n`   | Keep only the last n results      | N = 100 |
| `SAMPLE n` | Keep a random sample of n results | -       |

Pipe operators are executed after all filtering and ranking. They are chainable, e.g.:

`"artificial intelligence" | HEAD 500 | SAMPLE 50`

The above returns a random sample of 50 from the first 500 results.

### Meta Controls

* `sort:field[:asc|desc]` - sort results by field, e.g., sort:publication\_date:desc
* `limit:n` - cap number of results, e.g., limit:50
* `similar:id` - find items similar to given id, e.g., similar:abc123
* `cluster=n` - restrict to cluster, e.g., cluster=4

### Enhancement

* `^n` - boost term weight, e.g., AI^3
* `"exact phrase"` - exact match, e.g., "artificial intelligence"
* `"near phrase"~5` - proximity, e.g., "climate change"\~3 (parsing only)

<figure><img src="../.gitbook/assets/image (16).png" alt=""><figcaption></figcaption></figure>

### Examples

1. Simple search:

| `artificial intelligence` |
| ------------------------- |



2. Search with filter:

| `AI AND category="AI Business" sentiment=Positive` |
| -------------------------------------------------- |



3. Search with advanced filters:

| `AI NOT Google has:driver_type Score>=1.0` |
| ------------------------------------------ |



4. Search with meta controls:

| `AI sort:publication_date:desc limit:50` |
| ---------------------------------------- |



5. Pipe operator:

| `AGI \| HEAD 20 \| TAIL 5` |
| -------------------------- |

### Usage in Code

| <p><code>from app.kissql.parser import parse_query, parse_full_query</code><br><br><code># Basic usage (compatible with existing code)</code><br><br><code>cleaned_text, metadata, extra = parse_query("AI AND category=business")</code><br><br><code># Full structured query</code><br><br><code>query = parse_full_query("AI AND category=business")</code><br><br><code>print(query.text)  # "AI AND"</code><br><br><code>print(query.constraints)  # [Constraint(field='category', operator='=', value='business')</code>]</p> |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |

### Execution

The executor module provides functionality to execute parsed queries:

| <p><code>from app.kissql.parser import parse_full_query</code><br><br><code>from app.kissql.executor import execute_query</code><br><br><code>query = parse_full_query("AI AND category=business")</code><br><br><code>results = execute_query(query, top_k=100)</code></p> |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |



### 1.  Quick Reference

\#         ───── free-text terms ─────        ── filters ──      ─ meta ─<br>

vector databases agi category="AI" sentiment!=negative sort:publication\_date:desc limit:200<br>

| Feature                   | Syntax                          | Example                               |
| ------------------------- | ------------------------------- | ------------------------------------- |
| Equality                  | field = value                   | category="AI Business"                |
| Inequality                | != or <>                        | sentiment!=negative                   |
| Numeric / date compare    | >  >=  <  <=                    | score>=0.9  publication\_date<2024-01 |
| Range (inclusive)         | a..b                            | score=0.7..1                          |
| Starts / ends / contains  | ^=  $=  \~=                     | title^="The" · url$=".pdf"            |
| Set membership            | in(val1,val2,…)                 | topic in(GenAI,LLM,RAG)               |
| Existence / missing       | has:field  !has:field           | has:summary                           |
| Boost term / field weight | term^n  field^n=value           | vector^2.5 · category^3="AI"          |
| Phrase search             | "exact words"                   | "foundation model"                    |
| Proximity (≤ k words)     | "words"\~k                      | "open source"\~5                      |
| Logical operators         | AND  OR  NOT (case-insensitive) | ai AND hardware NOT gpu               |
| Sort results              | \`sort:field\[:asc] \[desc]     | <p>sort:publication_date:desc<br></p> |
| Per-page / hard limit     | limit:n                         | limit:50                              |
| Semantic neighbours       | similar:id                      | similar:abc123                        |
| Cluster filter            | cluster=n                       | cluster=7                             |



Everything not recognised as a filter is treated as free-text and matched with vector or keyword search depending on the selected mode.

***

### 2.  Full Syntax

#### 2.1  Tokens

query       ::=  (term | filter | meta | logical\_op)\*

term        ::=  bare\_word | quoted\_phrase | proximity

filter      ::=  field operator value

meta        ::=  sort | limit | cluster | similar

logical\_op  ::=  AND | OR | NOT | && | || | !<br>

• Bare words (`vector, rag`) are searched fuzzily. • Quoted phrases keep the order: "`agentic workflows`". • Proximity: `"agentic AI"~3` means ≤3 tokens apart.

#### 2.2  Operators

| Operator | Meaning                    | Notes                        |
| -------- | -------------------------- | ---------------------------- |
| =        | exact match (case-insens.) | quotes optional if no spaces |
| !=  <>   | not equal                  | <p><br></p>                  |
| >  >=    | numeric / ISO-date compare | <p><br></p>                  |
| <  <=    | <p><br></p>                | <p><br></p>                  |
| a..b     | inclusive range            | works for numbers/dates      |
| ^=       | starts with                | string only                  |
| $=       | ends with                  | <p><br></p>                  |
| \~=      | contains substring         | <p><br></p>                  |
| in()     | value is in list           | commas, no spaces            |
| has:     | field exists               | !has: for missing            |

#### 2.3  Boosting

vektor^4          # boost free-text term

category^2="LLM"  # boost documents whose category equals "LLM"

#### 2.4  Meta-directives

sort:score:desc       # primary ordering

limit:500             # override UI limit

similar:xyz           # retrieve nearest neighbours to URI xyz

cluster=4             # restrict to embedding cluster 4

***

### 4.  Implementation Notes

1. The front-end tokeniser strips recognised limit: and sort: before talking to the API; everything else is forwarded as-is.
2. Equality predicates map to metadata filters for ChromaDB.  Advanced operators are currently applied client-side or in further back-end layers.
3. The language intentionally avoids parentheses; use the natural left-to-right evaluation with explicit AND/OR if needed.

***

### 5.  Tips & Tricks

• Put values with spaces in double quotes: news\_source="The Economist".&#x20;

• Combine free-text with filters freely: langchain vector store category=Tools.&#x20;

• Start with broad search, then click facet badges to auto-append filters.

***

Happy querying – and remember: Keep It Simple, Stupid! 😎

