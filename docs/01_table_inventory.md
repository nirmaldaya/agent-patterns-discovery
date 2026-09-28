# Step 1 · Table inventory for data exploration

Source: PostgreSQL schemas `core`, `mcp`, `process_studio`, `rbac` and `trulens` (201 tables in total).

**72 tables are ingested** for exploring agents, workflows, tools and knowledge bases. The other 129 are deliberately left out, and the reasons are listed at the end. The machine-readable version of this list, with the exact columns excluded, is [`config/tables.yml`](../config/tables.yml).

## How the data fits together

```
                         rbac.organization > domain > project > team
                                        ^ (via rbac.realm)
                                        |
 process_definition --nodes--> agents <--workflow_agents-- workflows
                                 |  \____ agents_tools ______> tools --> tools_parameters
                                 |  \____ agents_knowledge_bases > knowledgebase_collection_mst --> files
                                 |  \____ agent_guardrails ____> guardrail_mst
                                 |  \____ model / models (LLM)
                                 v
 usage:   artifact_executions, *_execution_job, artifact_events, agent_steps, user_activity
 LLM:     ai_gateway_audit_log                MCP: servers > tools > tool_execution_audit
 quality: *_user_ratings, *_favourites, user_feedback, trulens_*
 demand:  search_events
```

## Ingested tables

Load mode: **full** reloads the table each run, and **incr** appends new rows by the watermark column shown.

### A. Artifact definitions: what customers built

| Table | What it tells us | Load | Columns left out or masked |
|---|---|---|---|
| `core.agents` | Every agent: role, goal, backstory, description, expected output, model, status, org, tags, counters | full | dropped: `agent_image`; secrets masked in: `agent_config` |
| `core.agent_categories` | Agent category names | full | - |
| `core.tools` | Every platform tool: description, config, type, function type, methodology, counters | full | secrets masked in: `tool_config` |
| `core.tools_parameters` | Input parameters of each tool | full | - |
| `core.tools_builtin` | Tools shipped with the platform | full | - |
| `core.workflows` | Every workflow (crew / pipeline): description, config, status, org, counters | full | secrets masked in: `workflow_config` |
| `core.knowledgebase_collection_mst` | Every knowledge base: vector DB, type, function type, methodology | full | - |
| `core.knowledgebase_collection_transaction` | Files loaded into each knowledge base (name, size, embeddings) | full | dropped: `uploaded_by`, `file_path`; secrets masked in: `file_metadata` |
| `core.guardrail_mst` | Every guardrail: type, rules, status | full | - |
| `core.model` | LLM deployments agents are configured with | full | - |
| `core.models` | AI-gateway model catalogue (type, tier, capabilities, cost) | full | - |
| `core.model_providers` | LLM providers behind the gateway | full | dropped: `vault_path`; secrets masked in: `config` |
| `core.code_conversion_usecases` | Source and target languages of code-conversion use cases (tech stack signal) | full | - |
| `mcp.servers` | MCP servers onboarded: category, tags, transport, auth type, health | full | dropped: `authentication_config`; secrets masked in: `server_config`, `metadata` |
| `mcp.tools` | Tools exposed by each MCP server, with input schema and category | full | secrets masked in: `metadata` |
| `mcp.deployments` | Where each MCP server is deployed (environment) | full | - |
| `mcp.onboarding_workflows` | MCP server onboarding attempts and outcomes | full | secrets masked in: `server_config`, `metadata` |
| `process_studio.process_definition` | Process Studio processes (BPMN-like orchestration of agents, workflows, humans) | full | secrets masked in: `process_definition_json`, `designer_metadata_json` |

### B. Composition: how artifacts are wired together

