from typing import List
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun, AsyncCallbackManagerForRetrieverRun
from langchain_core.documents import Document

from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.embedding_service import get_embedding_service


class UserKnowledgeRetriever(BaseRetriever):
    """
    Custom LangChain retriever that queries a specific user's Knowledge base.
    """
    user_id: str
    repo: KnowledgeRepository
    limit: int = 5
    
    # Exclude repo from Pydantic validations
    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Synchronous retrieval (Not strictly needed since we use async, but required by BaseRetriever interface)"""
        raise NotImplementedError("Use async retrieval instead: _aget_relevant_documents")

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Asynchronously get relevant documents for the user."""
        embedding_service = get_embedding_service()
        msg_embedding = embedding_service.generate_embedding(query)
        
        chunks = await self.repo.search_user_knowledge(
            user_id=self.user_id,
            query_embedding=msg_embedding,
            limit=self.limit
        )
        
        docs = []
        for chunk in chunks:
            doc = Document(
                page_content=chunk.content,
                metadata={"source_type": chunk.source_type}
            )
            docs.append(doc)
            
        return docs
