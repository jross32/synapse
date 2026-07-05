"""REST routes for Synapse Quality OS gates, contracts, evidence, and impact audit."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from . import quality_os
from .storage import Storage


def build_quality_os_router(storage: Storage) -> APIRouter:
    router = APIRouter(tags=["quality-os"])

    @router.get("/quality-gates", response_model=None)
    async def list_quality_gates(
        subject_type: str | None = None,
        subject_id: str | None = None,
        status: str | None = None,
        blocking: bool | None = None,
    ) -> dict[str, Any]:
        parsed_status = (
            quality_os.QualityGateStatus(status) if status else None
        )
        return {
            "gates": [
                gate.model_dump(mode="json")
                for gate in quality_os.list_gates(
                    storage.conn,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    status=parsed_status,
                    blocking=blocking,
                )
            ]
        }

    @router.post("/quality-gates", response_model=None, status_code=201)
    async def create_quality_gate(payload: quality_os.QualityGateCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            created = quality_os.create_gate(conn, payload)
        return created.model_dump(mode="json")

    @router.get("/quality-gates/{gate_id}", response_model=None)
    async def get_quality_gate(gate_id: str) -> dict[str, Any]:
        return quality_os.get_gate(storage.conn, gate_id).model_dump(mode="json")

    @router.post("/quality-gates/{gate_id}/resolve", response_model=None)
    async def resolve_quality_gate(
        gate_id: str, payload: quality_os.QualityGateResolveRequest
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            resolved = quality_os.resolve_gate(conn, gate_id, payload)
        return resolved.model_dump(mode="json")

    @router.post("/quality-gates/{gate_id}/waive", response_model=None)
    async def waive_quality_gate(
        gate_id: str, payload: quality_os.QualityGateWaiveRequest
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            waived = quality_os.waive_gate(conn, gate_id, payload)
        return waived.model_dump(mode="json")

    @router.get("/ui-contracts", response_model=None)
    async def list_ui_contracts() -> dict[str, Any]:
        return {
            "contracts": [
                contract.model_dump(mode="json")
                for contract in quality_os.list_contracts(storage.conn)
            ]
        }

    @router.post("/ui-contracts", response_model=None, status_code=201)
    async def create_ui_contract(payload: quality_os.UiContractCreate) -> dict[str, Any]:
        with storage.transaction() as conn:
            created = quality_os.create_contract(conn, payload)
        return created.model_dump(mode="json")

    @router.get("/ui-contracts/{contract_id}", response_model=None)
    async def get_ui_contract(contract_id: str) -> dict[str, Any]:
        return quality_os.get_contract(storage.conn, contract_id).model_dump(mode="json")

    @router.post("/ui-contracts/{contract_id}/run", response_model=None)
    async def run_ui_contract(
        contract_id: str, payload: quality_os.UiContractRunRequest
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            contract, evidence, gate = quality_os.run_contract(conn, contract_id, payload)
        return {
            "contract": contract.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
            "gate": gate.model_dump(mode="json") if gate else None,
        }

    @router.post("/ui-contracts/promote", response_model=None, status_code=201)
    async def promote_ui_contract(
        payload: quality_os.UiContractPromoteRequest
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            contract = quality_os.promote_contract(conn, payload)
        return contract.model_dump(mode="json")

    @router.get("/ui-surface-map", response_model=None)
    async def get_ui_surface_map() -> dict[str, Any]:
        return {
            "surfaces": [
                surface.model_dump(mode="json")
                for surface in quality_os.list_surfaces(storage.conn)
            ]
        }

    @router.post("/ui-impact-audit", response_model=None)
    async def run_ui_impact_audit(
        payload: quality_os.UiImpactAuditRequest,
    ) -> dict[str, Any]:
        with storage.transaction() as conn:
            result = quality_os.impact_audit(conn, payload)
        return result.model_dump(mode="json")

    return router
