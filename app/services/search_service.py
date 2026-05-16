import os
import json
import httpx
from typing import Dict, Any, List

from langchain_core.tools import tool

class SerperSearchService:
    def __init__(self):
        self.api_key = os.getenv("SERPER_API_KEY", "")
        self.base_url = "https://google.serper.dev/search"

    async def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Perform a Google search using the Serper API.
        """
        if not self.api_key:
            raise ValueError("SERPER_API_KEY environment variable is not set")

        headers = {
            'X-API-KEY': self.api_key,
            'Content-Type': 'application/json'
        }
        payload = {
            "q": query
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.base_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Extract organic results
            organic_results = data.get("organic", [])
            return organic_results

# Initialize singleton
search_service = SerperSearchService()

@tool
async def perform_web_search(query: str) -> str:
    """
    Search the web for real-time information, resources, tutorials, or links about a specific topic.
    Use this tool when you need external resources or when existing links are broken.
    """
    print(f"\n🔍 [WEB SEARCH TOOL CALLED] LLM is searching Google for: '{query}'\n")
    
    try:
        results = await search_service.search(query)
    except Exception as e:
        return f"Error performing search: {str(e)}"
        
    if not results:
        return "No results found."
        
    # Format the results into a readable string for the LLM
    formatted_results = []
    for idx, res in enumerate(results[:5]):  # Yield top 5 results
        title = res.get("title", "No Title")
        link = res.get("link", "No Link")
        snippet = res.get("snippet", "No Snippet")
        formatted_results.append(f"Result {idx + 1}:\nTitle: {title}\nURL: {link}\nSnippet: {snippet}\n")
        
    return "\n".join(formatted_results)
