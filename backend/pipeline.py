"""
Person 1 Complete Pipeline Orchestrator.
Flow: Input Image -> Face Processing (Detection/Alignment/Embedding) -> Genuine Web Search -> Candidate Results
"""

import logging
from pathlib import Path
from typing import List, Union, Optional
from pydantic import BaseModel, Field

from backend.face import FaceProcessor, FaceDetectionResult, NoFaceDetectedError
from backend.search import BaseSearchProvider, SerpApiGoogleLensProvider, CandidateResult

logger = logging.getLogger(__name__)


class Person1Result(BaseModel):
    """
    Standard output payload for Person 1 module.
    Delivers face detection/embedding data + reverse web search candidates to Person 2.
    """
    input_image_path: str = Field(description="Path to input image file")
    primary_face: FaceDetectionResult = Field(description="Primary face detection & 512-d embedding")
    detected_faces_count: int = Field(description="Total number of faces detected in input image")
    candidates: List[CandidateResult] = Field(description="List of reverse-search candidate results")


class Person1Pipeline:
    """
    Complete Person 1 Pipeline combining Face Processing and Web Reverse-Search.
    """

    def __init__(
        self,
        face_processor: Optional[FaceProcessor] = None,
        search_provider: Optional[BaseSearchProvider] = None,
    ):
        """
        Initialize Person 1 Pipeline.

        :param face_processor: Custom FaceProcessor instance. Defaults to InsightFace FaceProcessor().
        :param search_provider: Custom BaseSearchProvider instance. Defaults to SerpApiGoogleLensProvider().
        """
        self.face_processor = face_processor or FaceProcessor()
        self.search_provider = search_provider or SerpApiGoogleLensProvider()

    def run(
        self, 
        image_path: Union[str, Path], 
        max_search_results: int = 10
    ) -> Person1Result:
        """
        Execute Person 1 End-to-End Workflow.

        :param image_path: Local file path of input image.
        :param max_search_results: Maximum candidates to retrieve from search engine.
        :return: Person1Result object containing face embedding data and candidate search list.
        :raises NoFaceDetectedError: If no face is detected in the input image.
        """
        path = Path(image_path)
        logger.info(f"Starting Person 1 Pipeline for image: {path.name}")

        # Step 1: Detect, Align, and Embed Face
        all_faces = self.face_processor.process_image(path)
        if not all_faces:
            raise NoFaceDetectedError(f"No face detected in input image '{path.name}'. Pipeline aborted.")

        primary_face = all_faces[0]
        logger.info(
            f"Face processing complete. Detected {len(all_faces)} face(s). "
            f"Primary face score: {primary_face.det_score:.2f}, embedding dim: {len(primary_face.embedding)}"
        )

        # Step 2: Genuine Web Reverse Image Search
        logger.info("Initiating web reverse-image search...")
        candidates = self.search_provider.search(path, max_results=max_search_results)
        logger.info(f"Web search complete. Found {len(candidates)} candidate(s).")

        return Person1Result(
            input_image_path=str(path.resolve()),
            primary_face=primary_face,
            detected_faces_count=len(all_faces),
            candidates=candidates,
        )
