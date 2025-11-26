# Keyword Monitoring

The Keyword Monitor page allows you to organize and manage keywords into groups for automated news monitoring. Keywords are organized by topic and used by the Auto-Collect system to find relevant articles.

**Set Up Topic**

Opens the onboarding wizard to configure a new topic. Topics are high-level categories that contain keyword groups.

**New Group**

Creates a new keyword group within an existing topic.

***

### Keyword Groups

Each keyword group represents a collection of related keywords that the system monitors together.

#### Group Card Information

Each group card displays:

* Group Name - Descriptive name for the keyword collection
* Topic Badge - Shows which topic this group belongs to
* Monitored Keywords - List of keywords being tracked
* Action Buttons - Add keywords or delete the group

***

### Creating a New Keyword Group

#### Steps:

&#x20; 1\. Click the New Group button

&#x20; 2\. Fill in the modal form:

**Group Name**

A descriptive name for this keyword collection.

Examples:

* "AI Safety News"
* "Cloud Computing Updates"
* "Cybersecurity Threats"

**Topic**

Select which topic this group belongs to. Topics are high-level categories for organizing your monitoring.

<figure><img src="../.gitbook/assets/unknown.png" alt=""><figcaption></figcaption></figure>

***

### Managing Keywords

**Adding Keywords to a Group**

1. Click Add Keyword on the desired group card
2. Enter your keyword or phrase in the modal

**Keyword or Phrase**

Enter the term you want to monitor. Supports advanced search operators:

Search Operators:

* Exact Phrases - Use quotes for exact matching
* Example: "artificial intelligence"
* OR Operator - Match any of the alternatives
* Example: AI OR "artificial intelligence"
* AND Operator - Match combinations
* Example: AI AND safety

#### Tips:

* Use specific phrases to reduce noise
* Combine operators for precise matching
* Test with a few keywords before adding many

**Group Organization Tips:**

By Topic:

* &#x20;Keep groups focused on specific sub-topics
* &#x20;Example: Under "Technology" topic, create groups for "AI", "Cloud", "Security"

By Specificity:

* Broad group: General industry terms
* Narrow group: Specific product names or events

By Priority:

* High-priority: Critical terms needing immediate attention
* Low-priority: Background monitoring terms

**Removing Keywords**

Click the × button on any keyword badge to remove it from the group. The system will ask you to confirm before deleting.

**Deleting Keyword Groups**

Click Delete Group to remove an entire keyword group and all its keywords.

_**Warning: This action cannot be undone. All keywords in the group will be permanently deleted. The system will ask you to confirm before deleting.**_

***

### How Keyword Groups Work

### Integration with Auto-Collect

Keywords defined here are used by the Auto-Collect system (configured on Keyword Alerts page) to:

* Search News APIs - System queries providers with your keywords
* Find Matches - Articles matching keywords are retrieved
* Score Relevance - AI determines how relevant each article is
* Apply QC - Quality control filters low-quality articles
* Save Results - Approved articles are saved to your database

#### Workflow:

1. Create Groups - Organize keywords by topic and subject area
2. Add Keywords - Define what terms to monitor in each group
3. Auto-Collection - System automatically searches for matching articles (configured on Keyword Alerts page)
4. Processing - Articles are scored and filtered (configured on Keyword Alerts page)
5. Review - View results on the Keyword Alerts page

***

### Best Practices

| Keyword Management                                                                                                                      | Group Organization                                                                                         |
| --------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| <ul><li>Start Small</li><li>Use Specific Phrases</li><li>Combine Operators</li><li>Test Keywords</li><li> Regular Maintenance</li></ul> | <ul><li>Logical Grouping</li><li>Clear Naming</li><li>Topic Alignment</li><li>Don't Over-Segment</li></ul> |

***

### API Usage Tracking

The system tracks API usage to prevent exceeding daily limits. Usage information is displayed on the Keyword Alerts page.

What Counts as an API Request:

* Each keyword search counts as one request
* Multiple keywords = multiple requests
* Searches run based on your Auto-Collection schedule

Managing API Usage:

* Set appropriate check intervals (less frequent = fewer requests)
* Balance coverage with API limits
* Monitor usage on Keyword Alerts page

***

### Troubleshooting

**No Keywords Appearing**

* Ensure you've added keywords to the group
* Check that the group was created successfully
* Refresh the page

**Keywords Not Finding Articles**

* Verify keywords are spelled correctly
* Check Auto-Collect settings on Keyword Alerts page
* Ensure Auto-Collection is enabled
* Review API usage limits

**Can't Create Group**

* Ensure you've selected a valid topic
* Verify group name is filled in
* Check for duplicate group names

**Settings Not Available**

* Settings have moved to the Keyword Alerts page
* Click "Go to Auto-Processing Settings" button
* Access via /keyword-alerts URL