| Table | What it tells us | Load | Columns left out or masked |
|---|---|---|---|
| `core.agents_tools` | Which tools each agent uses | full | - |
| `core.agents_knowledge_bases` | Which knowledge bases (RAG collections) each agent uses | full | - |
| `core.agent_guardrails` | Which guardrails are attached to each agent | full | - |
| `core.agents_user_hierarchy` | Agent to org-hierarchy assignment | full | - |
| `core.tool_user_hierarchy` | Tool to org-hierarchy assignment | full | - |
| `core.workflow_agents` | Ordered agents in each workflow | full | - |
| `core.workflows_user_hierarchy` | Workflow to org-hierarchy assignment | full | - |
| `core.knowledgebase_user_hierarchy` | Knowledge base to org-hierarchy assignment | full | - |
| `core.guardrail_user_hierarchy` | Guardrail to org-hierarchy assignment | full | - |
| `process_studio.process_definition_artifact_link` | Agents, workflows and tools placed as nodes in each process | full | - |

### C. Evolution: versions, clones and justifications

| Table | What it tells us | Load | Columns left out or masked |
|---|---|---|---|
| `core.agents_approved_history` | Every approved version of an agent, with tool and KB snapshots | full | secrets masked in: `agent_config`, `tools_snapshot`, `kb_snapshot` |
| `core.tools_approved_history` | Every approved version of a tool | full | secrets masked in: `tool_config` |
| `core.workflows_approved_history` | Every approved version of a workflow, with agent snapshot | full | secrets masked in: `workflow_config`, `agents_snapshot` |
| `core.agent_justification_audit` | Why an agent was created or cloned (free text) | full | dropped: `created_by_email` |

### D. Organisation and context: who built it and where

| Table | What it tells us | Load | Columns left out or masked |
|---|---|---|---|
| `rbac.organization` | Top of the customer org hierarchy | full | dropped: `image` |
| `rbac.domain` | Org hierarchy level 2 (business unit). Not an industry | full | dropped: `image` |
| `rbac.project` | Org hierarchy level 3 | full | dropped: `image` |
| `rbac.team` | Org hierarchy level 4 | full | dropped: `image` |
| `rbac.realm` | Workspace pointing to organization, domain, project and team. Main join for org context | full | - |
| `rbac.practice_area` | Practice area names referenced by agents, tools and knowledge bases | full | - |
| `rbac.tags` | Controlled tag list | full | - |
| `rbac.hierarchy_label_configuration` | What this customer calls each hierarchy level (e.g. 'Business Unit' for domain) | full | - |
| `rbac.user_role_hierarchy` | User role to hierarchy entity assignment | full | - |
| `rbac.users` | User persona only: department, job title, location, team. No names, emails or credentials | full | only: `user_id`, `team_id`, `job_title`, `department`, `location`, `timezone`, `is_active`, `created_at`, `last_logged_in`, `last_realm_id` |
| `rbac.integration_providers` | Third-party systems available as integrations (Jira, ADO, ...) | full | dropped: `client_id`, `client_secret`, `authorize_url`, `token_url`, `callback_url`; secrets masked in: `meta`, `field_schema` |
| `rbac.integration_provider_tools` | Tools that use each integration | full | secrets masked in: `config`, `meta` |
| `rbac.integrations` | Which users connected which integrations | full | only: `id`, `user_id`, `provider`, `auth_type`, `connected_at`, `last_synced_at`, `created_at` |
| `core.tenants` | Tenant tier, region, PII mode and guardrail level | full | dropped: `webhook_url` |
| `core.customer_license_mst` | Customer name and licence period | full | only: `id`, `customer_name`, `start_date`, `end_date`, `issue_date` |

### E. Usage and behaviour: what customers actually run

| Table | What it tells us | Load | Columns left out or masked |
|---|---|---|---|
| `core.artifact_executions` | One row per agent, workflow or tool run: time, tokens, cost, rating, issue tags, comment | full | - |
| `core.artifact_events` | Parent/child execution spans (which agent or tool ran inside which workflow) | full | - |
| `core.agent_execution_job` | Agent execution jobs and their final status | full | dropped: `user_signature` |
| `core.workflow_execution_job` | Workflow execution jobs and their final status | full | dropped: `user_signature` |
| `core.agent_steps` | Step-level trace of agents inside workflow runs (thoughts, tool calls) | incr (`id`) | - |
| `core.user_activity` | Views and executions of agents, workflows and tools by users | incr (`id`) | dropped: `ip_address`, `user_agent` |
| `core.feature_usage` | Platform feature usage per user | full | - |
| `core.ai_gateway_audit_log` | Every LLM call through the gateway: model, tokens, cost, latency, PII and guardrail outcome | incr (`occurred_at`) | dropped: `prompt_text`, `response_text`, `user_login`, `user_name`, `user_email` |
| `mcp.tool_execution_audit` | Every MCP tool call: agent, workflow, success, latency, security violation | incr (`id`) | dropped: `request_payload`, `response_payload`, `user_email`, `credential_used`, `user_agent` |
| `mcp.tool_usage_stats` | MCP tool usage per organisation and workflow | incr (`id`) | dropped: `parameters` |
| `process_studio.process_execution` | Process runs and outcomes | full | dropped: `start_user_inputs_json` |
| `process_studio.node_execution_projection` | Node-level status inside process runs | full | - |
| `process_studio.human_task` | Human approval and review steps inside process runs | full | - |

