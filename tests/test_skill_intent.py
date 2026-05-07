from __future__ import annotations

from skills.intent import extract_intent, extract_symbol_arg


def test_extract_intent_detects_code_file_request():
    intent = extract_intent('Explain auth.py')

    assert intent['action'] == 'summarize'
    assert intent['domain'] == 'code'
    assert intent['filetype'] == 'py'
    assert intent['args'] == {'path': 'auth.py'}


def test_extract_intent_strips_trailing_punctuation_from_path():
    intent = extract_intent('Create a simple snake game in snake.py.')

    assert intent['domain'] == 'code'
    assert intent['filetype'] == 'py'
    assert intent['args'] == {'path': 'snake.py'}


def test_extract_intent_does_not_guess_symbol_from_file_only_request():
    intent = extract_intent('Explain snake.py')

    assert intent['args'] == {'path': 'snake.py'}
    assert 'symbol' not in intent['args']


def test_extract_intent_detects_code_review_request():
    intent = extract_intent('Review review_target.py')

    assert intent['action'] == 'review'
    assert intent['domain'] == 'code'
    assert intent['args'] == {'path': 'review_target.py'}


def test_extract_symbol_arg_requires_explicit_function_marker():
    assert extract_symbol_arg('Explain function login in auth.py', {'path': 'auth.py'}) == 'login'
    assert extract_symbol_arg('Explain login in auth.py', {'path': 'auth.py'}) is None
    assert extract_symbol_arg('Create a skill to debug a function') is None


def test_extract_symbol_arg_supports_symbol_before_marker():
    assert extract_symbol_arg('Explain login function in auth.py', {'path': 'auth.py'}) == 'login'


def test_extract_symbol_arg_supports_debug_symbol_call_before_path():
    intent = extract_intent('debug main() in aaa.py')

    assert intent['action'] == 'debug'
    assert intent['args'] == {'path': 'aaa.py', 'symbol': 'main'}


def test_extract_intent_classifies_questions_and_commands():
    assert extract_intent('What does auth.py do?')['speech_act'] == 'question'
    assert extract_intent('How would you refactor auth.py?')['speech_act'] == 'question'
    assert extract_intent('Explain auth.py')['speech_act'] == 'command'
    assert extract_intent('Please refactor auth.py')['speech_act'] == 'command'
