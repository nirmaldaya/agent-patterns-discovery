# Next iteration: tuning after the first run

Findings from the first run on real data (deployment `dep_001`, about 29,400 artifacts), parked until after the
first demo.

| Area | First run | Verdict |
|---|---|---|
| SDLC phase | 93% of agents, 68% of workflows | Good |
| Tech stack | 73% of agents, 56% of workflows, 69% of tools | Good |
| Industry | 14% of agents, 6% of workflows | Low. Agent text rarely names an industry |
| Solution patterns | 10 communities, the two largest over 7,000 members | Too coarse |
| MCP servers, MCP tools, processes | 0 rows in `artifact_catalog` | To check |

## 1. Industry mapping (biggest win)

Map the 19 organizations in `ref.industry_mapping`. This lists them with the industries keyword matching found:

```sql
SELECT c.organization_name,
       count(*) AS artifacts,
       sum(CASE WHEN size(c.industries) > 0 THEN 1 ELSE 0 END) AS labelled,
       concat_ws(', ', slice(array_sort(collect_list(i.industry)), 1, 3)) AS sample_inferred
FROM apdi.explore.artifact_catalog c
LEFT JOIN (SELECT artifact_type, artifact_id, _deployment_id, industry
           FROM apdi.explore.artifact_catalog LATERAL VIEW explode(industries) t AS industry) i
  ON i._deployment_id = c._deployment_id AND i.artifact_type = c.artifact_type AND i.artifact_id = c.artifact_id
GROUP BY 1 ORDER BY 2 DESC;
```

```sql
INSERT INTO apdi.ref.industry_mapping VALUES
  ('dep_001', 'ORGANIZATION', '<organization name>', '<Industry>', '<you>', current_timestamp(), NULL);
```

Use `DOMAIN` level where a business unit differs from its organization. Leave internal or multi-industry
organizations unmapped.

**Possible enhancement:** propagate industry within an org unit. When most labelled artifacts in a business unit
point to one industry, give the unit's other artifacts that industry with `industry_source = INFERRED_ORG`.

## 2. Solution patterns too coarse

Re-run `05_graph_analytics` with `resolution` = 3, then 5 if still too large. Target: dozens of patterns, most
between 20 and 500 members.

```sql
SELECT count(*) AS patterns, max(size) AS largest, percentile(size, 0.5) AS median
FROM apdi.explore.graph_communities;
```

## 3. False-positive labels

"Email" appears as a top technology in two of the largest patterns. Check which keywords drive each label:

```sql
SELECT dimension, label, matched_keyword, count(*) AS artifacts
FROM apdi.explore.artifact_labels
WHERE source = 'KEYWORD'
GROUP BY 1, 2, 3 ORDER BY artifacts DESC LIMIT 60;

SELECT name, role, goal FROM apdi.explore.agents WHERE lower(goal) LIKE '%email%' LIMIT 10;
```

Then tighten `config/keyword_taxonomy.yml` (for example, require email to appear as an integration such as
"send email", "outlook", "smtp", rather than any mention).

## 4. No MCP servers, MCP tools or processes

```sql
SELECT 'mcp_servers' t, count(*) FROM apdi.raw_mcp.mcp_servers
UNION ALL SELECT 'mcp_tools', count(*) FROM apdi.raw_mcp.mcp_tools
UNION ALL SELECT 'processes', count(*) FROM apdi.explore.processes;
```

All zero means the features are unused in this deployment (a finding in itself). Otherwise, fix the catalog query
in `notebooks/03_build_labels_and_catalog.py`.

## Re-run order after changes

03 → 04 → 05 (new resolution) → 06. The Genie space and the app pick up the new data automatically.