### F. Quality and sentiment

| Table | What it tells us | Load | Columns left out or masked |
|---|---|---|---|
| `core.agent_user_ratings` | Star ratings of agents | full | - |
| `core.tool_user_ratings` | Star ratings of tools | full | - |
| `core.workflow_user_ratings` | Star ratings of workflows | full | - |
| `core.agent_favourites` | Agents users bookmarked | full | - |
| `core.tool_favourites` | Tools users bookmarked | full | - |
| `core.workflow_favourites` | Workflows users bookmarked | full | - |
| `core.user_feedback` | Bugs, feature requests, complaints and praise with sentiment | full | - |
| `trulens.trulens_apps` | Applications evaluated by TruLens | full | secrets masked in: `app_json` |
| `trulens.trulens_feedback_defs` | TruLens evaluation metric definitions | full | - |
| `trulens.trulens_feedbacks` | TruLens evaluation scores (groundedness, relevance ...) | full | dropped: `calls_json` |
| `trulens.trulens_records` | Evaluated records (timing and cost only) | full | dropped: `input`, `output`, `record_json` |

### G. Demand signals

| Table | What it tells us | Load | Columns left out or masked |
|---|---|---|---|
| `core.search_events` | What users searched for and whether anything was found (unmet demand) | incr (`id`) | dropped: `client_ip`, `user_agent` |

Binary (`bytea`) columns are always dropped, for example `hierarchy_label_configuration` icons.

## Tables not ingested

