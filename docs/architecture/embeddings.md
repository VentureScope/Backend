# User Embeddings Architecture

## Overview
This document explains how user data (career interests, GitHub profile, and E-student backgrounds) is combined, embedded, and stored to enable fast and mathematically accurate similarity searches.

## Technologies Used
- **Sentence-Transformers**: A Python library that gives us access to pre-trained, lightweight ML models (we default to `all-MiniLM-L6-v2`) to turn text into embeddings.
- **pgvector**: A PostgreSQL extension that natively indexes and compares vectors (such as `cosine_distance`).

## Schema Design
The `User` model (`app/models/user.py`) has been upgraded with two new fields:
1. `estudent_profile` (`String(1000)`): Represents educational data coming in from the external E-student system.
2. `embedding` (`Vector(384)`): Stores the generated 384-dimensional array of floats. 

## Embedding Service
We implemented the `SentenceTransformerEmbeddingService` in `app/services/embedding_service.py` to abstract the generation of embeddings.

When a user is created (`AuthService.register`) or updated (`UserService.update_profile` / `UserService.admin_update_user`), the service performs the following standard routine:
1. **Combine Data**: It fetches the user's `career_interest`, `github_username` (which could be expanded to fetch full GitHub bio details), and `estudent_profile`.
2. **Text Normalization**: It collapses these strings into a single, cohesive paragraph.
3. **Encoding**: The `sentence-transformers` model creates a mathematical representation (a 384-dimension vector) describing the meaning of that paragraph.
4. **Storage**: The vector is placed directly on the `User.embedding` database column.

## Similarity Search
To find users who are similar to one another:
1. Turn a target string (or target user's context) into a query vector using the same `embedding_service`.
2. Hit the PostgreSQL database using SQL `user.embedding.cosine_distance(query_vector)`.
3. Database filters out the target user and sorts all others by the smallest distance.

## Setup Requirements

### 1. Supabase / PostgreSQL Setup
Locally or in Supabase, you must enable `pgvector`:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. Python Packages
Since we added AI models, ensure your `.venv` is updated:
```bash
pip install -r requirements.txt
```

### 3. Migrating
Be sure to generate and commit the database migration:
```bash
alembic revision --autogenerate -m "Add estudent_profile and pgvector embeddings"
alembic upgrade head
```
