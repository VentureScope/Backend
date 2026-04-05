import httpx
from typing import Dict, Any

async def fetch_github_profile_description(username: str) -> str | None:
    if not username:
        return None
    try:
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(f"https://api.github.com/users/{username}")
            if user_resp.status_code != 200:
                return None
            user_data = user_resp.json()
            
            repo_resp = await client.get(f"https://api.github.com/users/{username}/repos")
            repos = []
            if repo_resp.status_code == 200:
                repos = repo_resp.json()
            
        bio = user_data.get("bio") or "No bio provided."
        name = user_data.get("name") or username
        company = user_data.get("company") or ""
        
        # Calculate language proportions
        languages = {}
        total_repos = 0
        for repo in repos:
            if not repo.get("fork"):
                lang = repo.get("language")
                if lang:
                    languages[lang] = languages.get(lang, 0) + 1
                    total_repos += 1
                    
        lang_str = "No major languages found."
        if total_repos > 0:
            lang_props = [f"{lang} ({count/total_repos*100:.1f}%)" for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True)]
            lang_str = ", ".join(lang_props)
            
        return f"GitHub Profile - Name: {name}, Company: {company}, Bio: {bio}, Top Languages: {lang_str}"
    except Exception:
        return None
