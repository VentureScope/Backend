"""
Chat Service – Personalized RAG chatbot.

Flow per WebSocket message:
  1. Save user message to DB
  2. Instantiate LangChain Retriever (UserKnowledgeRetriever) and fetch relevant documents
  3. Build a LangChain ChatPromptTemplate with system context and message history
  4. Instantiate custom LangChain HostedLLM
  5. Stream LLM response back chunk-by-chunk using LCEL `.astream()`
  6. Save the complete assistant message to DB
  7. Fire a notification
"""

import logging
from typing import Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.documents import Document

from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.repositories.chat_repository import ChatRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.notification_service import NotificationService
from app.services.embedding_service import get_embedding_service
from app.services.hosted_llm import HostedLLM
from app.services.knowledge_retriever import UserKnowledgeRetriever

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Helper: build the personalized system prompt from user profile
# ─────────────────────────────────────────────────────────────

def _build_system_prompt(user: User, relevant_knowledge_context: str) -> str:
    """
    Construct a rich system prompt grounded in the user's actual profile data
    AND relevant knowledge chunks found from the database.
    """
    lines = [
        "You are a personalized career and academic assistant for the VentureScope platform.",
        "You have access to the following verified information about the user you are talking to.",
        "Always tailor your answers to their specific background, goals, and academic record.",
        "",
        "=== CORE USER PROFILE ===",
    ]

    if user.full_name:
        lines.append(f"Name: {user.full_name}")

    if user.career_interest:
        lines.append(f"Career Interest & Goals: {user.career_interest}")

    if user.github_username:
        lines.append(f"GitHub Username: {user.github_username}")

    if user.role:
        lines.append(f"Account Role: {user.role}")

    if relevant_knowledge_context:
        lines += [
            "",
            "=== RETRIEVED USER KNOWLEDGE ===",
            "The following are detailed pieces of information specific to the user (e.g., from their academic transcript or uploaded documents) that match their query:",
            relevant_knowledge_context,
        ]

    lines += [
        "",
        "=== INSTRUCTIONS ===",
        "- Answer ONLY based on what you know about this user from the profile and retrieved knowledge above.",
        "- Be encouraging, specific, and actionable.",
        "- If the user asks something you cannot answer from their profile or the knowledge base, say so honestly.",
        "- Do NOT invent personal details or academic grades not listed above.",
        "- Keep replies concise unless the user asks for detail.",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# ChatService
# ─────────────────────────────────────────────────────────────

class ChatService:
    """Handles all chat business logic: persistence, RAG context, LangChain execution."""

    # Number of previous messages to include as conversation context
    HISTORY_LIMIT = 20

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ChatRepository(db)
        self.knowledge_repo = KnowledgeRepository(db)
        self.notification_service = NotificationService(db)

    # ────────────── Session CRUD ──────────────

    async def create_session(self, user_id: str, title: str = "New Chat") -> ChatSession:
        return await self.repo.create_session(user_id=user_id, title=title)

    async def list_sessions(
        self, user_id: str, page: int = 1, per_page: int = 20
    ) -> tuple[list[ChatSession], int]:
        skip = (page - 1) * per_page
        sessions = await self.repo.list_sessions(user_id, skip=skip, limit=per_page)
        total = await self.repo.count_sessions(user_id)
        return sessions, total

    async def get_session(self, session_id: str, user_id: str) -> ChatSession:
        session = await self.repo.get_session(session_id, user_id)
        if not session:
            raise ValueError("Chat session not found")
        return session

    async def rename_session(
        self, session_id: str, user_id: str, title: str
    ) -> ChatSession:
        session = await self.repo.get_session_bare(session_id, user_id)
        if not session:
            raise ValueError("Chat session not found")
        return await self.repo.update_session_title(session, title)

    async def delete_session(self, session_id: str, user_id: str) -> None:
        session = await self.repo.get_session_bare(session_id, user_id)
        if not session:
            raise ValueError("Chat session not found")
        await self.repo.delete_session(session)

    # ────────────── Core chat logic ──────────────

    def _format_knowledge_documents(self, docs: list[Document]) -> str:
        if not docs:
            return ""
        
        parts = []
        for d in docs:
            source = d.metadata.get("source_type", "unknown")
            parts.append(f"[Source: {source}]:\n{d.page_content}\n---")
        return "\n".join(parts)

    async def stream_reply(
        self,
        user: User,
        session_id: str,
        user_message: str,
        on_chunk: Callable[[str], Awaitable[None]],
    ) -> ChatMessage:
        """
        Main entry point called from the WebSocket handler, now using LangChain LCEL.
        """
        # 1. Verify session ownership
        session = await self.repo.get_session_bare(session_id, user.id)
        if not session:
            raise ValueError("Chat session not found or access denied")

        # 2. Save user message
        await self.repo.add_message(session_id, role="user", content=user_message)

        # 3. Vector query on the user's message using LangChain Retriever
        try:
            retriever = UserKnowledgeRetriever(user_id=user.id, repo=self.knowledge_repo)
            docs = await retriever.ainvoke(user_message)
            relevant_context = self._format_knowledge_documents(docs)
        except Exception as e:
            logger.warning(f"Failed to perform vector search with LangChain retriever: {e}")
            relevant_context = ""

        # 4. Load conversation history and convert to LangChain generic messages
        history = await self.repo.get_messages(session_id, limit=self.HISTORY_LIMIT)
        lc_history = []
        for msg in history:
            if msg.role == "user":
                lc_history.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                lc_history.append(AIMessage(content=msg.content))

        # 5. Build LangChain ChatPromptTemplate
        system_prompt = _build_system_prompt(user, relevant_context)
        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{question}"),
        ])

        # 6. Stream using LCEL pipeline mapping HostedLLM
        llm = HostedLLM()
        chain = prompt_template | llm
        
        full_reply = ""
        try:
            # Execute async streaming through LCEL pipeline
            async for chunk in chain.astream({"question": user_message, "history": lc_history}):
                if chunk:
                    full_reply += str(chunk)
                    await on_chunk(str(chunk))
        except Exception as e:
            logger.error(f"LangChain streaming error for session={session_id}: {e}")
            raise RuntimeError(f"LangChain error: {e}") from e

        # 7. Persist the complete assistant reply
        assistant_msg = await self.repo.add_message(
            session_id, role="assistant", content=full_reply
        )

        # 8. Create notification
        try:
            await self.notification_service.create_chat_reply_notification(
                user_id=user.id,
                session_id=session_id,
                message_id=assistant_msg.id,
                preview=full_reply,
            )
        except Exception as e:
            logger.warning(f"Notification creation failed: {e}")

        return assistant_msg
