from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.base import ContractModel, ResultStatus


class DemoContract(ContractModel):
    name: str
    count: int
    optional: str | None = None


class DemoStatusContract(ContractModel):
    status: ResultStatus


def test_contract_model_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        DemoContract(name='demo', count=1, unexpected=True)


def test_contract_model_validates_assignment():
    contract = DemoContract(name='demo', count=1)

    with pytest.raises(ValidationError):
        contract.count = 'not-an-int'


def test_to_payload_excludes_none_values():
    contract = DemoContract(name='demo', count=1, optional=None)

    assert contract.to_payload() == {
        'name': 'demo',
        'count': 1,
    }


def test_to_payload_keeps_non_none_values():
    contract = DemoContract(name='demo', count=1, optional='value')

    assert contract.to_payload() == {
        'name': 'demo',
        'count': 1,
        'optional': 'value',
    }


def test_result_status_accepts_known_values():
    contract = DemoStatusContract(status='ok')

    assert contract.status == 'ok'
    assert contract.to_payload() == {'status': 'ok'}


def test_result_status_serializes_enum_values():
    contract = DemoStatusContract(status=ResultStatus.APPROVAL_REQUIRED)

    assert contract.to_payload() == {'status': 'approval_required'}


def test_result_status_rejects_unknown_values():
    with pytest.raises(ValidationError):
        DemoStatusContract(status='pending')
