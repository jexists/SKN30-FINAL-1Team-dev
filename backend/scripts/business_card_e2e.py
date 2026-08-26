"""실제 명함 이미지로 OCR부터 고객·원본 보관까지 검증하는 로컬 E2E.

자격증명과 이미지 경로는 환경변수로만 받으며, OCR 결과의 개인정보는 출력하지 않습니다.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

BASE_URL = os.getenv("SALESLUV_E2E_BASE_URL", "http://127.0.0.1:8000/api")
EMAIL = os.environ["SALESLUV_E2E_EMAIL"]
PASSWORD = os.environ["SALESLUV_E2E_PASSWORD"]
CARD_PATH = Path(os.environ["SALESLUV_E2E_CARD_PATH"])


def require(response: httpx.Response, endpoint: str) -> None:
    if response.is_error:
        raise RuntimeError(f"{endpoint} failed with status {response.status_code}")


def main() -> None:
    with httpx.Client(
        base_url=BASE_URL,
        timeout=httpx.Timeout(180.0, connect=15.0),
    ) as client:
        login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        require(login, "login")
        session = login.json()
        print({"login_status": login.status_code, "session_received": bool(session.get("id"))})

        with CARD_PATH.open("rb") as image:
            scan = client.post(
                "/business-cards/scan",
                files={"image": (CARD_PATH.name, image, "image/jpeg")},
            )
        require(scan, "business_card_scan")
        draft = scan.json()
        fields = draft.get("fields", {})
        field_names = ("name", "company_name", "department", "job_title", "email", "phone")
        print(
            {
                "scan_status": scan.status_code,
                "ocr_fields_present": {name: bool(fields.get(name)) for name in field_names},
                "match_count": len(draft.get("matches", [])),
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

        with CARD_PATH.open("rb") as image:
            archive = client.post(
                "/business-cards/archive",
                data={"contact_id": customer["id"]},
                files={"image": (CARD_PATH.name, image, "image/jpeg")},
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