| Reason | Tables |
|---|---|
| Credentials, keys and secrets. Never ingest | `core.ado_credential`, `core.jira_credential`, `core.security_credential`, `core.service_api_keys`, `core.tenant_api_keys`, `core.api_key_audit_log`, `core.license`, `core.alm_config`, `mcp.server_credentials`, `mcp.credential_audit_log`, `rbac.integration_credentials`, `rbac.user_token_store`, `rbac.validation_rules_config`, `core.validation_rules` |
| Binary file uploads | `core.agent_execution_job_attachments`, `core.workflow_execution_job_attachments`, `core.workflow_execution_files`, `process_studio.process_execution_input_file` |
| Raw prompts, inputs, outputs and logs. Phase 2 NLP, needs a content/PII policy first | `core.agents_execution_logs`, `core.workflow_execution_logs`, `core.agent_execution_output`, `core.agent_execution_job_requests`, `core.workflow_execution_job_requests`, `core.workflow_execution_history`, `core.chat_memory_history`, `core.chat_sessions`, `core.transactions_history`, `core.analysis_transactions`, `process_studio.process_execution_input_override`, `core.aavabot_ingestion_log`, `core.aavabot_prompts` |
| Draft and secondary version history. Phase 2 (design evolution) | `core.agents_drafted_history`, `core.tools_drafted_history`, `core.workflows_drafted_history`, `core.knowledgebase_collection_mst_approved_history`, `core.knowledgebase_collection_mst_draft_history`, `core.guardrails_approved_history`, `core.guardrails_draft_history`, `mcp.tool_versions`, `mcp.tool_integrity_snapshots`, `process_studio.process_definition_user_hierarchy` |
| Legacy use-case and prompt catalogues. Review in phase 2 | `core.use_cases`, `core.prompt_new`, `core.prompt_templates`, `core.prompt_example`, `core.prompt_category`, `core.prompt_domain`, `core.data_engineering_usecases`, `core.delivery_excellence_usecases`, `core.visualization_usecases`, `core.plugins_usecases`, `core.qe_track_usecase`, `core.qe_workflow_config`, `core.jira_issues_status`, `core.labels`, `core.category`, `core.analysis_type_mst`, `core.feedback`, `core.component`, `core.component_analytics` |
| Access-control plumbing (pages, endpoints, roles, studios) | `rbac.actions`, `rbac.pages`, `rbac.endpoints`, `rbac.endpoints_registry`, `rbac.role_permissions`, `rbac.roles`, `rbac.user_roles`, `rbac.portal`, `rbac.portal_roles`, `rbac.studio`, `rbac.studio_pages`, `rbac.studio_roles`, `rbac.user_studio_portals`, `rbac.user_studio_role_access`, `rbac.user_studio_roles`, `rbac.user_studios`, `rbac.admin_level_access`, `rbac.artifact_access`, `rbac.artifact_keys`, `rbac.artifact_validation`, `rbac.skipped_endpoints`, `rbac.realm_level_mapping`, `rbac.user_realm`, `rbac.user_preferences`, `rbac.hierarchy_migration`, `rbac.hierarchy_migration_run_audit`, `rbac.hierarchy_label_configuration_history`, `rbac.audit_log`, `core.audit_log` |
| Platform configuration and operations | `core.shedlock`, `core.elastic_sync_status`, `core.search_sync_status`, `core.dashboard_refresh_log`, `core.deletion_tracking`, `core.callback_delivery_log`, `core.plugin_sync_metadata`, `core.tenant_quotas`, `core.tenant_model_policies`, `core.model_routing_rules`, `core.ai_model_configs`, `core.azure_openai_model`, `core.aws_bedrock_model`, `core.google_ai_model`, `core.azure_api_version_ref`, `core.configs`, `core.settings`, `core.reference_data`, `core.manage_workflow_id`, `core.workflow_callback_config`, `core.user_sessions`, `core.user_goals`, `core.mylist`, `core.mylist_entity_mapping`, `core.agent_tools_values`, `core.workflow_tools_values`, `process_studio.outbox_event`, `process_studio.process_audit_event`, `mcp.rate_limit_tracking`, `mcp.server_health_checks`, `mcp.security_events`, `mcp.tool_security_policies`, `mcp.tool_role_mappings`, `mcp.user_tool_consents`, `mcp.workload_identities`, `mcp.offboarding_workflows` |
| TruLens internals | `trulens.trulens_dataset`, `trulens.trulens_ground_truth`, `trulens.trulens_runs`, `trulens.trulens_alembic_version` |

## Things to confirm with the platform team

The source has no declared foreign keys, so the joins below were inferred from column names. Please confirm them:

| Assumption | Used in |
|---|---|
| `agents.domain_id`, `tools.domain_id`, `workflows.domain_id` reference `rbac.domain.id` | Fallback org context when `realm_id` is empty |
| `agents/tools/workflows/knowledge bases.practice_area` reference `rbac.practice_area.id` | `practice_area` column |
| `agents.model_id` references `core.model.id`, and `agents.gateway_model_id` references `core.models.model_id` | `model_name` |
| `agents_tools.tool_id` references `core.tools.id` (not `mcp.tools`) | agent-tool bridge |
| `artifact_executions.artifact_type` values are `AGENT`, `WORKFLOW`/`PIPELINE`, `TOOL` | run counts |
| `artifact_executions.execution_id` matches `agent_execution_job.execution_id` / `workflow_execution_job.executionid` | `job_status` |
| `ai_gateway_audit_log.agent_id` / `pipeline_id` hold `core.agents.id` / `core.workflows.id` as text | LLM usage per agent |
| `mcp.tool_execution_audit.agent_id` / `workflow_id` reference core agents and workflows | MCP usage per agent |
| `process_definition.status`, `approval_status` codes (smallint) | shown as raw codes until the mapping is known |
| Format of the free-text `tags` column (comma separated?) | kept as text |
