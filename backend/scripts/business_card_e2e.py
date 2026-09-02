"""실제 명함 이미지로 OCR부터 고객·원본 보관까지 검증하는 로컬 E2E.

자격증명과 이미지 경로는 환경변수로만 받으며, OCR 결과의 개인정보는 출력하지 않습니다.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

BASE_URL = os.getenv("SALESLUV_E2E_BASE_URL", "http://127.0.0.1:8000/api")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"필수 환경변수가 없습니다: {name}")
    return value


def require(response: httpx.Response, endpoint: str) -> None:
    if response.is_error:
        raise RuntimeError(f"{endpoint} failed with status {response.status_code}")


def await_scan(client: httpx.Client, scan_id: str, *, timeout_seconds: float = 300.0) -> dict:
    """인식이 끝날 때까지 상태를 폴링한다. 화면이 쓰는 방식과 같다."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        response = client.get(f"/business-cards/scan/{scan_id}")
        require(response, "business_card_scan_status")
        body = response.json()
        processing_status = body.get("processing_status")
        if processing_status == "completed":
            return body
        if processing_status == "failed":
            raise RuntimeError(f"business card scan failed: {body.get('processing_error')}")
        time.sleep(1.0)
    raise RuntimeError("business card scan timed out")


def main() -> None:
    email = _required_env("SALESLUV_E2E_EMAIL")
    password = _required_env("SALESLUV_E2E_PASSWORD")
    card_path = Path(_required_env("SALESLUV_E2E_CARD_PATH"))
    if not card_path.is_file():
        raise SystemExit("SALESLUV_E2E_CARD_PATH가 파일을 가리키지 않습니다.")

    with httpx.Client(
        base_url=BASE_URL,
        timeout=httpx.Timeout(180.0, connect=15.0),
    ) as client:
        login = client.post("/auth/login", json={"email": email, "password": password})
        require(login, "login")
        session = login.json()
        print({"login_status": login.status_code, "session_received": bool(session.get("id"))})

        with card_path.open("rb") as image:
            scan = client.post(
                "/business-cards/scan",
                files={"image": (card_path.name, image, "image/jpeg")},
            )
        require(scan, "business_card_scan")
        # 스캔은 202로 접수만 하고, 결과는 폴링으로 받는다.
        draft = await_scan(client, scan.json()["scan_id"])
        fields = draft.get("fields") or {}
        field_names = ("name", "company_name", "department", "job_title", "email", "phone")
        print(
            {
                "scan_status": scan.status_code,
                "scan_processing_status": draft.get("processing_status"),
                "ocr_fields_present": {name: bool(fields.get(name)) for name in field_names},
            }
        )

        required = (fields.get("name"), fields.get("company_name"), fields.get("phone"))
        if not all(required):
            raise RuntimeError("OCR required fields are incomplete")

        companies_response = client.get("/customer-companies", params={"skip": 0, "limit": 100})
        require(companies_response, "list_companies")
        companies = companies_response.json().get("items", [])
        company = next(
            (
                item
                for item in companies
                if item.get("name", "").strip().casefold()
                == fields["company_name"].strip().casefold()
            ),
            None,
        )
        company_created = False
        if company is None:
            company_response = client.post(
                "/customer-companies", json={"name": fields["company_name"]}
            )
            require(company_response, "create_company")
            company = company_response.json()
            company_created = True

        customer_response = client.post(
            "/customer-contacts",
            json={
                "company_id": company["id"],
                "name": fields["name"],
                "department": fields.get("department") or None,
                "job_title": fields.get("job_title") or None,
                "email": fields.get("email") or None,
                "phone": fields["phone"],
                "source_code": None,
                "memo": "실제 명함 OCR E2E 테스트",
                "visited": False,
                "assignee_member_ids": [session["id"]],
            },
        )
        require(customer_response, "create_customer")
        customer = customer_response.json()

        with card_path.open("rb") as image:
            archive = client.post(
                "/business-cards/archive",
                data={"contact_id": customer["id"]},
                files={"image": (card_path.name, image, "image/jpeg")},
            )
        require(archive, "archive_business_card")
        archived = archive.json()
        print(
            {
                "e2e": "passed",
                "company_created": company_created,
                "customer_created": bool(customer.get("id")),
                "archive_document_created": bool(archived.get("id")),
                "archive_customer_linked": archived.get("customer_contact_id")
                == customer.get("id"),
            }
        )


if __name__ == "__main__":
    main()
