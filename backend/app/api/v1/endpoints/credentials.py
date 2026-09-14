from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.credentials_store import create_credential, list_credentials

router = APIRouter(prefix="/credentials", tags=["credentials"])


class CredentialSummary(BaseModel):
    id: str
    name: str
    type: str
    created_at: Optional[str] = None


class CreateCredentialBody(BaseModel):
    name: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    secret: str = ""


@router.get("", response_model=List[CredentialSummary])
def get_credentials(
    type: Optional[str] = Query(None, alias="type"),
) -> List[CredentialSummary]:
    return list_credentials(type)


@router.post("", response_model=CredentialSummary, status_code=201)
def post_credential(body: CreateCredentialBody) -> CredentialSummary:
    try:
        return create_credential(body.name, body.type, body.secret)
    except ValueError as exc:
        if str(exc) == "name_required":
            raise HTTPException(status_code=400, detail="Le nom est obligatoire.")
        if str(exc) == "type_required":
            raise HTTPException(status_code=400, detail="Le type est obligatoire.")
        raise
