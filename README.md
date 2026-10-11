# Agentic Data Analyst with Text-to-SQL and Automated Visualization

Ask questions about a database in plain English. An AI agent understands the
question, inspects the schema, writes SQL, validates it (read-only), executes
it, fixes its own mistakes, charts the result, and explains it in simple
language.

**Natural Language -> Understand -> Generate SQL -> Validate -> Execute ->
Analyze -> Visualize -> Explain**

## Why this is an agent, not a plain SQL generator

- **Multi-step loop with tools and decisions**, orchestrated by LangGraph.
- **Self-correction:** if the SQL fails validation or the database returns an
  error (e.g. column `product` does not exist), the agent reads the error,
  rewrites the query and retries - up to 3 attempts.
- **Follow-up memory:** "Show it as a pie chart" refers to the previous
  result; the backend keeps per-conversation history.
- **Values always come from the database.** The explanation step is told to
  use only the returned rows, never invented numbers.

## Architecture

```mermaid
flowchart LR
    U[Streamlit UI] -->|POST /ask| API[FastAPI backend]
    API --> G[LangGraph agent]
    subgraph G[LangGraph agent]
        A[understand] --> S[fetch schema] --> Q[generate SQL] --> V[validate read-only]
        V -->|ok| E[execute on PostgreSQL]
        V -->|bad| C[correct SQL]
        E -->|error| C
        C -->|retry, max 3| V
        E -->|rows| N[analyze + explain] --> CH[choose chart]
    end
    E --- DB[(PostgreSQL<br>demo sales data)]
    G --> U
    G -.->|Gemini free tier / Groq| LLM[(LLM API)]
```

| Layer | Tech |
|---|---|
| UI | Streamlit (`ui/streamlit_app.py`) |
| Backend | FastAPI (`app/main.py`) |
| Agent loop | LangGraph + LangChain (`app/agents/`) |
| SQL safety | sqlglot-based read-only validator (`app/sql_validator.py`) |
| Charts | rule-based selection + user override (`app/charts.py`), rendered with Plotly |
| Database | PostgreSQL (local install, `db/`) |
| LLM | Gemini free tier or Groq - keys in `.env` only |

## Database Schema & Entity Relationships

The PostgreSQL database (`sales_db`) follows a star-adjacent relational schema designed for analytics, aggregations, customer segmentation, regional breakdown, and sales representative tracking:

### Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    REGIONS ||--o{ CUSTOMERS : "contains (1:N)"
    REGIONS ||--o{ SALES_REPRESENTATIVES : "assigned (1:N)"
    CUSTOMERS ||--o{ SALES : "places (1:N)"
    PRODUCTS ||--o{ SALES : "sold_in (1:N)"
    SALES_REPRESENTATIVES ||--o{ SALES : "closes (1:N)"

    REGIONS {
        int region_id PK
        text region_name
        text state
    }

    CUSTOMERS {
        int customer_id PK
        text customer_name
        text city
        text segment
        int region_id FK
    }

    PRODUCTS {
        int product_id PK
        text product_name
        text category
        numeric unit_price
    }

    SALES_REPRESENTATIVES {
        int rep_id PK
        text rep_name
        int region_id FK
    }

    SALES {
        int sale_id PK
        date sale_date
        int customer_id FK
        int product_id FK
        int rep_id FK
        int quantity
        numeric unit_price
        numeric total_amount
    }
```

### Data Flow & Table Details

```mermaid
flowchart TD
    subgraph Dimensions [Dimension Tables]
        R["regions (12 rows)<br>• region_id (PK)<br>• region_name, state"]
        C["customers (22 rows)<br>• customer_id (PK)<br>• customer_name, segment, region_id (FK)"]
        SR["sales_representatives (10 rows)<br>• rep_id (PK)<br>• rep_name, region_id (FK)"]
        P["products (14 rows)<br>• product_id (PK)<br>• product_name, category, unit_price"]
    end

    subgraph Facts [Fact Table]
        S["sales (1,168 rows)<br>• sale_id (PK)<br>• sale_date, quantity, unit_price, total_amount<br>• customer_id (FK), product_id (FK), rep_id (FK)"]
    end

    R -->|1 : N| C
    R -->|1 : N| SR
    C -->|1 : N| S
    SR -->|1 : N| S
    P -->|1 : N| S
```

| Table Name | Type | Rows | Description & Key Columns |
|---|---|---|---|
| `regions` | Dimension | 12 | Geographies and Indian states (e.g., Chennai Metro, Coimbatore, Bengaluru Urban, Mumbai West). |
| `customers` | Dimension | 22 | Retail, wholesale, and corporate buyers mapped to `regions` via `region_id`. |
| `products` | Dimension | 14 | FMCG, Electronics, Groceries, and Home items with `category` and `unit_price`. |
| `sales_representatives` | Dimension | 10 | Sales agents mapped to their primary operating region via `region_id`. |
| `sales` | Fact | 1,168 | Granular daily sales transactions with `sale_date`, `quantity`, `unit_price`, and `total_amount`. |

## Project layout

```
agentic-data-analyst/
├── app/
│   ├── main.py            # FastAPI: /ask, /schema, /health + conversation memory
│   ├── config.py          # settings from .env
│   ├── db.py              # schema introspection + read-only execution
│   ├── llm.py             # Gemini / Groq factory
│   ├── sql_validator.py   # read-only SQL validation (sqlglot)
│   ├── charts.py          # chart-type selection + overrides
│   ├── agents/            # orchestrator, sql_expert, statistician, explorer, report_builder
│   └── tools/             # anomaly detector, forecaster, stats engine, sql tool
├── ui/streamlit_app.py    # chat UI
├── db/schema.sql          # demo schema (5 relational tables)
├── db/seed.py             # sample Indian sales data (deterministic, ~1,200 rows)
├── tests/                 # validator + chart unit tests
├── .env.example           # copy to .env and add your key
└── requirements.txt
```

## Setup (Mac)

Prerequisites: Python 3.10+, PostgreSQL 14+ (create user `ada` / db `sales_db`), and a free LLM API key.

1. **Clone and create a virtualenv**
   ```bash
   git clone https://github.com/Doni1905/agentic-data-analyst.git
   cd agentic-data-analyst
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Get a free LLM key** (one of):
   - Gemini: <https://aistudio.google.com/app/apikey> (default)
   - Groq: <https://console.groq.com/keys> (set `LLM_PROVIDER=groq`)

3. **Configure**
   ```bash
   cp .env.example .env
   # edit .env: paste GOOGLE_API_KEY (or set LLM_PROVIDER=groq + GROQ_API_KEY)
   ```

4. **Start PostgreSQL and seed the demo data**
   ```bash
   # ensure PostgreSQL is running and DATABASE_URL in .env points to it
   python db/seed.py          # ~1200 sales rows, Tamil Nadu / Kerala / ...
   ```

5. **Run the backend and the UI** (two terminals)
   ```bash
   uvicorn app.main:app --reload          # http://localhost:8000/docs
   streamlit run ui/streamlit_app.py      # http://localhost:8501
   ```

6. **Run the tests**
   ```bash
   pytest tests/
   ```

## Example questions

- What were the total sales in Tamil Nadu last year?
- Which product generated the highest revenue?
- Show me the monthly sales trend.
- Which region has the lowest sales?
- Compare sales between Tamil Nadu and Kerala as a bar chart.
- Show it as a pie chart. *(follow-up - reuses the previous result)*

## How the chart is chosen

| Question shape | Chart |
|---|---|
| "trend", "monthly", "over time" | line |
| "compare", "top", "highest", "lowest" | bar |
| "share", "percentage", "breakdown" | pie |
| "relationship between X and Y" | scatter |
| "as a line chart" etc. | your override wins |
| no numeric column / empty result | table |

The UI shows the reason under every chart ("Chart choice: ...").

## Safety

- The validator allows exactly one `SELECT` (or `WITH ... SELECT`).
- `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `CREATE`, `SELECT INTO`,
  filesystem functions, etc. are blocked before execution.
- Table and column names are checked against the real schema.
- Queries run inside a read-only transaction as a second line of defence.
- API keys live only in `.env` (git-ignored). `.env.example` has the shape.

## Scope (v1)

Filtering, grouping, joins, top-N, averages/min/max, date analysis,
comparisons and trends work well. Deeply nested questions may need later
work. React UI and Power BI export are future scope.

## Screenshots

_Add after first run:_

1. Streamlit answering "Which product generated the highest revenue?" with bar chart
2. Monthly sales trend (line chart)
3. A self-correction retry shown in the SQL expander
