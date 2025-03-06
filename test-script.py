#!/usr/bin/env python
"""
Integration test script for the MCP Server.
Tests the MCP Gateway and direct API endpoints for each tool.
"""

import requests
import json
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Server URL
BASE_URL = os.getenv('MCP_SERVER_URL', 'http://localhost:5000')

def test_health():
    """Test the health check endpoint"""
    print("Testing health check endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    
    if response.status_code == 200:
        print("✅ Health check successful")
    else:
        print(f"❌ Health check failed: {response.status_code}")
        print(response.text)

def test_manifest():
    """Test the MCP manifest endpoint"""
    print("\nTesting MCP manifest endpoint...")
    response = requests.get(f"{BASE_URL}/mcp/manifest")
    
    if response.status_code == 200:
        manifest = response.json()
        print("✅ Manifest retrieved successfully")
        print(f"Available tools: {', '.join(manifest['tools'].keys())}")
    else:
        print(f"❌ Manifest retrieval failed: {response.status_code}")
        print(response.text)

def test_github_tool():
    """Test the GitHub tool using MCP gateway"""
    print("\nTesting GitHub tool via MCP gateway...")
    
    # Define a GitHub username to test with
    github_username = "octocat"
    
    payload = {
        "tool": "github",
        "action": "listRepos",
        "parameters": {
            "username": github_username
        }
    }
    
    response = requests.post(f"{BASE_URL}/mcp/gateway", json=payload)
    
    if response.status_code == 200:
        result = response.json()
        if result['status'] == 'success':
            print(f"✅ GitHub listRepos successful - found {len(result['result'])} repos")
        else:
            print(f"❌ GitHub listRepos request failed: {result.get('error')}")
    else:
        print(f"❌ GitHub tool request failed: {response.status_code}")
        print(response.text)
    
    # Test direct API endpoint
    print("Testing GitHub tool via direct API...")
    response = requests.get(f"{BASE_URL}/tool/github/listRepos?username={github_username}")
    
    if response.status_code == 200:
        print("✅ Direct GitHub API request successful")
    else:
        print(f"❌ Direct GitHub API request failed: {response.status_code}")
        print(response.text)

def test_memory_tool():
    """Test the Memory tool for setting and retrieving data"""
    print("\nTesting Memory tool...")
    
    # Test set operation via MCP gateway
    key = "test-key"
    value = "test-value"
    
    set_payload = {
        "tool": "memory",
        "action": "set",
        "parameters": {
            "key": key,
            "value": value,
            "metadata": {
                "test": True,
                "timestamp": "2023-01-01T00:00:00Z"
            }
        }
    }
    
    response = requests.post(f"{BASE_URL}/mcp/gateway", json=set_payload)
    
    if response.status_code == 200:
        result = response.json()
        if result['status'] == 'success':
            print("✅ Memory set successful")
        else:
            print(f"❌ Memory set failed: {result.get('error')}")
    else:
        print(f"❌ Memory set request failed: {response.status_code}")
        print(response.text)
    
    # Test get operation via MCP gateway
    get_payload = {
        "tool": "memory",
        "action": "get",
        "parameters": {
            "key": key
        }
    }
    
    response = requests.post(f"{BASE_URL}/mcp/gateway", json=get_payload)
    
    if response.status_code == 200:
        result = response.json()
        if result['status'] == 'success' and result['result']['value'] == value:
            print(f"✅ Memory get successful - retrieved value: {result['result']['value']}")
        else:
            print(f"❌ Memory get failed or incorrect value: {result}")
    else:
        print(f"❌ Memory get request failed: {response.status_code}")
        print(response.text)
    
    # Test direct API endpoint for list operation
    print("Testing Memory tool via direct API...")
    response = requests.get(f"{BASE_URL}/tool/memory/list")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Direct Memory API request successful - found {result['total']} items")
    else:
        print(f"❌ Direct Memory API request failed: {response.status_code}")
        print(response.text)

def test_puppeteer_tool():
    """Test the Puppeteer tool for taking a screenshot"""
    print("\nTesting Puppeteer tool...")
    
    # Test screenshot operation via MCP gateway
    screenshot_payload = {
        "tool": "puppeteer",
        "action": "screenshot",
        "parameters": {
            "url": "https://example.com",
            "fullPage": False,
            "type": "png"
        }
    }
    
    response = requests.post(f"{BASE_URL}/mcp/gateway", json=screenshot_payload)
    
    if response.status_code == 200:
        result = response.json()
        if result['status'] == 'success' and 'base64Image' in result['result']:
            print("✅ Puppeteer screenshot successful - image received")
        else:
            print(f"❌ Puppeteer screenshot failed: {result}")
    else:
        print(f"❌ Puppeteer screenshot request failed: {response.status_code}")
        print(response.text)

def main():
    """Run all tests"""
    print("=== MCP Server Integration Tests ===")
    print(f"Testing server at: {BASE_URL}")
    
    try:
        test_health()
        test_manifest()
        test_github_tool()
        test_memory_tool()
        test_puppeteer_tool()
        
        print("\n✅ All tests completed!")
    except Exception as e:
        print(f"\n❌ Tests failed with error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
