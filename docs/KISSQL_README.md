# KISSQL – *Keep-It-Simple Stupid* Query Language

*KISSQL* (pronounced *kiss-Q-L*) is a tiny, human-friendly search syntax
that lets you mix natural-language keywords with power-user filters in a
single line – no brackets, no JSON.

The grammar is deliberately minimal so you can type queries straight into a
search box without memorising a full SQL dialect.

---

## 1.  Quick Reference

```
#         ───── free-text terms ─────        ── filters ──      ─ meta ─
vector databases agi category="AI" sentiment!=negative sort:publication_date:desc limit:200
```

| Feature                     | Syntax                                            | Example                                   |
|-----------------------------|---------------------------------------------------|-------------------------------------------|
| Equality                    | `field = value`                                   | `category="AI Business"`                 |
| Inequality                  | `!=` or `<>`                                      | `sentiment!=negative`                     |
| Numeric / date compare      | `>  >=  <  <=`                                    | `score>=0.9`  `publication_date<2024-01`  |
| Range (inclusive)           | `a..b`                                            | `score=0.7..1`                            |
| Starts / ends / contains    | `^=`  `$=`  `~=`                                  | `title^="The"` · `url$=".pdf"`          |
| Set membership              | `in(val1,val2,…)`                                 | `topic in(GenAI,LLM,RAG)`                 |
| Existence / missing         | `has:field`  `!has:field`                         | `has:summary`                             |
| Boost term / field weight   | `term^n`  `field^n=value`                         | `vector^2.5` · `category^3="AI"`         |
| Phrase search               | `"exact words"`                                  | `"foundation model"`                     |
| Proximity (≤ *k* words)     | `"words"~k`                                      | `"open source"~5`                         |
| Logical operators           | `AND  OR  NOT` (case-insensitive)                 | `ai AND hardware NOT gpu`                 |
| Sort results                | `sort:field[:asc
desc]`                           | `sort:publication_date:desc`              |
| Per-page / hard limit       | `limit:n`                                         | `limit:50`                                |
| Semantic neighbours         | `similar:id`                                      | `similar:abc123`                          |
| Cluster filter              | `cluster=n`                                       | `cluster=7`                               |

Everything not recognised as a filter is treated as free-text and matched
with vector or keyword search depending on the selected mode.

---

## 2.  Full Syntax

### 2.1  Tokens

```
query       ::=  (term | filter | meta | logical_op)*
term        ::=  bare_word | quoted_phrase | proximity
filter      ::=  field operator value
meta        ::=  sort | limit | cluster | similar
logical_op  ::=  AND | OR | NOT | && | || | !
```

• *Bare words* (`vector`, `rag`) are searched fuzzily.
• *Quoted phrases* keep the order: `"agentic workflows"`.
• *Proximity*: `"agentic AI"~3` means ≤3 tokens apart.

### 2.2  Operators

| Operator | Meaning                    | Notes                    |
|----------|---------------------------|--------------------------|
| =        | exact match (case-insens.) | quotes optional if no spaces |
| !=  <>   | not equal                 |                          |
| >  >=    | numeric / ISO-date compare|                          |
| <  <=    |                            |                          |
| a..b     | inclusive range           | works for numbers/dates  |
| ^=       | starts with               | string only             |
| $=       | ends with                 |                          |
| ~=       | contains substring        |                          |
| in()     | value is in list          | commas, no spaces        |
| has:     | field exists              | `!has:` for missing      |

### 2.3  Boosting

```
vektor^4          # boost free-text term
category^2="LLM"  # boost documents whose category equals "LLM"
```

### 2.4  Meta-directives

```
sort:score:desc       # primary ordering
limit:500             # override UI limit
similar:xyz           # retrieve nearest neighbours to URI xyz
cluster=4             # restrict to embedding cluster 4
```

---

## 3.  Examples

```kissql
# sentiment analysis on open-source LLMs published this year
llm open-source sentiment!=negative publication_date>=2024-01-01

# top financial news, recent first, 100 per page
finance category="Finance" sort:publication_date:desc limit:100

# phrase + facet filters
"foundation model" topic="AI and Machine Learning" sentiment=positive

# nearest neighbours to an article
similar:https://example.com/article/123

# visualise only cluster 12
cluster=12
```

---

## 4.  Implementation Notes

1. The front-end tokeniser strips recognised `limit:` and `sort:` before
talking to the API; everything else is forwarded as-is.
2. Equality predicates map to metadata filters for ChromaDB.  Advanced
   operators are currently applied client-side or in further back-end
   layers.
3. The language intentionally avoids parentheses; use the natural left-to-right
   evaluation with explicit `AND`/`OR` if needed.

---

## 5.  Tips & Tricks

• Put values with spaces in double quotes: `news_source="The Economist"`.
• Combine free-text with filters freely: `langchain vector store category=Tools`.
• Start with broad search, then click facet badges to auto-append filters.

---

Happy querying – and remember: *Keep It Simple, Stupid!* 😎 