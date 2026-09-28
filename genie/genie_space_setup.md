# Step 4 · APDI Genie space

How to attach Databricks AI/BI Genie to the curated `explore` tables so anyone can ask questions like
*"What agents have healthcare customers built for testing?"* in plain language.

Menu names below match the Genie UI at the time of writing and may differ slightly in your workspace.

## 1. Prerequisites

| What | Why |
|---|---|
| The APDI job has run at least once (see the [README](../README.md)) | Creates and fills `<catalog>.explore` |
| A **Pro or Serverless SQL warehouse** | Genie runs its SQL on it. Serverless starts fastest |
| Grants for the people who will use the space (below) | Genie answers only from data the user can read |

```sql
-- Give business users the curated layer only. The raw_* schemas stay with the data team.
GRANT USE CATALOG ON CATALOG apdi TO `apdi-users`;
GRANT USE SCHEMA, SELECT ON SCHEMA apdi.explore TO `apdi-users`;
```

Users also need **CAN USE** on the SQL warehouse and at least **CAN RUN** on the Genie space.

## 2. Create the space

1. In the workspace sidebar open **Genie**, then **New**.
2. Pick the SQL warehouse.
3. Add tables from `apdi.explore`. Start with the core set, then add the rest if people ask about them:

   | Core (add first) | Add when needed |
   |---|---|
   | `artifact_catalog`: start here, every artifact with labels | `executions` |
   | `artifact_labels` | `llm_usage_daily` |
   | `agents` | `mcp_tool_usage_daily` |
   | `workflows` | `quality_scores` |
   | `tools` | `user_feedback` |
   | `knowledge_bases` | `processes`, `process_nodes` |
   | `mcp_servers`, `mcp_tools` | `guardrails`, `agent_guardrails` |
   | `workflow_agents`, `agent_tools`, `agent_knowledge_bases` | `integrations`, `org_hierarchy` |
   | `search_queries` | |

   Do **not** add `explore.artifact_text`. It is long raw text for later NLP work.
4. Name it **APDI – Agent Pattern Discovery**, and add a short description such as
   "Ask what customers build on the platform: agents, workflows, tools and knowledge bases by industry,
   business unit, tech stack and SDLC phase."

## 3. General instructions

Paste this into **Configure > Instructions > Text**:

```text
You answer questions about what customers build and run on our agentic AI platform (built on crewAI).
Artifacts are: AGENT (a crewAI agent), WORKFLOW (a crew / pipeline of agents run in order), TOOL (a
platform tool an agent calls), MCP_SERVER and MCP_TOOL (Model Context Protocol integrations),
KNOWLEDGE_BASE (a RAG document collection), GUARDRAIL and PROCESS (a Process Studio business process).

Table choice
- Start with explore.artifact_catalog for any question about what exists, by industry, SDLC phase,
  tech stack, business function or archetype. It has one row per artifact and the labels as arrays.
- Use explore.agents / workflows / tools / knowledge_bases for type-specific detail (role, goal,
  model, agent chain, parameters, files).
- Use explore.executions, llm_usage_daily and mcp_tool_usage_daily for usage, cost and failures.
- Use explore.search_queries for demand: is_zero_result = true means users searched and found nothing.
- Use explore.artifact_labels to explain why an artifact has a label (matched_keyword).

Filtering labels
- Label columns are arrays. Filter with array_contains(col, 'Label'). To count per label use
  LATERAL VIEW explode(col). Label values are case-sensitive and must match the list below.
- "Industry" means the artifact_catalog.industries column. An empty array means horizontal or
  unclassified. "Healthcare customers" means industries contains 'Healthcare'.
- "Domain" or "business unit" means domain_name (the customer's org unit). "Business function"
  (HR, Finance, Customer Service ...) is the business_functions array. If a user says "domain" and
  means a business area such as HR or claims, use business_functions and mention domain_name as an
  alternative.
- "Azure" alone means either the 'Azure' or the 'Azure DevOps' tech_stack label. Include both.
- Labels come from keyword matching (industry_source = INFERRED_KEYWORD) unless a steward mapped
  the industry (MANUAL). Mention this when the answer depends on inferred labels.

Label values
- sdlc_phases: Requirements, Design & Architecture, Development, Code Review & Quality, Testing,
  Build & Deploy (CI/CD), Operations & Support, Documentation, Project & Delivery Management
- industries: Healthcare, Life Sciences & Pharma, Insurance, Banking & Financial Services, Retail & CPG,
  Manufacturing, Telecom & Media, Energy & Utilities, Travel & Hospitality, Public Sector,
  Logistics & Supply Chain
- business_functions: Software Engineering & IT, Customer Service, Human Resources, Finance & Accounting,
  Sales & Marketing, Legal & Compliance, Procurement, Data & Analytics, Security
- archetypes: Summarizer, Extractor, Classifier / Router, Generator, Reviewer / Validator,
  Converter / Translator, Q&A / Knowledge Assistant, Planner / Orchestrator, Analyzer, Recommender
- tech_stack examples: Azure, AWS, Google Cloud, Jira, Azure DevOps, Confluence, GitHub, GitLab,
  ServiceNow, SAP, Salesforce, Microsoft 365, Databricks, Snowflake, Java, Python, .NET / C#,
  COBOL / Mainframe, SQL, OpenAI / GPT, RAG / Vector Search, OCR / Document AI, MCP, Selenium

Defaults
- "Customers built" means agents with agent_type = 'USER'. Exclude SYSTEM agents unless asked.
- "Published" or "live" means status = 'APPROVED'.
- Prefer run_count over platform_execution_counter for usage.
- Always join tables on _deployment_id as well as the id columns.
- For processes, use is_latest_version = true unless versions are asked for.
- Show names, not ids. Order results by the most meaningful measure, descending.
```

