from app.models import Case
from app.core.db import get_db
from app.services.storage_s3 import get_s3_client
from app.core.config import settings

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

router = APIRouter()

#check liveness
@router.get("/debug/db")
def debug_db(db: Session = Depends(get_db)):
    test_case = Case(
        source_type = "NIFTI",
        source_uris = {"TEST_KEY":"TEST_SOURCE_URI"}
    )
    db.add(test_case)
    db.commit()
    db.refresh(test_case)
    found = db.get(Case, test_case.id)
    db.delete(found)
    db.commit()
    return {"inserted_id": str(test_case.id), "existed": found is not None, "deleted": True}


@router.get("/debug/s3")
def debug_s3():
    s3_client = get_s3_client()
    bucket = settings.S3_BUCKET
    key = "debug/hello.txt"
    message = f"Hello from {bucket}"
    body = message.encode("utf-8")

    #PUT
    try :
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="text/plain"
        )
    except Exception as e:
        return {
            "success" : False,
            "message" : "Failed saving file to storage minio",
            "e_message" : str(e),
        }
    #GET
    try :
        obj = s3_client.get_object(
            Bucket=bucket,
            Key=key,
        )
        data = obj["Body"].read().decode("utf-8")
    except Exception as e:
        return {
            "success" : False,
            "message" : "Failed getting file from storage minio",
            "e_message" : str(e),
        }

    return {"success" : True, "bucket": settings.S3_BUCKET, "key": key, "roundtrip": data}


#get all cases
@router.get("/debug/cases")
def list_cases(db : Session = Depends(get_db)):
    cases = db.query(Case).order_by(Case.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "created_at": c.created_at,
            "source_type": c.source_type,
            "source_uris": c.source_uris,
            "metadata_json": c.metadata_json,
            "metadata_statuses" : c.metadata_statuses,
        } for c in cases
    ]