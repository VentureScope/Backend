"""
OrgChatService — AI advisor chat scoped to an organization.

Each member has private sessions. The system prompt is built from:
  - The organization's profile (industry, description, core services, team aggregate)
  - Vector search across ALL org members' user_knowledge chunks
  - Active org roadmaps and team progress

Uses the same HostedLLM + LangGraph ReAct agent as the personal ChatService.
"""

import logging
import uuid
from typing import Callable, Awaitable
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.documents import Document

from app.models.org_chat import OrgChatSession, OrgChatMessage
from app.models.organization import Organization, OrganizationMember
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.organization_repository import OrganizationRepository
from app.services.hosted_llm import HostedLLM
from app.services.search_service import perform_web_search
from app.services.embedding_service import get_embedding_service
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def _build_org_system_prompt(
    org: Organization,
    members: list,
    roadmaps_context: str,
    knowledge_context: str,
) -> str:
    lines = [
        f"You are the AI advisor for {org.display_name}, an organization on VentureScope.",
        "You have access to verified information about this organization and its team.",
        "Give specific, grounded, and actionable advice tailored to this organization.",
        "",
        "=== ORGANIZATION PROFILE ===",
        f"Name: {org.display_name}",
    ]

    if org.industry:
        lines.append(f"Industry: {org.industry}")
    if org.description:
        lines.append(f"Description: {org.description}")
    if org.tagline:
        lines.append(f"Tagline: {org.tagline}")
    if org.core_services:
        services = org.core_services if isinstance(org.core_services, list) else []
        if services:
            lines.append(f"Core Services: {', '.join(str(s) for s in services)}")
    if org.website_url:
        lines.append(f"Website: {org.website_url}")
    if org.github_orgs:
        gh_orgs = org.github_orgs if isinstance(org.github_orgs, list) else []
        names = [g.get("name", "") if isinstance(g, dict) else str(g) for g in gh_orgs]
        if names:
            lines.append(f"GitHub Organizations: {', '.join(names)}")

    # Team aggregate
    all_skills = [
        skill
        for m in members
        for skill in (m.user.skills or [])
        if m.user
    ]
    top_skills = [s for s, _ in Counter(all_skills).most_common(10)]

    all_interests = [
        m.user.career_interest
        for m in members
        if m.user and m.user.career_interest
    ]
    top_interests = [i for i, _ in Counter(all_interests).most_common(5)]

    lines += [
        "",
        "=== TEAM INTELLIGENCE ===",
        f"Headcount: {len(members)} members",
    ]
    if top_skills:
        lines.append(f"Top Skills Across Team: {', '.join(top_skills)}")
    if top_interests:
        lines.append(f"Common Career Interests: {', '.join(top_interests)}")

    if roadmaps_context:
        lines += [
            "",
            "=== ACTIVE LEARNING ROADMAPS ===",
            roadmaps_context,
        ]

    if knowledge_context:
        lines += [
            "",
            "=== RETRIEVED TEAM KNOWLEDGE ===",
            "The following are relevant facts from team members' profiles, "
            "transcripts, and CVs that match the current question:",
            knowledge_context,
        ]

    lines += [
        "",
        "=== INSTRUCTIONS ===",
        "- Advise the organization as a whole, not just one member.",
        "- Use team knowledge to give specific, grounded recommendations.",
        "- Focus on team strengths, skill gaps, and growth opportunities.",
        "- When referencing member data, use aggregated info — don't name individuals.",
        "- Be concise unless the user asks for detail.",
        "- If you need current market data, use the web search tool.",
    ]

    return "\n".join(lines)


def _format_knowledge_docs(docs: list) -> str:
    if not docs:
        return ""
    parts = []
    for d in docs:
        source = d.metadata.get("source_type", "unknown")
        parts.append(f"[Source: {source}]:\n{d.page_content}\n---")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# OrgChatRepository (inline — keeps things simple)
# ---------------------------------------------------------------------------

class OrgChatRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_session(
        self, org_id: str, user_id: str, title: str = "New Chat"
    ) -> OrgChatSession:
        session = OrgChatSession(
            id=str(uuid.uuid4()),
            org_id=org_id,
            created_by=user_id,
            title=title,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def get_session(
        self, session_id: str, user_id: str
    ) -> OrgChatSession | None:
        result = await self.db.execute(
            select(OrgChatSession).where(
                OrgChatSession.id == session_id,
                OrgChatSession.created_by == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_sessions(
        self, org_id: str, user_id: str, skip: int = 0, limit: int = 20
    ) -> list[OrgChatSession]:
        result = await self.db.execute(
            select(OrgChatSession)
            .where(
                OrgChatSession.org_id == org_id,
                OrgChatSession.created_by == user_id,
            )
            .order_by(OrgChatSession.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_sessions(self, org_id: str, user_id: str) -> int:
        from sqlalchemy import func
        result = await self.db.execute(
            select(func.count(OrgChatSession.id)).where(
                OrgChatSession.org_id == org_id,
                OrgChatSession.created_by == user_id,
            )
        )
        return result.scalar_one()

    async def update_title(self, session: OrgChatSession, title: str) -> OrgChatSession:
        session.title = title
        await self.db.flush()
        return session

    async def delete_session(self, session: OrgChatSession) -> None:
        await self.db.delete(session)
        await self.db.flush()

    async def add_message(
        self,
        session_id: str,
        user_id: str | None,
        role: str,
        content: str,
    ) -> OrgChatMessage:
        msg = OrgChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
        )
        self.db.add(msg)
        await self.db.flush()
        return msg

    async def get_messages(
        self, session_id: str, limit: int = 20
    ) -> list[OrgChatMessage]:
        result = await self.db.execute(
            select(OrgChatMessage)
            .where(OrgChatMessage.session_id == session_id)
            .order_by(OrgChatMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# OrgChatService
# ---------------------------------------------------------------------------

class OrgChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrgChatRepository(db)
        self.knowledge_repo = KnowledgeRepository(db)
        self.org_repo = OrganizationRepository(db)

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    async def create_session(
        self, org_id: str, user_id: str, title: str = "New Chat"
    ) -> OrgChatSession:
        await self._assert_member(org_id, user_id)
        session = await self.repo.create_session(org_id, user_id, title)
        await self.db.commit()
        return session

    async def list_sessions(
        self, org_id: str, user_id: str, page: int = 1, per_page: int = 20
    ) -> tuple[list[OrgChatSession], int]:
        await self._assert_member(org_id, user_id)
        skip = (page - 1) * per_page
        sessions = await self.repo.list_sessions(org_id, user_id, skip=skip, limit=per_page)
        total = await self.repo.count_sessions(org_id, user_id)
        return sessions, total

    async def get_session(
        self, org_id: str, session_id: str, user_id: str
    ) -> OrgChatSession:
        await self._assert_member(org_id, user_id)
        session = await self.repo.get_session(session_id, user_id)
        if not session or session.org_id != org_id:
            raise ValueError("Chat session not found.")
        return session

    async def rename_session(
        self, org_id: str, session_id: str, user_id: str, title: str
    ) -> OrgChatSession:
        session = await self.get_session(org_id, session_id, user_id)
        return await self.repo.update_title(session, title)

    async def delete_session(
        self, org_id: str, session_id: str, user_id: str
    ) -> None:
        session = await self.get_session(org_id, session_id, user_id)
        await self.repo.delete_session(session)
        await self.db.commit()

    # ------------------------------------------------------------------
    # Core streaming logic
    # ------------------------------------------------------------------

    async def stream_reply(
        self,
        org_id: str,
        user_id: str,
        session_id: str,
        user_message: str,
        on_chunk: Callable[[str], Awaitable[None]],
    ) -> OrgChatMessage:
        """
        Main entry point called from the WebSocket handler.
        Builds org-scoped RAG context and streams LangGraph reply.
        """
        # 1. Validate session and membership
        session = await self.repo.get_session(session_id, user_id)
        if not session or session.org_id != org_id:
            raise ValueError("Chat session not found or access denied.")

        # 2. Save user message
        await self.repo.add_message(session_id, user_id, "user", user_message)

        # 3. Load org + members
        org = await self.org_repo.get_by_id(org_id)
        if not org:
            raise ValueError("Organization not found.")
        members = org.members or []
        member_user_ids = [m.user_id for m in members]

        # 4. Vector search across all members' knowledge
        knowledge_context = ""
        try:
            embedding_service = get_embedding_service()
            import asyncio
            query_embedding = await asyncio.to_thread(
                embedding_service.generate_embedding, user_message
            )
            docs = await self.knowledge_repo.search_across_users(
                user_ids=member_user_ids,
                query_embedding=query_embedding,
                limit=15,
            )
            knowledge_context = _format_knowledge_docs([
                Document(
                    page_content=d.content,
                    metadata={"source_type": d.source_type, "user_id": d.user_id}
                )
                for d in docs
            ])
        except Exception as e:
            logger.warning("Org knowledge search failed: %s", e)

        # 5. Build roadmaps context
        roadmaps_context = await self._build_roadmaps_context(org_id, member_user_ids)

        # 6. Build system prompt
        system_prompt = _build_org_system_prompt(
            org=org,
            members=members,
            roadmaps_context=roadmaps_context,
            knowledge_context=knowledge_context,
        )

        # 7. Load conversation history
        history = await self.repo.get_messages(session_id, limit=HISTORY_LIMIT)
        lc_history = [
            HumanMessage(content=m.content) if m.role == "user"
            else AIMessage(content=m.content)
            for m in history
        ]

        # 8. Stream via LangGraph ReAct agent
        llm = HostedLLM()
        agent = create_react_agent(
            model=llm,
            tools=[perform_web_search],
            prompt=system_prompt,
        )

        messages = lc_history + [HumanMessage(content=user_message)]
        full_reply = ""

        try:
            async for event in agent.astream_events({"messages": messages}, version="v2"):
                if event["event"] == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if getattr(chunk, "content", None):
                        text = str(chunk.content)
                        full_reply += text
                        await on_chunk(text)
        except Exception as e:
            logger.error("LangGraph streaming error for org session %s: %s", session_id, e)
            raise RuntimeError(f"AI service error: {e}") from e

        # 9. Persist reply
        assistant_msg = await self.repo.add_message(
            session_id, None, "assistant", full_reply
        )
        await self.db.commit()
        return assistant_msg

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _assert_member(self, org_id: str, user_id: str) -> None:
        from fastapi import HTTPException
        if not await self.org_repo.is_member(org_id, user_id):
            raise HTTPException(
                status_code=403,
                detail="You are not a member of this organization.",
            )

    async def _build_roadmaps_context(
        self, org_id: str, member_user_ids: list[str]
    ) -> str:
        """Build a short text summary of all active org roadmaps and team progress."""
        try:
            org_roadmaps = await self.org_repo.list_org_roadmaps(org_id)
            if not org_roadmaps:
                return ""

            lines = []
            for org_rm in org_roadmaps:
                r = org_rm.roadmap
                total_steps = len(r.steps)
                if total_steps == 0:
                    continue

                from statistics import mean
                pcts = []
                for uid in member_user_ids:
                    completed = sum(
                        1 for step in r.steps
                        if any(
                            p.user_id == uid and p.status == "completed"
                            for p in step.progress
                        )
                    )
                    pcts.append(round(completed / total_steps * 100, 1))

                agg = round(mean(pcts), 1) if pcts else 0.0
                lines.append(
                    f"- {r.title} ({r.trend_name or 'General'}): "
                    f"{agg}% team completion"
                )

            return "\n".join(lines)
        except Exception as e:
            logger.warning("Failed to build roadmaps context: %s", e)
            return ""
