# Solar AI Context Pack

Use these files as static context for a solar asset-management dashboard AI.

The goal is to help the AI move from "there is an alert" to:
1. Is this real or a data-quality issue?
2. What is the likely root-cause category?
3. What evidence supports that theory?
4. What is the estimated operational/financial impact?
5. Who owns the next action?
6. What should be done next?

Recommended loading order:
1. ai_system_prompt.md
2. kpi_definitions.json
3. issue_taxonomy.json
4. data_dictionary_scada.csv
5. data_quality_rules.json
6. alarm_action_matrix.csv
7. rca_playbooks.md
8. escalation_sla_matrix.csv
9. site_metadata_template.csv
10. contract_om_context_template.csv
11. known_exceptions_template.csv
12. ai_output_schema.json

Best practice:
- Keep these files mostly static.
- Feed live SCADA, ticket, email, and budget data separately.
- Update site_metadata_template.csv and contract_om_context_template.csv with real site-level data.
- Update known_exceptions_template.csv whenever a recurring issue is explained.
