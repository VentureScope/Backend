"""
Import jobs from CSV file into the database.

Usage:
    python scripts/import_jobs_csv.py <csv_file_path>

The CSV should have columns: job_id, company_name, job_title, normalized_title,
DescriptionVec, city, region, country, is_remote, job_type, education_level, skills,
year_month, timestamp
"""

import csv
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from app.core.config import settings


def get_sync_engine():
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+pg8000://")
    url = url.split("?")[0]
    return create_engine(url, poolclass=NullPool)


def parse_description_vec(raw: str) -> list[float] | None:
    if not raw or raw.strip() == "":
        return None
    try:
        cleaned = raw.strip().strip('"').strip("'")
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None


def parse_skills(raw: str) -> list | None:
    if not raw or raw.strip() == "":
        return None
    cleaned = raw.strip().strip('"').strip("'")
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        parts = [s.strip() for s in cleaned.split(",") if s.strip()]
        return parts if parts else None


def parse_bool(raw: str) -> bool | None:
    if not raw or raw.strip() == "":
        return None
    return raw.strip().lower() in ("true", "1", "yes")


def parse_timestamp(raw: str) -> datetime | None:
    if not raw or raw.strip() == "":
        return None
    try:
        return datetime.fromisoformat(raw.strip().strip('"'))
    except (ValueError, TypeError):
        return None


def import_csv(filepath: str) -> dict:
    engine = get_sync_engine()

    insert_sql = text("""
        INSERT INTO jobs (
            id, job_id, company_name, job_title, normalized_title,
            description, embedding, city, region, country,
            is_remote, job_type, education_level, skills,
            source, posted_date, created_at
        ) VALUES (
            gen_random_uuid()::text, :job_id, :company_name, :job_title, :normalized_title,
            :description, CAST(:embedding AS vector), :city, :region, :country,
            :is_remote, :job_type, :education_level, CAST(:skills AS jsonb),
            'manual_csv', :posted_date, NOW()
        )
        ON CONFLICT (job_id) DO NOTHING
    """)

    inserted = 0
    skipped = 0
    errors = 0
    batch = []
    batch_size = 20

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader, start=2):
            try:
                job_id = row.get("job_id", "").strip()
                if not job_id:
                    errors += 1
                    continue

                embedding = parse_description_vec(row.get("DescriptionVec", ""))
                if embedding is not None and len(embedding) != 384:
                    print(f"  Warning row {row_num}: embedding has {len(embedding)} dims (expected 384), skipping embedding")
                    embedding = None
                skills = parse_skills(row.get("skills", ""))
                posted_date = parse_timestamp(row.get("timestamp", ""))

                city = row.get("city", "").strip()
                region = row.get("region", "").strip()
                country = row.get("country", "").strip()
                if len(city) > 255 or len(region) > 255 or len(country) > 100:
                    print(f"  Skipping row {row_num}: corrupted city/region/country field (possible CSV column misalignment)")
                    errors += 1
                    continue

                batch.append({
                    "job_id": job_id,
                    "company_name": row.get("company_name", "").strip(),
                    "job_title": row.get("job_title", "").strip(),
                    "normalized_title": row.get("normalized_title", "").strip(),
                    "description": None,
                    "embedding": str(embedding) if embedding else None,
                    "city": city,
                    "region": region,
                    "country": country,
                    "is_remote": parse_bool(row.get("is_remote", "")),
                    "job_type": row.get("job_type", "").strip(),
                    "education_level": row.get("education_level", "").strip(),
                    "skills": json.dumps(skills) if skills else None,
                    "posted_date": posted_date,
                })

                if len(batch) >= batch_size:
                    result = _flush_batch(engine, insert_sql, batch)
                    inserted += result[0]
                    skipped += result[1]
                    batch = []

            except Exception as e:
                print(f"Error at row {row_num}: {e}")
                errors += 1

    if batch:
        result = _flush_batch(engine, insert_sql, batch)
        inserted += result[0]
        skipped += result[1]

    engine.dispose()
    return {"inserted": inserted, "skipped": skipped, "errors": errors}


def _flush_batch(engine, insert_sql, batch: list[dict]) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    with engine.connect() as conn:
        with conn.begin():
            for row in batch:
                result = conn.execute(insert_sql, row)
                if result.rowcount and result.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
    print(f"  Batch: {len(batch)} rows ({inserted} inserted, {skipped} skipped)...")
    return inserted, skipped


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_jobs_csv.py <csv_file_path>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    print(f"Importing jobs from: {filepath}")
    result = import_csv(filepath)
    print(f"\nDone! Inserted: {result['inserted']}, "
          f"Skipped: {result['skipped']}, Errors: {result['errors']}")
