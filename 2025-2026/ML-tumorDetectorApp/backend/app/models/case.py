import datetime
from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import DateTime, String, Text, Enum, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.base import Base
import uuid
#we use server side datatypes
#IN DATABASE RUN :
#CREATE EXTENSION IF NOT EXISTS PGCRYPTO;

class Case(Base):
    __tablename__ = "cases"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    created_at : Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    display_name : Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        server_default=text("'Unnamed'")
    )
    has_tumor : Mapped[str] = mapped_column(
        Enum("YES", "NO", "UNDETERMINED", name="tumor_status"),
        nullable=False,
        server_default=text("'UNDETERMINED'")
    )
    expert_note : Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    #source type for either dicom, nifti, png, etc
    source_type : Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    #source_uri for finding where the object located
    
    #old
    """
    source_uri : Mapped[str] = mapped_column(
        String(255),
        nullable=True,
    )
    """
    #new :
    source_uris : Mapped[dict] = mapped_column(
        JSONB(),
        nullable = True,
    )

    """
    metadata_json dict structure :
    {
        "t1ce" : t1ce_metadata_json,
        "flair" : flair_metadata_json,
        "t1" : t1_metadata_json,
        "t2" : t2_metadata_json,
    } 
    """
    metadata_json : Mapped[dict] = mapped_column(
        JSONB(),
        nullable=False,
        server_default = text("'{}'::jsonb")
    )
    
    """
    metadata_status: Mapped[str] = mapped_column(
    String(25),
    nullable=False,
    server_default=text("'PENDING'")    
    """
    metadata_statuses: Mapped[dict] = mapped_column(
    JSONB(),
    nullable=False,
    server_default=text(
        "'{\"T1CE\":\"PENDING\",\"FLAIR\":\"PENDING\",\"T1\":\"PENDING\",\"T2\":\"PENDING\",\"SEG\":\"PENDING\"}'::jsonb"
    )
)

