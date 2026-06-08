"""User configuration routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from workbench.core.auth import get_current_user
from workbench.core.models import User

router = APIRouter()


@router.get("/config")
async def get_config(user: Annotated[User, Depends(get_current_user)]):
    return {
        "theme": "dark",
        "username": user.username,
    }
