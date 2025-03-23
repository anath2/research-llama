'''
MCP server for searching the web for information.
'''

import os
import time
import json
import asyncio
from typing import Dict, List, Optional, Any, Union, TypedDict
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

# Check for API key
BRAVE_API_KEY = os.environ.get('BRAVE_API_KEY')
if not BRAVE_API_KEY:
    raise ValueError("Error: BRAVE_API_KEY environment variable is required")

# Rate limit configuration
RATE_LIMIT = {
    "per_second": 1,
    "per_month": 15000
}

# Request counter for rate limiting
request_count = {
    "second": 0,
    "month": 0,
    "last_reset": time.time()
}

# Type definitions
class BraveWebResult(TypedDict, total=False):
    title: str
    description: str
    url: str
    language: Optional[str]
    published: Optional[str]
    rank: Optional[int]

class BraveWebResponse(TypedDict, total=False):
    web: Optional[Dict[str, List[BraveWebResult]]]
    locations: Optional[Dict[str, List[Dict[str, str]]]]

class BraveLocationAddress(TypedDict, total=False):
    streetAddress: Optional[str]
    addressLocality: Optional[str]
    addressRegion: Optional[str]
    postalCode: Optional[str]

class BraveLocationRating(TypedDict, total=False):
    ratingValue: Optional[float]
    ratingCount: Optional[int]

class BraveLocationCoordinates(TypedDict, total=False):
    latitude: float
    longitude: float

class BraveLocation(TypedDict):
    id: str
    name: str
    address: BraveLocationAddress
    coordinates: Optional[BraveLocationCoordinates]
    phone: Optional[str]
    rating: Optional[BraveLocationRating]
    openingHours: Optional[List[str]]
    priceRange: Optional[str]

class BravePoiResponse(TypedDict):
    results: List[BraveLocation]

class BraveDescription(TypedDict):
    descriptions: Dict[str, str]

# Create an MCP server
mcp = FastMCP(
    name="brave-search",
    version="0.1.0",
)

def check_rate_limit():
    """Check if the current request exceeds rate limits"""
    now = time.time()
    if now - request_count["last_reset"] > 1:
        request_count["second"] = 0
        request_count["last_reset"] = now
    
    if (request_count["second"] >= RATE_LIMIT["per_second"] or 
        request_count["month"] >= RATE_LIMIT["per_month"]):
        raise ValueError('Rate limit exceeded')
    
    request_count["second"] += 1
    request_count["month"] += 1

async def perform_web_search(query: str, count: int = 10, offset: int = 0) -> str:
    """Perform a web search using Brave Search API"""
    check_rate_limit()
    
    # Construct URL and parameters
    url = 'https://api.search.brave.com/res/v1/web/search'
    params = {
        'q': query,
        'count': min(count, 20),  # API limit
        'offset': offset
    }
    
    # Make the API request
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        'X-Subscription-Token': BRAVE_API_KEY
    }
    
    async with mcp.http_client() as client:
        response = await client.get(url, params=params, headers=headers)
        
        if response.status_code != 200:
            raise ValueError(f"Brave API error: {response.status_code} {response.reason_phrase}\n{response.text}")
        
        data = response.json()
    
    # Extract just web results
    results = []
    if 'web' in data and 'results' in data['web']:
        for result in data['web']['results']:
            results.append({
                'title': result.get('title', ''),
                'description': result.get('description', ''),
                'url': result.get('url', '')
            })
    
    return '\n\n'.join([
        f"Title: {r['title']}\nDescription: {r['description']}\nURL: {r['url']}"
        for r in results
    ])

async def get_pois_data(ids: List[str]) -> BravePoiResponse:
    """Get POI details for location IDs"""
    check_rate_limit()
    
    url = 'https://api.search.brave.com/res/v1/local/pois'
    
    # Filter out any empty IDs
    valid_ids = [id for id in ids if id]
    
    params = []
    for id in valid_ids:
        params.append(('ids', id))
    
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        'X-Subscription-Token': BRAVE_API_KEY
    }
    
    async with mcp.http_client() as client:
        response = await client.get(url, params=params, headers=headers)
        
        if response.status_code != 200:
            raise ValueError(f"Brave API error: {response.status_code} {response.reason_phrase}\n{response.text}")
        
        return response.json()

async def get_descriptions_data(ids: List[str]) -> BraveDescription:
    """Get descriptions for location IDs"""
    check_rate_limit()
    
    url = 'https://api.search.brave.com/res/v1/local/descriptions'
    
    # Filter out any empty IDs
    valid_ids = [id for id in ids if id]
    
    params = []
    for id in valid_ids:
        params.append(('ids', id))
    
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        'X-Subscription-Token': BRAVE_API_KEY
    }
    
    async with mcp.http_client() as client:
        response = await client.get(url, params=params, headers=headers)
        
        if response.status_code != 200:
            raise ValueError(f"Brave API error: {response.status_code} {response.reason_phrase}\n{response.text}")
        
        return response.json()

