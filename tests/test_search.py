'''
Tests for the Brave Search MCP server.
'''

import os
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import search  # Import the search module

# Sample test data
SAMPLE_WEB_RESPONSE = {
    "web": {
        "results": [
            {
                "title": "Sample Title 1",
                "description": "Sample Description 1",
                "url": "https://example.com/1"
            },
            {
                "title": "Sample Title 2",
                "description": "Sample Description 2",
                "url": "https://example.com/2"
            }
        ]
    }
}

SAMPLE_LOCAL_RESPONSE = {
    "locations": {
        "results": [
            {"id": "loc1", "title": "Location 1"},
            {"id": "loc2", "title": "Location 2"}
        ]
    }
}

SAMPLE_POIS_RESPONSE = {
    "results": [
        {
            "id": "loc1",
            "name": "Restaurant 1",
            "address": {
                "streetAddress": "123 Main St",
                "addressLocality": "Anytown",
                "addressRegion": "CA",
                "postalCode": "12345"
            },
            "phone": "+1-555-123-4567",
            "rating": {
                "ratingValue": 4.5,
                "ratingCount": 100
            },
            "openingHours": ["Mon-Fri 9am-5pm", "Sat 10am-3pm"],
            "priceRange": "$$"
        },
        {
            "id": "loc2",
            "name": "Restaurant 2",
            "address": {
                "streetAddress": "456 Oak Ave",
                "addressLocality": "Othertown",
                "addressRegion": "NY",
                "postalCode": "67890"
            },
            "phone": "+1-555-987-6543",
            "rating": {
                "ratingValue": 4.0,
                "ratingCount": 75
            },
            "openingHours": ["Mon-Sun 8am-10pm"],
            "priceRange": "$$$"
        }
    ]
}

SAMPLE_DESCRIPTIONS_RESPONSE = {
    "descriptions": {
        "loc1": "A great place to eat with a variety of dishes.",
        "loc2": "Upscale dining with excellent service."
    }
}

@pytest.fixture
def mock_env():
    """Set up environment variable for testing"""
    original_env = os.environ.get('BRAVE_API_KEY')
    os.environ['BRAVE_API_KEY'] = 'test_api_key'
    yield
    if original_env:
        os.environ['BRAVE_API_KEY'] = original_env
    else:
        del os.environ['BRAVE_API_KEY']

@pytest.fixture
def reset_rate_limit():
    """Reset rate limit counters before each test"""
    search.request_count = {
        "second": 0,
        "month": 0,
        "last_reset": search.time.time()
    }
    yield

class MockResponse:
    def __init__(self, data, status_code=200):
        self.data = data
        self.status_code = status_code
        self.reason_phrase = "OK" if status_code == 200 else "Error"
        self.text = json.dumps(data)
    
    def json(self):
        return self.data

class MockHttpClient:
    def __init__(self, responses):
        self.responses = responses
        self.request_count = 0
    
    async def get(self, url, params=None, headers=None):
        if self.request_count < len(self.responses):
            response = self.responses[self.request_count]
            self.request_count += 1
            return response
        return MockResponse({}, 404)

@pytest.mark.asyncio
async def test_web_search(mock_env, reset_rate_limit):
    """Test the web search functionality"""
    # Create a mock response
    mock_response = MockResponse(SAMPLE_WEB_RESPONSE)
    
    # Mock the HTTP client
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = MagicMock()
    mock_client.__aenter__.return_value.get.return_value = mock_response
    
    # Patch the HTTP client creation
    with patch.object(search.mcp, 'http_client', return_value=mock_client):
        result = await search.perform_web_search("test query")
    
    # Verify the result contains expected data
    assert "Sample Title 1" in result
    assert "Sample Description 1" in result
    assert "https://example.com/1" in result
    assert "Sample Title 2" in result

@pytest.mark.asyncio
async def test_local_search(mock_env, reset_rate_limit):
    """Test the local search functionality"""
    # Create mock responses for the sequence of API calls
    mock_responses = [
        MockResponse(SAMPLE_LOCAL_RESPONSE),  # First call to get location IDs
        MockResponse(SAMPLE_POIS_RESPONSE),   # Second call to get POI details
        MockResponse(SAMPLE_DESCRIPTIONS_RESPONSE)  # Third call to get descriptions
    ]
    
    # Create a mock client that returns our sequence of responses
    mock_client = MockHttpClient(mock_responses)
    
    # Patch the HTTP client creation and asyncio.gather
    with patch.object(search.mcp, 'http_client', return_value=mock_client), \
         patch('search.asyncio.gather', new=AsyncMock(
             return_value=[SAMPLE_POIS_RESPONSE, SAMPLE_DESCRIPTIONS_RESPONSE]
         )):
        result = await search.perform_local_search("restaurants near me")
    
    # Verify the result contains expected data
    assert "Restaurant 1" in result
    assert "123 Main St, Anytown, CA, 12345" in result
    assert "4.5 (100 reviews)" in result
    assert "A great place to eat" in result
    assert "Restaurant 2" in result

@pytest.mark.asyncio
async def test_rate_limit(mock_env, reset_rate_limit):
    """Test rate limiting functionality"""
    # Set the rate limit to be exceeded
    search.request_count["second"] = search.RATE_LIMIT["per_second"]
    
    # Attempt to search
    with pytest.raises(ValueError) as excinfo:
        await search.perform_web_search("test query")
    
    assert "Rate limit exceeded" in str(excinfo.value)

@pytest.mark.asyncio
async def test_brave_web_search_tool(mock_env, reset_rate_limit):
    """Test the brave_web_search tool wrapper"""
    # Mock the underlying search function
    with patch('search.perform_web_search', new=AsyncMock(
        return_value="Mocked search results"
    )):
        result = await search.brave_web_search("python programming")
    
    assert result == "Mocked search results"

@pytest.mark.asyncio
async def test_brave_local_search_tool(mock_env, reset_rate_limit):
    """Test the brave_local_search tool wrapper"""
    # Mock the underlying search function
    with patch('search.perform_local_search', new=AsyncMock(
        return_value="Mocked local results"
    )):
        result = await search.brave_local_search("cafes near me")
    
    assert result == "Mocked local results"

@pytest.mark.asyncio
async def test_error_handling(mock_env, reset_rate_limit):
    """Test error handling in tool wrappers"""
    # Mock a search function that raises an exception
    with patch('search.perform_web_search', new=AsyncMock(
        side_effect=ValueError("API error")
    )):
        result = await search.brave_web_search("test query")
    
    assert "Error: API error" in result 