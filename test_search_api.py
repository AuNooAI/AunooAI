import requests

# Login first
login_url = 'http://localhost:10000/login'
session = requests.Session()

# Get the login page first to get CSRF token
login_page = session.get('http://localhost:10000/login')

# Login with admin/admin
login_data = {
    'username': 'admin',
    'password': 'Admin182!'
}

# Login
login_response = session.post(login_url, data=login_data, 
                            allow_redirects=False)
print(f'Login status: {login_response.status_code}')

# Now test the search API
search_url = 'http://localhost:10000/api/search_articles'
params = {
    'topic': 'AI and Machine Learning',
    'page': 1,
    'per_page': 3
}

response = session.get(search_url, params=params)
print(f'Search API status: {response.status_code}')
print(f'Response headers: {response.headers}')
print(f'Response text preview: {response.text[:200]}...')

if response.status_code == 200:
    # Check if response is HTML (redirect page)
    if 'text/html' in response.headers.get('content-type', ''):
        print('\nGot HTML response - likely a redirect page')
        if 'login' in response.text.lower():
            print('Appears to be redirected to login page')
    else:
        try:
            data = response.json()
            print(f'\nTotal articles: {data.get("total_count", 0)}')
            articles = data.get('articles', [])
            
            print(f'\nShowing {len(articles)} articles:')
            for i, article in enumerate(articles):
                print(f'\n{"="*50}')
                print(f'Article {i+1}:')
                print(f'  Title: {article.get("title", "N/A")}')
                print(f'  Category: {article.get("category", "N/A")}')
                print(f'  Sentiment: {article.get("sentiment", "N/A")}')
                print(f'  Future Signal: {article.get("future_signal", "N/A")}')
                print(f'  Time to Impact: {article.get("time_to_impact", "N/A")}')
                print(f'  Driver Type: {article.get("driver_type", "N/A")}')
                print(f'  Tags: {article.get("tags", [])}')
                print(f'  News Source: {article.get("news_source", "N/A")}')
                
                # Check enrichment status
                has_category = bool(article.get("category") and 
                                  article.get("category") != "N/A")
                has_sentiment = bool(article.get("sentiment") and 
                                   article.get("sentiment") != "N/A")
                has_future_signal = bool(article.get("future_signal") and 
                                       article.get("future_signal") != "N/A")
                has_enrichment = has_category or has_sentiment or has_future_signal
                
                print('\n  Enrichment Status:')
                print(f'    Has Category: {has_category}')
                print(f'    Has Sentiment: {has_sentiment}')
                print(f'    Has Future Signal: {has_future_signal}')
                print(f'    Is Enriched: {has_enrichment}')
        except Exception as e:
            print(f'Error parsing JSON: {e}')
else:
    print(f'Error: {response.text}') 