-- APDI Genie space - trusted example queries
--
-- Add each block to the Genie space as an example SQL query (Configure > Instructions > SQL queries),
-- using the Q line as the question. They teach Genie the array filters, the explode pattern and
-- the business meaning of the tables. They are also good benchmark questions.
-- Queries use explore.<table> and run with the space's catalog selected.


-- Q: What agents have healthcare customers built for testing?
SELECT artifact_name, organization_name, domain_name, team_name, sdlc_phases, industries, industry_source, run_count
FROM explore.artifact_catalog
WHERE artifact_type = 'AGENT'
  AND array_contains(industries, 'Healthcare')
  AND array_contains(sdlc_phases, 'Testing')
ORDER BY run_count DESC;


-- Q: Which workflows use Azure and Jira together?
SELECT artifact_name AS workflow_name, tech_stack, related_names AS agent_chain, run_count
FROM explore.artifact_catalog
WHERE artifact_type = 'WORKFLOW'
  AND (array_contains(tech_stack, 'Azure') OR array_contains(tech_stack, 'Azure DevOps'))
  AND array_contains(tech_stack, 'Jira')
ORDER BY run_count DESC;


-- Q: How many agents support each SDLC phase?
SELECT phase AS sdlc_phase, count(*) AS agents, sum(run_count) AS runs
FROM explore.artifact_catalog
LATERAL VIEW explode(sdlc_phases) p AS phase
WHERE artifact_type = 'AGENT' AND status = 'APPROVED'
GROUP BY phase
ORDER BY agents DESC;


-- Q: Show agents by business unit (domain) and SDLC phase
SELECT COALESCE(domain_name, 'Unassigned') AS domain_name, phase AS sdlc_phase, count(*) AS agents
FROM explore.artifact_catalog
LATERAL VIEW explode(sdlc_phases) p AS phase
WHERE artifact_type = 'AGENT'
GROUP BY 1, 2
ORDER BY 1, agents DESC;


-- Q: Which technologies are most often used together in agents?
WITH tech AS (
  SELECT _deployment_id, artifact_id, t AS tech
  FROM explore.artifact_catalog
  LATERAL VIEW explode(tech_stack) x AS t
  WHERE artifact_type = 'AGENT'
)
SELECT a.tech AS tech_1, b.tech AS tech_2, count(*) AS agents
FROM tech a
JOIN tech b ON a._deployment_id = b._deployment_id AND a.artifact_id = b.artifact_id AND a.tech < b.tech
GROUP BY a.tech, b.tech
ORDER BY agents DESC
LIMIT 20;


-- Q: What kinds of agents (archetypes) are customers building in each industry?
SELECT ind AS industry, arch AS archetype, count(*) AS agents
FROM explore.artifact_catalog
LATERAL VIEW explode(CASE WHEN size(industries) = 0 THEN array('Horizontal / Unclassified') ELSE industries END) i AS ind
LATERAL VIEW explode(archetypes) a AS arch
WHERE artifact_type = 'AGENT'
GROUP BY 1, 2
ORDER BY 1, agents DESC;


-- Q: Which tools are reused by the most agents?
SELECT tool_name, tool_type, action_type, agent_count, agent_names, run_count
FROM explore.tools
ORDER BY agent_count DESC, run_count DESC
LIMIT 20;


-- Q: What are the most common agent chains in workflows?
SELECT agent_count, agent_chain, count(*) AS workflows, sum(run_count) AS runs
FROM explore.workflows
GROUP BY agent_count, agent_chain
ORDER BY workflows DESC, runs DESC;


-- Q: What are users searching for that does not exist yet?
SELECT query_normalized, count(*) AS searches, max(executed_at) AS last_searched
FROM explore.search_queries
WHERE is_zero_result
GROUP BY query_normalized
ORDER BY searches DESC
LIMIT 25;


-- Q: Which agents are good candidates for reusable templates?
SELECT agent_name, domain_name, team_name, run_count, distinct_runner_count, avg_user_rating, favourite_count,
       workflow_count, is_golden, tool_names
FROM explore.agents
WHERE agent_type = 'USER' AND status = 'APPROVED'
ORDER BY distinct_runner_count DESC, run_count DESC, avg_user_rating DESC NULLS LAST
LIMIT 20;


-- Q: Which LLM models do agents use in each business unit?
SELECT COALESCE(domain_name, 'Unassigned') AS domain_name, model_name, count(*) AS agents
FROM explore.agents
WHERE agent_type = 'USER'
GROUP BY 1, 2
ORDER BY 1, agents DESC;


-- Q: What did LLM usage cost per agent in the last 30 days?
SELECT agent_name, model_key, sum(call_count) AS calls, sum(total_tokens) AS tokens, round(sum(cost_usd), 2) AS cost_usd,
       sum(pii_detected_count) AS pii_hits, sum(guardrail_blocked_count) AS blocked_calls
FROM explore.llm_usage_daily
WHERE usage_date >= date_sub(current_date(), 30) AND agent_name IS NOT NULL
GROUP BY agent_name, model_key
ORDER BY cost_usd DESC;


-- Q: Which agents fail most often?
SELECT artifact_name AS agent_name, count(*) AS runs,
       count_if(job_status = 'FAILED') AS failed_runs,
       round(100.0 * count_if(job_status = 'FAILED') / count(*), 1) AS failure_pct,
       round(avg(duration_seconds)) AS avg_seconds
FROM explore.executions
WHERE artifact_type = 'AGENT'
GROUP BY artifact_name
HAVING count(*) >= 1
ORDER BY failed_runs DESC, failure_pct DESC;


-- Q: How many healthcare agents have a guardrail attached?
SELECT a.agent_name, a.guardrail_count, a.guardrail_names, a.knowledge_base_names
FROM explore.agents a
JOIN explore.artifact_catalog c
  ON c._deployment_id = a._deployment_id AND c.artifact_type = 'AGENT' AND c.artifact_id = a.agent_id
WHERE array_contains(c.industries, 'Healthcare')
ORDER BY a.guardrail_count;


-- Q: Which MCP tools write to external systems and how reliable are they?
SELECT server_name, tool_name, action_type, call_count, success_rate_pct, distinct_agent_count
FROM explore.mcp_tools
ORDER BY call_count DESC;


-- Q: Which artifacts could not be classified into an SDLC phase or business function?
SELECT artifact_type, artifact_name, description
FROM explore.artifact_catalog
WHERE size(sdlc_phases) = 0 AND size(business_functions) = 0
ORDER BY artifact_type, artifact_name;


-- Q: Why was an agent labelled with a tech stack or phase?
SELECT artifact_name, dimension, label, matched_keyword, source
FROM explore.artifact_labels
WHERE artifact_type = 'AGENT' AND lower(artifact_name) LIKE '%test case%'
ORDER BY dimension, label;
