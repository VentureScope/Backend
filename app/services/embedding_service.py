import json
import os
from typing import List
from abc import ABC, abstractmethod
from dotenv import load_dotenv

from langchain.embeddings.base import Embeddings
from openai import OpenAI

from app.core.config import settings

load_dotenv()


class HostedEmbeddings(Embeddings):
    def __init__(self, model_name=None, token=None):
        # Fallback to the settings embedding model name or the default one
        self.model_name = model_name or settings.EMBEDDING_MODEL_NAME or "openai/text-embedding-3-large"
        self.endpoint = os.getenv("END_POINT")
        if not self.endpoint:
            raise ValueError("END_POINT environment variable is not set.")
        self.token = token or os.getenv("HOSTED_LLM_TOKEN")
        if not self.token:
            raise ValueError("Missing API_KEY / HOSTED_LLM_TOKEN")
            
        self.client = OpenAI(base_url=self.endpoint, api_key=self.token)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(input=texts, model=self.model_name)
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


class BaseEmbeddingService(ABC):
    @abstractmethod
    def generate_embedding(self, text: str) -> list[float]:
        pass

    @abstractmethod
    def construct_user_document(
        self,
        career_interest: str | None,
        github_profile: str | None,
        estudent_profile: str | None,
        skills: list | None = None,
        cv_url: str | None = None,
    ) -> str:
        """Combine all bits of user context into one big cohesive string to embed."""
        pass


class HostedEmbeddingService(BaseEmbeddingService):
    def __init__(self, model_name: str = settings.EMBEDDING_MODEL_NAME):
        # We instantiate the user-provided class
        self.embeddings = HostedEmbeddings(model_name=model_name)

    def generate_embedding(self, text: str) -> list[float]:
        # Using embed_query directly from the Langchain wrapper
        return self.embeddings.embed_query(text)

    def construct_user_document(
        self,
        career_interest: str | None,
        github_profile: str | None,
        estudent_profile: str | None,
        skills: list | None = None,
        cv_url: str | None = None,
    ) -> str:
        """
        Extract only what's available and create a single paragraph text for embedding.
        """
        parts = []
        if career_interest and career_interest.strip():
            parts.append(f"Career Interest and Goals: {career_interest.strip()}")
        if skills and len(skills) > 0:
            skills_text = ", ".join(skills)
            parts.append(f"Skills: {skills_text}")
        if github_profile and github_profile.strip():
            parts.append(f"GitHub Technical Profile & Projects: {github_profile.strip()}")
        if estudent_profile and estudent_profile.strip():
            parts.append(f"Educational Background (E-student): {estudent_profile.strip()}")
        if cv_url:
            parts.append(f"CV uploaded and available for review")
        
        # Default placeholder if profile is empty
        if not parts:
            return "General new user with no profile data yet."
            
        return "\n".join(parts)


# Easy dependency injection interface
def get_embedding_service() -> BaseEmbeddingService:
    return HostedEmbeddingService()
