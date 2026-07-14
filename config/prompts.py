"""LLM prompt templates for extraction and enrichment."""

WEBSITE_EXTRACTION_PROMPT = """You are a Family Office intelligence analyst. Extract ALL available structured data from this website content.

Website URL: {url}
Website Content:
{content}

Extract the following fields (return JSON). Use null ONLY for fields where the content provides absolutely no indication:

{{
    "family_office_name": "Official name of the entity",
    "entity_type": "Single Family Office / Multi Family Office / Hybrid / Unknown",
    "description": "2-3 sentence description of what they do, their history, and who founded them",
    "year_founded": "Year as string or null",
    "aum_estimated": "Dollar amount with units (e.g. '$2.5 Billion') or null",
    "aum_source": "Where the AUM figure comes from (e.g. 'website', 'SEC filing') or null",
    "investment_thesis": "Their investment philosophy/strategy in 2-3 sentences",
    "investing_sectors": "Comma-separated list of ALL sectors they invest in (be comprehensive)",
    "hq_city": "City",
    "hq_state": "State/Province/Region",
    "hq_country": "Country (full name, e.g. 'United States of America')",
    "contact_name": "Key person name (Founder, CIO, CEO, Managing Director, Partner)",
    "contact_title": "Their exact title",
    "contact_email": "Email if visible on site (check footer, contact page references)",
    "corporate_linkedin_url": "LinkedIn company page URL if mentioned",
    "key_investments": "Notable portfolio companies, deals, or investments mentioned — comma-separated",
    "recent_activity": "Any recent news, investments, fund launches, or announcements"
}}

IMPORTANT EXTRACTION RULES:
- Extract EVERYTHING available, even partial information
- For investing_sectors, list ALL sectors mentioned anywhere on the page
- For description, synthesize from the About section or homepage messaging
- For contact info, check if there are mailto: links, tel: links, or contact sections
- If the entity type isn't explicitly stated, infer from context (e.g. "serving the [Family Name]" = SFO)
- Return ONLY valid JSON, no markdown or explanation."""

NEWS_EXTRACTION_PROMPT = """Extract Family Office intelligence from this news article/snippet.

Source: {source}
Content:
{content}

Return JSON with any of these fields you can extract (null for unknowns):

{{
    "family_office_name": "Name mentioned",
    "recent_activity": "What happened (investment, hiring, fund launch, etc.)",
    "activity_date": "Date of the activity (YYYY-MM-DD or YYYY-MM or YYYY)",
    "key_investments": "Companies or deals mentioned",
    "aum_estimated": "AUM if mentioned",
    "investing_sectors": "Sectors mentioned",
    "contact_name": "Person mentioned in leadership role",
    "contact_title": "Their title"
}}

Return ONLY valid JSON."""

LLM_ENRICHMENT_PROMPT = """You are a Family Office research analyst. Your role is to ENHANCE existing data with better descriptions, classifications, and context.

Entity: "{name}"
Existing data:
{existing_data}

Provide information ONLY for these fields:
{missing_fields}

YOU MAY ONLY FILL THESE FIELD TYPES:
- description: 2-3 informative sentences about who they are, who founded them, what they do
- investment_thesis: Their investment approach/philosophy
- investing_sectors: Comprehensive comma-separated list (Private Equity, Real Estate, Venture Capital, Technology, Healthcare, etc.)
- entity_type: "Single Family Office", "Multi Family Office", or "Hybrid"
- year_founded: Only if you confidently know it
- hq_city, hq_state, hq_country: Only if you confidently know (use full country names)
- contact_name: Most senior known principal — only if you are confident this person is real
- contact_title: Their actual title — only if providing contact_name

YOU MUST NOT PROVIDE (use null for these even if asked):
- contact_email — NEVER generate email addresses
- contact_linkedin — NEVER generate LinkedIn URLs
- contact_phone — NEVER generate phone numbers
- aum_estimated — NEVER estimate AUM figures
- corporate_linkedin_url — NEVER generate LinkedIn URLs
- website_url — NEVER generate website URLs
- Any URL of any kind

Return ONLY a valid JSON object. Use null for anything you cannot confidently provide."""

RAG_SYSTEM_PROMPT = """You are an AI assistant for Family Office intelligence. You help fund managers,
investment professionals, and business development teams find and evaluate Family Offices.

You have access to a curated dataset of {total_records} validated Family Office records.
Each record contains entity details, principal contacts, investment signals, and data quality scores.

When answering questions:
1. Base your answers ONLY on the retrieved records provided to you
2. Cite specific Family Office names and data points
3. If the data doesn't contain the answer, say so honestly
4. Highlight actionable insights — who to contact, why them, why now
5. Note data confidence levels when relevant

Format responses clearly with the Family Office name, key details, and why they match the query."""

RAG_QUERY_PROMPT = """Based on the following Family Office records from our database, answer the user's question.

Retrieved Records:
{context}

User Question: {question}

Provide a clear, actionable answer based ONLY on the retrieved data.
If multiple records match, rank them by relevance to the question.
Include specific data points (AUM, sectors, contacts, recent activity) that support your answer."""
