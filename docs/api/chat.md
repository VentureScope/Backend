# Real-Time AI Chat Documentation

## Overview
VentureScope features a fully interactive, real-time Personalized AI Chatbot. The chatbot utilizes a Retrieval-Augmented Generation (RAG) architecture built with **LangChain**, streaming LLM, and **pgvector**. It relies exclusively on the user's *own* specific profile data and uploaded knowledge—such as academic transcripts or Github overviews—to synthesize its responses, yielding highly specific personalized career and academic advice.

## Prerequisites
- A valid User JWT token.
- WebSockets compatible client.
- The user must have a configured `UserKnowledge` base (this happens automatically when users upload transcripts or edit their profiles).

---

## Architecture: How the RAG Pipeline Works

When the user asks a question, the backend executes an advanced LCEL (LangChain Expression Language) streaming pipeline:

1. **User Embedding**: The user's typed question is intercepted and passed to the `EmbeddingService`, returning a vector matrix matching the query's semantic meaning.
2. **Knowledge Retrieval (`UserKnowledgeRetriever`)**: The `KnowledgeRepository` queries PostgreSQL using pgvector's `cosine_distance` algorithm. It searches **only** for chunks tied to `user_id == current_user.id` that mathematically match the topic.
3. **Prompt Composition**: The `ChatService` builds a LangChain `ChatPromptTemplate` containing:
   - System instructions & base profile traits (Career Goal, Github handle).
   - Up to 20 messages of historical conversation context.
   - The *Retrieved Context* (e.g., specific grades matching their question).
4. **LLM Execution (`HostedLLM`)**: The custom LangChain LLM executes a remote call to the hosted large language model (e.g., `gpt-4o-mini`).
5. **WebSocket Streaming (`.astream`)**: Using LCEL, the pipeline streams text `GenerationChunk`s directly to the frontend WebSocket in real-time, giving a typing effect.
6. **Notifications**: Upon completion, the system stores the final generated content in the `chat_messages` table and optionally dispatches an event via the `NotificationService`.

---

## Integration Guide: How to Chat

To implement the chatbot in the frontend, you must orchestrate standard HTTP requests mixed with a WebSocket connection.

### 1. Create a Chat Session (HTTP)

Before chatting, users need an active dialogue session. 
*(If the user just wants to resume an old conversation, you can fetch existing sessions via `GET /api/chat/sessions` instead).*

**Endpoint:** `POST /api/chat/sessions`

**cURL Example:**
```bash
curl -X POST "http://localhost:8000/api/chat/sessions" \
     -H "Authorization: Bearer <YOUR_JWT_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"title": "Academic Advice"}'
```
**Response Details:** Returns a session ID. (e.g. `123e4567-e89b-12d3...`)

### 2. Connect to the WebSocket Stream (Real-Time)

To stream messages, connect your WebSocket using the standard `ws://` protocol. 
Because browsers cannot attach HTTP Authorization Headers to WebSocket handshakes, you must pass the JWT token as a **query parameter**.

**Endpoint:** `WS /api/chat/ws/{session_id}?token={JWT_TOKEN}`

**Frontend Example (JavaScript):**
```javascript
// Step A: Format URL
const sessionId = "123e4567-e89b-12d3-a456-426614174000";
const token = localStorage.getItem("jwt_token"); // your auth token
const wsUrl = `ws://localhost:8000/api/chat/ws/${sessionId}?token=${token}`;

// Step B: Connect and setup listeners
const socket = new WebSocket(wsUrl);

socket.onopen = () => {
    console.log("Chat streaming connected!");
    
    // Send a message to the AI
    socket.send("What classes did I take in 2023 and what were my grades?");
};

socket.onmessage = (event) => {
    // The event.data contains the text chunks!
    // Simply append these chunks sequentially to the UI 
    // to simulate a typing effect.
    document.getElementById("chat-box").innerHTML += event.data;
};

socket.onerror = (error) => {
    console.error("WebSocket Error: ", error);
};

socket.onclose = () => {
    console.log("Chat segment closed.");
};
```

### 3. Fetch Historical Messages (HTTP)

If a user reloads the page or selects a previous tab, you can fetch all previous dialogue chunks to render the UI before establishing the WebSocket for new messages.

**Endpoint:** `GET /api/chat/sessions/{session_id}/messages`

**cURL Example:**
```bash
curl -X GET "http://localhost:8000/api/chat/sessions/{session_id}/messages?limit=50" \
     -H "Authorization: Bearer <YOUR_JWT_TOKEN>"
```

### Notification Hooks

When the AI stream successfully completes and is saved to the database, a Notification object will be dispatched with type `chat_reply`. Users listening to the Global Notification WebSocket (`/api/chat/ws/notifications?token=...`) will be able to see that a reply was completed, even if they aren't actively on the chat screen!

## Troubleshooting

- **`403 Forbidden / Connection Rejected`**: Make sure your `?token=` parameter is a valid JWT. WebSockets will forcefully drop connections lacking valid signatures.
- **`500 LLM Errors`**: This usually indicates `END_POINT` and `HOSTED_LLM_TOKEN` variables are unset or invalid in your `.env` configuration.
- **Empty Retrieved Knowledge**: If the User hasn't uploaded a transcript or filled out their profile, `UserKnowledgeRetriever` will yield zero documents. The LLM will still respond normally but with generic context.