def format_local_results(pois_data: BravePoiResponse, desc_data: BraveDescription) -> str:
    """Format local search results into readable text"""
    if not pois_data.get('results'):
        return 'No local results found'
    
    formatted_results = []
    
    for poi in pois_data['results']:
        address_parts = []
        if poi.get('address'):
            if poi['address'].get('streetAddress'):
                address_parts.append(poi['address']['streetAddress'])
            if poi['address'].get('addressLocality'):
                address_parts.append(poi['address']['addressLocality'])
            if poi['address'].get('addressRegion'):
                address_parts.append(poi['address']['addressRegion'])
            if poi['address'].get('postalCode'):
                address_parts.append(poi['address']['postalCode'])
        
        address = ', '.join(address_parts) if address_parts else 'N/A'
        
        rating_value = 'N/A'
        rating_count = 0
        if poi.get('rating'):
            if poi['rating'].get('ratingValue') is not None:
                rating_value = poi['rating']['ratingValue']
            if poi['rating'].get('ratingCount') is not None:
                rating_count = poi['rating']['ratingCount']
        
        hours = 'N/A'
        if poi.get('openingHours'):
            hours = ', '.join(poi['openingHours'])
        
        description = 'No description available'
        if desc_data.get('descriptions') and poi['id'] in desc_data['descriptions']:
            description = desc_data['descriptions'][poi['id']]
        
        result = f"""Name: {poi.get('name', 'N/A')}
Address: {address}
Phone: {poi.get('phone', 'N/A')}
Rating: {rating_value} ({rating_count} reviews)
Price Range: {poi.get('priceRange', 'N/A')}
Hours: {hours}
Description: {description}"""
        
        formatted_results.append(result)
    
    return '\n---\n'.join(formatted_results)

async def perform_local_search(query: str, count: int = 5) -> str:
    """Perform a local search using Brave Search API"""
    check_rate_limit()
    
    # Initial search to get location IDs
    web_url = 'https://api.search.brave.com/res/v1/web/search'
    params = {
        'q': query,
        'search_lang': 'en',
        'result_filter': 'locations',
        'count': min(count, 20)
    }
    
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
        'X-Subscription-Token': BRAVE_API_KEY
    }
    
    async with mcp.http_client() as client:
        response = await client.get(web_url, params=params, headers=headers)
        
        if response.status_code != 200:
            raise ValueError(f"Brave API error: {response.status_code} {response.reason_phrase}\n{response.text}")
        
        web_data = response.json()
    
    # Extract location IDs
    location_ids = []
    if web_data.get('locations') and web_data['locations'].get('results'):
        location_ids = [result.get('id') for result in web_data['locations']['results'] if result.get('id')]
    
    if not location_ids:
        # Fallback to web search if no local results
        return await perform_web_search(query, count)
    
    # Get POI details and descriptions in parallel
    pois_data, descriptions_data = await asyncio.gather(
        get_pois_data(location_ids),
        get_descriptions_data(location_ids)
    )
    
    return format_local_results(pois_data, descriptions_data)

# Define the web search tool
@mcp.tool(
    description=(
        "Performs a web search using the Brave Search API, ideal for general queries, news, articles, and online content. "
        "Use this for broad information gathering, recent events, or when you need diverse web sources. "
        "Supports pagination, content filtering, and freshness controls. "
        "Maximum 20 results per request, with offset for pagination."
    )
)
async def brave_web_search(
    query: str = "Search query (max 400 chars, 50 words)",
    count: int = 10,
    offset: int = 0
) -> str:
    """
    Perform a web search using Brave Search
    
    Args:
        query: Search query (max 400 chars, 50 words)
        count: Number of results (1-20, default 10)
        offset: Pagination offset (max 9, default 0)
    
    Returns:
        Formatted search results as text
    """
    try:
        return await perform_web_search(query, count, offset)
    except Exception as e:
        return f"Error: {str(e)}"

# Define the local search tool
@mcp.tool(
    description=(
        "Searches for local businesses and places using Brave's Local Search API. "
        "Best for queries related to physical locations, businesses, restaurants, services, etc. "
        "Returns detailed information including:\n"
        "- Business names and addresses\n"
        "- Ratings and review counts\n"
        "- Phone numbers and opening hours\n"
        "Use this when the query implies 'near me' or mentions specific locations. "
        "Automatically falls back to web search if no local results are found."
    )
)
async def brave_local_search(
    query: str = "Local search query (e.g. 'pizza near Central Park')",
    count: int = 5
) -> str:
    """
    Search for local businesses and places
    
    Args:
        query: Local search query (e.g. 'pizza near Central Park')
        count: Number of results (1-20, default 5)
    
    Returns:
        Formatted local search results as text
    """
    try:
        return await perform_local_search(query, count)
    except Exception as e:
        return f"Error: {str(e)}"

# Main function to run the server
def main():
    mcp.run()

if __name__ == "__main__":
    main()

