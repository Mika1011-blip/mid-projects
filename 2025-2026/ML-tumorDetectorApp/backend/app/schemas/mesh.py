from pydantic import BaseModel, Field
from typing import List


class MeshLayer(BaseModel):
    name: str
    space: str = Field(description="Coordinate space, e.g. 'voxel'")
    spacing: List[float]  # [sx, sy, sz]
    vertices: List[List[float]]
    faces: List[List[int]]

    class Config:
        frozen = True  # makes the model immutable, like dataclass(frozen=True)
