"""미팅 작성자가 동결된 근거·CRM·이전 보고서를 읽는 도구."""

import copy
from typing import Any
from uuid import UUID

from app.agents.reports.meeting_contract import (
    COMMON_SCOPES,
    UNASSIGNED_SCOPES,
    ReportWritingInput,
)


def create_meeting_tools(source: ReportWritingInput) -> list:
    """실행 입력 하나에 묶인 읽기 전용 도구 세 개를 반환한다."""

    def read_meeting_evidence(sales_deal_id: UUID | None = None) -> dict[str, Any]:
        """현재 미팅의 동결 근거를 읽는다.

        딜 작성·수정 task에서는 선택된 ``sales_deal_id``를 넣어 해당 딜과 공통
        근거를 받고, 공통·딜 미지정 작성에서는 인수 없이 해당 범위의 근거만 받는다. 선택하지
        않은 딜은 오류이다. 반환값은 ``evidence``와 배경 참고용 ``attachments`` 목록이다.
        첨부를 이번 미팅의 발언·합의 근거로 쓰지 않으며 DB나 외부 자료를 조회하지 않는다.
        """
        if sales_deal_id is not None and sales_deal_id not in source.evidence.selected_deal_ids:
            return {"error": "deal_not_selected"}
        items = [
            item.model_dump(mode="json")
            for item in source.evidence.items
            if (
                item.applicability.scope in COMMON_SCOPES | UNASSIGNED_SCOPES
                if sales_deal_id is None
                else sales_deal_id in item.applicability.deal_ids
                or item.applicability.scope in COMMON_SCOPES
            )
        ]
        return {
            "evidence": items,
            "attachments": copy.deepcopy(source.attachments),
        }

    def read_deal_crm(sales_deal_id: UUID) -> dict[str, Any]:
        """딜 작성·수정 task에서 현재 미팅 근거와 함께 선택 딜의 CRM을 읽는다.

        선택된 ``sales_deal_id``의 딜·회사 배경을 ``crm_context``로 반환한다. 과거
        보고서와 다른 딜은 제외하며, 선택하지 않은 딜은 오류이고 DB나 외부 자료를
        조회하지 않는다.
        """
        if sales_deal_id not in source.evidence.selected_deal_ids:
            return {"error": "deal_not_selected"}
        crm = source.crm_context
        deals = crm.get("deals") if isinstance(crm.get("deals"), list) else []
        additional = (
            crm.get("additional_context") if isinstance(crm.get("additional_context"), list) else []
        )
        scoped = {
            key: copy.deepcopy(crm[key])
            for key in (
                "snapshot_at",
                "crm_time_basis",
                "activity",
                "company",
                "contact",
                "trade_history",
                "trade_history_metadata",
                "related_items_limit",
            )
            if key in crm
        }
        scoped["deals"] = [
            copy.deepcopy(item)
            for item in deals
            if isinstance(item, dict)
            and str(item.get("sales_deal_id") or item.get("id")) == str(sales_deal_id)
        ]
        scoped["additional_context"] = [
            copy.deepcopy(item)
            for item in additional
            if isinstance(item, dict)
            and item.get("kind") != "previous_reports"
            and str(item.get("sales_deal_id")) == str(sales_deal_id)
        ]
        return {"crm_context": scoped}

    def read_previous_reports(sales_deal_id: UUID) -> dict[str, Any]:
        """딜 작성·수정 task에서 현재 근거와 함께 같은 딜의 과거 보고서를 읽는다.

        선택된 ``sales_deal_id``의 동결 이력을 ``previous_reports``로 반환한다. 이전
        약속·변화의 배경일 뿐 이번 미팅의 발언 근거로 간주하면 안 되며, 선택하지 않은
        딜은 오류이다.
        """
        if sales_deal_id not in source.evidence.selected_deal_ids:
            return {"error": "deal_not_selected"}
        crm = source.crm_context
        histories = crm.get("previous_reports")
        histories = histories if isinstance(histories, list) else []
        additional = crm.get("additional_context")
        additional = additional if isinstance(additional, list) else []
        selected = [
            copy.deepcopy(item)
            for item in histories
            if isinstance(item, dict) and str(item.get("sales_deal_id")) == str(sales_deal_id)
        ]
        if not selected:
            selected = [
                copy.deepcopy(item["data"])
                for item in additional
                if isinstance(item, dict)
                and item.get("kind") == "previous_reports"
                and str(item.get("sales_deal_id")) == str(sales_deal_id)
                and isinstance(item.get("data"), dict)
            ]
        return {"previous_reports": selected}

    return [read_meeting_evidence, read_deal_crm, read_previous_reports]
