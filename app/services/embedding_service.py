import json
from sentence_transformers import SentenceTransformer
from app.core.config import settings
from abc import ABC, abstractmethod


class BaseEmbeddingService(ABC):
    @abstractmethod
    def generate_embedding(self, text: str) -> list[float]:
        pass

    @abstractmethod
    def construct_user_document(
        self, career_interest: str | None, github_profile: str | None, estudent_profile: str | None
    ) -> str:
        """Combine all bits of user context into one big cohesive string to embed."""
        pass


class SentenceTransformerEmbeddingService(BaseEmbeddingService):
    def __init__(self, model_name: str = settings.EMBEDDING_MODEL_NAME):
        # By separating this out, you can easily mock it out in tests or swap to an OpenAI API
        self.model = SentenceTransformer(model_name)

    def generate_embedding(self, text: str) -> list[float]:
        # Encode the text to vector and convert from numpy to standard list
        embedding = self.model.encode(text)
        return embedding.tolist()

    def construct_user_document(
        self, career_interest: str | None, github_profile: str | None, estudent_profile: str | None
    ) -> str:
        """
        Extract only what's available and create a single paragraph text for embedding.
        """
        parts = []
        if career_interest and career_interest.strip():
            parts.append(f"Career Interest and Goals: {career_interest.strip()}")
            
        if github_profile and github_profile.strip():
            parts.append(f"GitHub Technical Profile & Projects: {github_profile.strip()}")
            
        if estudent_profile and estudent_profile.strip():
            parts.append(f"Educational Background (E-student): {estudent_profile.strip()}")
            
        # Default placeholder if profile is empty
        if not parts:
            return "General new user with no profile data yet."
            
        return "\n".join(parts)


# Easy dependency injection interface
def get_embedding_service() -> BaseEmbeddingService:
    return SentenceTransformerEmbeddingService()
