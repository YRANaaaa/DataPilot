from typing import Any
from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int
    message: str
    data: dict[str, Any] | None = None