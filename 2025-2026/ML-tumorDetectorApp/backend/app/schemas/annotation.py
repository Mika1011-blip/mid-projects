from typing import Literal

from pydantic import BaseModel, Field


class AnnotationSlicePayload(BaseModel):
    axis: Literal["x", "y", "z"]
    k: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rle: list[int] = Field(default_factory=list)


class ApplySlicePayload(BaseModel):
    modality: str
    axis: Literal["x", "y", "z"]
    k: int = Field(ge=0)
    rot90: int = 0
    flip_x: bool = False
    flip_y: bool = False
    view_basis: list[list[int]] | None = None
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rle: list[int] = Field(default_factory=list)
    annotation_shape: list[int] | None = None
    annotation_slices: list[AnnotationSlicePayload] = Field(default_factory=list)
    run_pipeline_0: bool = True
