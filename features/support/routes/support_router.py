from fastapi import APIRouter, HTTPException
from ..models import SupportContactRequest, SupportContactResponse
from ..services import send_support_email


router = APIRouter(prefix="/v1/support", tags=["Support"])


@router.post("/contact", response_model=SupportContactResponse)
async def contact_support(request: SupportContactRequest) -> SupportContactResponse:
    """
    Submit a support request. Sends an email to admin@gt360.app.

    This endpoint is public and does not require authentication.
    """
    try:
        success = await send_support_email(
            name=request.name,
            email=request.email,
            category=request.category.value,
            subject=request.subject,
            message=request.message
        )

        if success:
            return SupportContactResponse(
                success=True,
                message="Your message has been sent successfully"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to send message. Please try again later."
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your request"
        )
