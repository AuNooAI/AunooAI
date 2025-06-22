#!/usr/bin/env python3
"""Test the forecast chart API"""
import requests
import json

def test_api():
    # Test the API endpoint
    url = 'http://localhost:10000/api/forecast-charts/generate/AI%20and%20Machine%20Learning'
    params = {
        'timeframe': '365',
        'title_prefix': 'AI Test',
        'interactive': 'true'
    }

    try:
        response = requests.get(url, params=params)
        print(f'Status code: {response.status_code}')
        data = response.json()
        print(f'Success: {data.get("success", False)}')
        print(f'Has chart_data: {bool(data.get("chart_data"))}')
        print(f'Chart data length: {len(data.get("chart_data", ""))}')
        print(f'Is HTML: {"<html>" in data.get("chart_data", "")}')
        
        # Check for errors
        if not data.get('success'):
            print(f'Error message: {data.get("message", "Unknown error")}')
            
    except Exception as e:
        print(f'Error: {e}')

if __name__ == "__main__":
    test_api() 