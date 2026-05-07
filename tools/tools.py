from tools.basic_tools import (
    append_to_file,
    find_file,
    read_file,
    read_file_with_line_numbers,
    remove_file,
    replace_in_file,
    run_shell,
    write_file,
)
from tools.code_tools import (
    explain_function_for_model,
    list_code_symbols,
    summarize_code_file,
)
from tools.curl_tool import curl_url
from tools.embedding import embed_texts
from tools.owasp_reference_tools import (
    rebuild_owasp_reference_index,
    search_owasp_reference,
    validate_owasp_corpus,
)
from tools.review_target_tools import discover_review_targets
from tools.schemas import OPENAI_TOOLS
from tools.skill_authoring_tools import create_skill, finalize_skill_draft, repair_skill_draft
from tools.skill_index_tools import (
    SKILL_INDEX_CHUNKER_VERSION,
    SKILL_INDEX_SCHEMA_VERSION,
    create_skill_faiss_index,
    rebuild_skill_faiss_index,
    search_skill_faiss_index,
)
from tools.tool_registry import Tool


# Public tool registry consumed by the agent. Implementation details live in
# responsibility-specific modules; this facade keeps existing imports stable.
TOOLS = {
    'run_shell': Tool('run_shell', run_shell),
    'read_file': Tool('read_file', read_file),
    'read_file_with_line_numbers': Tool('read_file_with_line_numbers', read_file_with_line_numbers),
    'write_file': Tool('write_file', write_file),
    'replace_in_file': Tool('replace_in_file', replace_in_file),
    'append_to_file': Tool('append_to_file', append_to_file),
    'find_file': Tool('find_file', find_file),
    'summarize_code_file': Tool('summarize_code_file', summarize_code_file),
    'list_code_symbols': Tool('list_code_symbols', list_code_symbols),
    'explain_function_for_model': Tool('explain_function_for_model', explain_function_for_model),
    'curl_url': Tool('curl_url', curl_url),
    'discover_review_targets': Tool('discover_review_targets', discover_review_targets),
    'validate_owasp_corpus': Tool('validate_owasp_corpus', validate_owasp_corpus),
    'rebuild_owasp_reference_index': Tool('rebuild_owasp_reference_index', rebuild_owasp_reference_index),
    'search_owasp_reference': Tool('search_owasp_reference', search_owasp_reference),
    'create_skill_faiss_index': Tool('create_skill_faiss_index', create_skill_faiss_index),
    'search_skill_faiss_index': Tool('search_skill_faiss_index', search_skill_faiss_index),
    'rebuild_skill_faiss_index': Tool('rebuild_skill_faiss_index', rebuild_skill_faiss_index),
    'create_skill': Tool('create_skill', create_skill),
    'finalize_skill_draft': Tool('finalize_skill_draft', finalize_skill_draft),
    'repair_skill_draft': Tool('repair_skill_draft', repair_skill_draft),
    'remove_file': Tool('remove_file', remove_file),
}


__all__ = [
    'OPENAI_TOOLS',
    'SKILL_INDEX_CHUNKER_VERSION',
    'SKILL_INDEX_SCHEMA_VERSION',
    'TOOLS',
    'append_to_file',
    'create_skill',
    'curl_url',
    'discover_review_targets',
    'create_skill_faiss_index',
    'embed_texts',
    'explain_function_for_model',
    'find_file',
    'finalize_skill_draft',
    'repair_skill_draft',
    'list_code_symbols',
    'read_file',
    'read_file_with_line_numbers',
    'rebuild_owasp_reference_index',
    'rebuild_skill_faiss_index',
    'remove_file',
    'replace_in_file',
    'run_shell',
    'search_owasp_reference',
    'search_skill_faiss_index',
    'summarize_code_file',
    'validate_owasp_corpus',
    'write_file',
]
