# Onboarding Wizard

A 3-step wizard that helps you configure new topic monitoring:

#### Step 1: API Keys (auto-skipped if already configured)

* Configure AI provider keys (OpenAI, Anthropic, Gemini)
* Configure news provider keys (NewsAPI, TheNewsAPI, etc.)
* Configure Firecrawl for web scraping

#### Step 2: Topic Setup

* Enter a topic name (e.g., "APT28 Campaigns")
* Provide a description of what you want to monitor
* AI suggests relevant keywords based on your topic

#### Step 3: Keywords

* Review AI-suggested keywords
* Add/remove/edit keywords as needed
* Keywords are used by Gather for automated collection

### Detailed Instructions

**Set up API Keys**

1. When you first start AuNoo, you will be presented with the onboarding agent.

<figure><img src=".gitbook/assets/unknown (1).png" alt=""><figcaption></figcaption></figure>

<br>

2. Make sure you have the API Keys ready we told you about earlier.&#x20;
3. The agent will run a basic test for each API before allowing you to continue

**Set up your first topic**

<figure><img src=".gitbook/assets/unknown (1) (1).png" alt=""><figcaption></figcaption></figure>

1. **Enter the topic or question you’re interested in.**&#x20;

At the core of AuNoo AI are topics: flexible constructs that can represent markets, knowledge fields, organizations, or even specific strategic questions. For instance:

* Markets: Cloud Service Providers, EV Battery Suppliers, or Threat Intelligence Providers.
* Knowledge Fields: Neurology, AI, or Archeology.
* Organizations or People: AI researchers, competitors, or even a favorite sports team.
* Scenarios: Questions like “Is AI hype?” or “How strong is the Cloud Repatriation movement?”<br>

2. **When you are happy with the topic name and description, hit “Suggest Categories”.**&#x20;

Aunoo’s onboarding agent will make some suggestions for the necessary topic ontology. You will see suggestions for Future Signals and Categories.

**Future Signals**

Future signals are scenarios for the direction a topic can take. For example, future signals for an AI hype model could be "AI is hype" or "AI is evolving gradually". In the case of tracking a market, it could be "Market Convergence" or "Market Growth Stalling".

<figure><img src=".gitbook/assets/unknown (2).png" alt=""><figcaption></figcaption></figure>

**Categories**

Each topic is broken down into categories, making it easier to organize and analyze data. For example, a topic on AI might include subcategories like AI in Finance or Cloud Quarterly Earnings. The topic agent can do most of the heavy lifting for you. All it needs is the topic name and a description.&#x20;

<figure><img src=".gitbook/assets/unknown (3).png" alt=""><figcaption></figcaption></figure>

You can amend the topic name or description and use the “Get Different Suggestions” option to regenerate the selection.

See the section on [ Topic Features ](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.0#heading=h.9q6j8oahy7z)for an in-depth overview of these and other available topic  features.

3. **When you are happy with the suggestions, press “Finish” to move to last step**
4. **You will be presented with the “Set Up Keyword” page.**

While AuNoo is a semantic solution, most news feeds still use keywords. The suggestions will allow AuNoo to search across different feeds and also help improve relevance scoring, as keywords are used to provide context to the AI.

<figure><img src=".gitbook/assets/unknown (4).png" alt=""><figcaption></figcaption></figure>

NOTE: Each keyword will be used to issue a search request, meaning that this will be counted as an API request by many newsfeeds. See [Best Practices for Keyword Monitoring ](https://docs.google.com/document/d/1Rkk_Hz4fXedv-J4-R_h_cTaLuQWJWsBEc6GreckkinM/edit?tab=t.0#heading=h.21drj3jlmjkc)for optimization tips and tricks.

5. **When you are satisfied with the keyword to be monitored, select the “Finish” button.**

