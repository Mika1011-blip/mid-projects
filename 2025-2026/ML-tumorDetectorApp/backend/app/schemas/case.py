from pydantic import BaseModel, Field
from typing import Dict, Optional, Any, Literal, List



class StringIn(BaseModel):
    str_input: str

class UploadedItem(BaseModel):
    modality: str
    object_key: str
    status: Literal["OK", "FAILED"]

class BatchIngestOut(BaseModel):
    case_id: str
    uploaded: List[UploadedItem]
    failed: Optional[List[UploadedItem]] = None