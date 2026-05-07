# Create New Skill

Use this procedure when the user asks to create, add, register, define, or author a new reusable skill.

1. Identify the requested skill purpose, target task, and expected trigger phrases from the user's request.
2. Ask at most one concise clarification question only if the skill purpose is too ambiguous to create useful metadata and a procedure.
3. If the request is clear enough, draft:
   - a short title suitable for a filename
   - a markdown procedure that gives the model concrete steps to follow
   - metadata JSON with the required routing fields
4. The metadata JSON must include:
   - `name`
   - `summary`
   - `description`
   - `categories`
   - `when_to_use`
   - `when_not_to_use`
   - `trigger_actions`
   - `inputs`
   - `outputs`
   - `tools_required`
5. Include `examples`, `exclusions`, `preconditions`, and `default_score` when they improve routing.
6. Before calling `create_skill`, validate the draft:
   - Trigger text, examples, and `when_to_use` must be instruction-style, not question-shaped.
   - Use runtime input names: `path`, `symbol`, `language`, or `query`. Use `path`, not `file_path`.
   - `inputs` and `outputs` values must be schema objects such as `{ "type": "string", "description": "..." }`, not bare strings.
   - Include at least one close-but-wrong case in `when_not_to_use`.
   - Include at least one example request.
   - Keep `default_score` conservative, normally between `0.4` and `0.7` unless the skill is narrowly about skill authoring.
   - Every tool in `tools_required` must be named explicitly in the markdown procedure.
   - The markdown procedure must say what to do when a required file, symbol, tool result, or precondition is missing.
   - For code skills, the metadata JSON `when_not_to_use` or `exclusions` must explicitly contain every nearby task type the skill does not handle: create, edit, refactor, fix, debug, review, and test. Putting these words only in the markdown procedure is not enough.
7. Call `create_skill` with the title, markdown procedure, and metadata JSON.
8. Do not manually write skill files unless `create_skill` fails.
9. After `create_skill` succeeds, report the created `metadata_path`, `procedure_path`, and whether the registry was reloaded.
10. If `create_skill` fails validation, draft files were written under `skills/drafts/`. Do not edit `skill_catalog/metadatas/` or `skill_catalog/procedures/`.
11. If the result includes `repair_suggestions`, call `repair_skill_draft` with the returned `draft_id` and those structured repairs. Do not use `replace_in_file` for metadata repairs when `repair_skill_draft` can apply them.
12. Use `replace_in_file` only for markdown procedure repairs or when no structured metadata repair is available. If validation mentions metadata, repair the JSON draft file, not the markdown procedure. Use `read_file` only if you need to inspect a draft file first.
13. After repairing drafts, call `finalize_skill_draft` with the returned `draft_id`.
14. After 3 failed finalize attempts, stop retrying and show the user the draft paths and validation errors.

The generated skill should route only for instructions to perform its procedure. It should not route for general questions unless the user explicitly wants a question-answering skill.
