"""
Evaluation API route — allows running and viewing empirical benchmarks.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.services.evaluation_service import run_evaluation

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.api_route("/run", methods=["GET", "POST"])
def get_evaluation_results(db: Session = Depends(get_db)):
    """Run baseline vs enhanced pipeline evaluation benchmark."""
    return run_evaluation(db)
