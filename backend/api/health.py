from fastapi import APIRouter, Depends
from auth.security import get_current_user

router = APIRouter(prefix="/api/health", tags=["Health"])

@router.get("/")
def health_check():
    return {"status": "ok"}

@router.get("/protected")
def protected_health_check(user_id: str = Depends(get_current_user)):
    return {
        "status": "ok",
        "message": "Authenticated successfully",
        "user_id": user_id
    }
