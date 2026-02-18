"""
Tax router - Driver endpoints for tax information and 1099 forms.
Handles W-9 submission and 1099 retrieval.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from psqlmodel import AsyncSession
from typing import Optional
from uuid import UUID

from shared.db.db_config import get_db
from features.auth.utils import verify_role
from features.drivers.services.tax_service import (
    submit_tax_information,
    calculate_1099_data,
    mask_tin
)
from features.drivers.services.receipt_upload_service import upload_w9_document


router = APIRouter(prefix="/v1/drivers", tags=["Driver Tax & 1099"])


@router.post("/{driver_id}/tax-information")
async def submit_driver_tax_info(
    driver_id: str,
    legal_first_name: str = Form(...),
    legal_middle_name: Optional[str] = Form(None),
    legal_last_name: str = Form(...),
    tin_type: str = Form(...),
    tin: str = Form(...),
    address_street: str = Form(...),
    address_city: str = Form(...),
    address_state: str = Form(...),
    address_zip: str = Form(...),
    address_country: str = Form("US"),
    w9_document: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    Submit W-9 tax information for a driver.

    Form data:
    - legal_first_name, legal_middle_name, legal_last_name
    - tin_type: 'SSN' or 'EIN'
    - tin: SSN (XXX-XX-XXXX) or EIN (XX-XXXXXXX)
    - address_street, address_city, address_state (2 letters), address_zip
    - address_country: default 'US'
    - w9_document: PDF of signed W-9 form (max 5MB)

    Validations:
    - TIN format must match type
    - State must be 2-letter code
    - W-9 document must be PDF
    - Driver can only submit once (no duplicates)
    """
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Upload W-9 document
    w9_url = await upload_w9_document(w9_document, driver_uuid)

    # Submit tax information
    tax_info = await submit_tax_information(
        session,
        driver_uuid,
        tin_type,
        tin,
        legal_first_name,
        legal_middle_name,
        legal_last_name,
        address_street,
        address_city,
        address_state,
        address_zip,
        address_country,
        w9_url
    )

    # Build response
    full_name = f"{tax_info.legal_first_name} {tax_info.legal_middle_name or ''} {tax_info.legal_last_name}".strip()
    full_address = f"{tax_info.address_street}, {tax_info.address_city}, {tax_info.address_state} {tax_info.address_zip}"

    return {
        "status": "ok",
        "message": "Tax information submitted successfully",
        "tax_info": {
            "tax_info_id": str(tax_info.id),
            "driver_id": str(tax_info.driver_id),
            "tin_type": tax_info.tin_type,
            "tin_masked": mask_tin(tax_info.tin),
            "legal_name": full_name,
            "address": full_address,
            "w9_submitted": tax_info.w9_submitted,
            "w9_document_url": tax_info.w9_document_url
        }
    }


@router.get("/{driver_id}/1099")
async def get_driver_1099(
    driver_id: str,
    year: int,
    format: str = "json",
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    Get 1099-NEC form data for a driver.

    Query parameters:
    - year: Tax year (e.g., 2026) - required
    - format: 'json' or 'pdf' (default 'json')

    Returns:
    - Complete 1099-NEC form data
    - Earnings breakdown
    - Expenses summary (not included in 1099)
    - Compliance information

    Requirements:
    - Driver must have submitted W-9 (tax information)
    - Earnings must be >= $600 for the year
    - Year cannot be in the future
    """
    try:
        driver_uuid = UUID(driver_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid driver ID")

    # Validate format
    if format not in ['json', 'pdf']:
        raise HTTPException(
            status_code=400,
            detail="Invalid format. Must be 'json' or 'pdf'"
        )

    # Calculate 1099 data
    form_data = await calculate_1099_data(session, driver_uuid, year)

    if format == 'json':
        return JSONResponse(content=form_data)

    elif format == 'pdf':
        # TODO: Generate PDF
        # For now, return JSON with message
        return JSONResponse(content={
            "message": "PDF generation not yet implemented",
            "data": form_data
        })