## 4. Example SQL queries

Add the queries in [`sample_queries.sql`](sample_queries.sql) under **Configure > Instructions > SQL queries**.
Each has its question on the `-- Q:` line. These examples do more for answer quality than anything else,
especially for the array and `explode` patterns.

## 5. Joins

`notebooks/04_apply_genie_metadata.py` declares primary and foreign keys in Unity Catalog, and Genie uses
them to join tables. If the notebook warns that a key could not be applied, add the join in
**Configure > Joins** instead. The main ones:

| Left | Right | On |
|---|---|---|
| `artifact_labels` | `artifact_catalog` | `_deployment_id`, `artifact_type`, `artifact_id` |
| `artifact_catalog` (artifact_type = 'AGENT') | `agents` | `_deployment_id`, `artifact_id = agent_id` |
| `artifact_catalog` (artifact_type = 'WORKFLOW') | `workflows` | `_deployment_id`, `artifact_id = workflow_id` |
| `workflow_agents` | `workflows`, `agents` | `_deployment_id`, `workflow_id` / `agent_id` |
| `agent_tools` | `agents`, `tools` | `_deployment_id`, `agent_id` / `tool_id` |
| `agent_knowledge_bases` | `agents`, `knowledge_bases` | `_deployment_id`, `agent_id` / `knowledge_base_id` |
| `mcp_tools` | `mcp_servers` | `_deployment_id`, `server_id` |
| `executions` | `agents` / `workflows` / `tools` | `_deployment_id`, `artifact_id` with `artifact_type` |

## 6. Questions to try

Structure and flavours
- What agents have healthcare customers built for testing?
- Which workflows use Azure and Jira together?
- How many agents support each SDLC phase, per business unit?
- What kinds of agents (archetypes) are built in each industry?
- Which technologies are most often used together?
- What are the most common agent chains in workflows?
- Which MCP tools write back to external systems?

Adoption and value
- Which agents are good candidates for reusable templates?
- Which tools are reused by the most agents?
- Which agents fail most often, and what do users comment on those runs?
- What did LLM usage cost per agent and model in the last 30 days?
- Which healthcare agents have no guardrail?

Gaps and demand
- What are users searching for that does not exist yet?
- Which artifacts could not be classified?
- What do complaints and feature requests mention most?

## 7. Keep it accurate

- Use **Benchmarks** (the space's evaluation tab): add the questions above with the SQL from
  `sample_queries.sql` as the expected answer, and re-run them after changing instructions or tables.
- Review questions users asked (**Monitoring**) weekly. When Genie gets one wrong, add an example query or
  an instruction instead of fixing it only once.
- Wrong industry? Add a row to `ref.industry_mapping`. Wrong or missing technology, phase or function? Edit
  `config/keyword_taxonomy.yml`. Both take effect on the next job run.
