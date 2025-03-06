#!/usr/bin/env python
"""
Example Python client for the MCP Server.
Demonstrates how to interact with the MCP Gateway.
"""

import requests
import json
import os
import argparse
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional

# Load environment variables
load_dotenv()

class MCPClient:
    """
    Client for the Model Context Protocol (MCP) server.
    """
    
    def __init__(self, base_url: str):
        """
        Initialize the MCP client.
        
        Args:
            base_url: The base URL of the MCP server
        """
        self.base_url = base_url
        self.gateway_url = f"{base_url}/mcp/gateway"
        self.manifest_url = f"{base_url}/mcp/manifest"
        self.manifest = None
    
    def get_manifest(self) -> Dict[str, Any]:
        """
        Get the MCP manifest describing available tools.
        
        Returns:
            The MCP manifest as a dictionary
        """
        response = requests.get(self.manifest_url)
        response.raise_for_status()
        self.manifest = response.json()
        return self.manifest
    
    def call_tool(self, tool: str, action: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool action via the MCP gateway.
        
        Args:
            tool: The name of the tool to call
            action: The action to perform
            parameters: The parameters for the action
        
        Returns:
            The response from the tool as a dictionary
        """
        payload = {
            "tool": tool,
            "action": action,
            "parameters": parameters
        }
        
        response = requests.post(self.gateway_url, json=payload)
        response.raise_for_status()
        return response.json()
    
    def list_tools(self) -> List[str]:
        """
        List the names of all available tools.
        
        Returns:
            A list of tool names
        """
        if not self.manifest:
            self.get_manifest()
        
        return list(self.manifest["tools"].keys())
    
    def list_actions(self, tool: str) -> Dict[str, Dict[str, Any]]:
        """
        List all available actions for a tool.
        
        Args:
            tool: The name of the tool
        
        Returns:
            A dictionary of action names to action descriptions
        """
        if not self.manifest:
            self.get_manifest()
        
        if tool not in self.manifest["tools"]:
            raise ValueError(f"Unknown tool: {tool}")
        
        return self.manifest["tools"][tool]["actions"]

def example_github_repos(client: MCPClient, username: str) -> None:
    """
    Example: List GitHub repositories for a user.
    
    Args:
        client: The MCP client
        username: The GitHub username to list repositories for
    """
    print(f"\n=== Listing GitHub repositories for {username} ===")
    
    result = client.call_tool("github", "listRepos", {"username": username})
    
    if result["status"] == "success":
        repos = result["result"]
        print(f"Found {len(repos)} repositories:")
        
        for i, repo in enumerate(repos[:5], 1):  # Show only first 5 repos
            print(f"{i}. {repo['name']} - {repo.get('description', 'No description')}")
        
        if len(repos) > 5:
            print(f"... and {len(repos) - 5} more")
    else:
        print(f"Error: {result.get('error')}")

def example_memory_operations(client: MCPClient) -> None:
    """
    Example: Perform memory operations (set, get, list).
    
    Args:
        client: The MCP client
    """
    print("\n=== Memory Tool Examples ===")
    
    # Set a memory item
    key = "example-key"
    value = {"name": "Example Data", "timestamp": "2023-01-01T00:00:00Z", "count": 42}
    
    print(f"Setting memory item with key '{key}'...")
    result = client.call_tool("memory", "set", {
        "key": key,
        "value": json.dumps(value),
        "metadata": {"type": "example", "temporary": True}
    })
    
    if result["status"] == "success":
        print("Memory item set successfully")
    else:
        print(f"Error setting memory item: {result.get('error')}")
        return
    
    # Get the memory item
    print(f"Getting memory item with key '{key}'...")
    result = client.call_tool("memory", "get", {"key": key})
    
    if result["status"] == "success":
        item = result["result"]
        print(f"Retrieved memory item: {item['value']}")
    else:
        print(f"Error getting memory item: {result.get('error')}")
    
    # List memory items
    print("Listing all memory items...")
    result = client.call_tool("memory", "list", {"limit": 10})
    
    if result["status"] == "success":
        items = result["result"]["items"]
        print(f"Found {result['result']['total']} memory items:")
        
        for item in items[:3]:  # Show only first 3 items
            print(f"- {item['key']}: {item['value'][:30]}...")
        
        if len(items) > 3:
            print(f"... and {len(items) - 3} more")
    else:
        print(f"Error listing memory items: {result.get('error')}")

def example_google_maps(client: MCPClient, address: str) -> None:
    """
    Example: Geocode an address using Google Maps.
    
    Args:
        client: The MCP client
        address: The address to geocode
    """
    print(f"\n=== Geocoding address: {address} ===")
    
    result = client.call_tool("gmaps", "geocode", {"address": address})
    
    if result["status"] == "success":
        geocode_result = result["result"]
        
        if geocode_result["status"] == "OK" and geocode_result["results"]:
            location = geocode_result["results"][0]["geometry"]["location"]
            formatted_address = geocode_result["results"][0]["formatted_address"]
            
            print(f"Formatted address: {formatted_address}")
            print(f"Coordinates: {location['lat']}, {location['lng']}")
            
            # Get reverse geocoding result
            print("\nReverse geocoding these coordinates...")
            reverse_result = client.call_tool("gmaps", "reverseGeocode", {
                "lat": location["lat"],
                "lng": location["lng"]
            })
            
            if reverse_result["status"] == "success" and reverse_result["result"]["status"] == "OK":
                print(f"Reverse geocoded address: {reverse_result['result']['results'][0]['formatted_address']}")
            else:
                print("Reverse geocoding failed")
        else:
            print(f"Geocoding failed: {geocode_result['status']}")
    else:
        print(f"Error: {result.get('error')}")

def example_puppeteer(client: MCPClient, url: str) -> None:
    """
    Example: Take a screenshot of a webpage using Puppeteer.
    
    Args:
        client: The MCP client
        url: The URL to screenshot
    """
    print(f"\n=== Taking screenshot of {url} ===")
    
    result = client.call_tool("puppeteer", "screenshot", {
        "url": url,
        "fullPage": False,
        "type": "png"
    })
    
    if result["status"] == "success":
        screenshot_result = result["result"]
        
        if screenshot_result["success"]:
            # Save the screenshot to a file
            img_data = screenshot_result["base64Image"]
            filename = "screenshot.png"
            
            import base64
            with open(filename, "wb") as f:
                f.write(base64.b64decode(img_data))
            
            print(f"Screenshot saved to {filename}")
        else:
            print(f"Screenshot failed: {screenshot_result.get('error')}")
    else:
        print(f"Error: {result.get('error')}")

def main():
    """Run the example client"""
    parser = argparse.ArgumentParser(description="MCP Client Example")
    parser.add_argument("--url", default=os.getenv("MCP_SERVER_URL", "http://localhost:5000"),
                        help="MCP server URL (default: http://localhost:5000)")
    parser.add_argument("--github-user", default="octocat",
                        help="GitHub username for repository listing example (default: octocat)")
    parser.add_argument("--address", default="1600 Amphitheatre Parkway, Mountain View, CA",
                        help="Address for geocoding example")
    parser.add_argument("--webpage", default="https://example.com",
                        help="Webpage URL for screenshot example")
    args = parser.parse_args()
    
    client = MCPClient(args.url)
    
    try:
        # Show available tools
        print(f"Connecting to MCP server at {args.url}...")
        tools = client.list_tools()
        print(f"Available tools: {', '.join(tools)}")
        
        # Run examples
        example_github_repos(client, args.github_user)
        example_memory_operations(client)
        example_google_maps(client, args.address)
        example_puppeteer(client, args.webpage)
        
        print("\n✅ All examples completed successfully!")
    
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to MCP server: {str(e)}")
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
