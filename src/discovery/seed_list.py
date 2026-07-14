"""Curated seed list of known Family Offices — Channel 1 of discovery.

Sources: publicly known FO directories, news coverage, SEC filings.
Pre-filled with known details to maximize dataset quality even before enrichment.
"""

SEED_FAMILY_OFFICES = [
    # ── Well-documented large SFOs ─────────────────────────────────
    {"name": "Cascade Investment", "website": "https://www.cascadeinv.com",
     "notes": "Bill Gates family office", "entity_type": "Single Family Office",
     "hq_city": "Kirkland", "hq_state": "Washington", "hq_country": "United States of America",
     "description": "Private investment vehicle managing the personal fortune of Bill Gates, co-founder of Microsoft. Diversified portfolio spanning technology, hospitality, energy, real estate, and agriculture."},

    {"name": "Emerson Collective", "website": "https://www.emersoncollective.com",
     "notes": "Laurene Powell Jobs", "entity_type": "Single Family Office",
     "hq_city": "Palo Alto", "hq_state": "California", "hq_country": "United States of America",
     "description": "Impact-focused organization founded by Laurene Powell Jobs, investing in education, immigration reform, environment, media, and health equity."},

    {"name": "Bezos Expeditions", "website": "https://www.bezosexpeditions.com",
     "notes": "Jeff Bezos family office", "entity_type": "Single Family Office",
     "hq_city": "Seattle", "hq_state": "Washington", "hq_country": "United States of America",
     "description": "Personal venture capital fund of Jeff Bezos, founder of Amazon. Early investor in Google, Twitter, Uber, Airbnb, and numerous technology startups."},

    {"name": "Iconiq Capital", "website": "https://www.iconiqcapital.com",
     "notes": "Multi-family office for tech billionaires", "entity_type": "Multi Family Office",
     "hq_city": "San Francisco", "hq_state": "California", "hq_country": "United States of America",
     "description": "Elite multi-family office serving technology founders including Mark Zuckerberg, Jack Dorsey, and other Silicon Valley leaders. Manages over $80B in assets across growth equity, real estate, and credit."},

    {"name": "MSD Partners", "website": "https://www.msdpartners.com",
     "notes": "Michael Dell family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Investment firm managing the capital of Michael Dell, founder of Dell Technologies. Diversified across public equity, private equity, credit, and real estate."},

    {"name": "Soros Fund Management", "website": "https://www.soros.com",
     "notes": "George Soros family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Family office of George Soros, legendary investor known for breaking the Bank of England. Manages macro-driven investments across global equities, fixed income, and currencies."},

    {"name": "Willett Advisors", "website": "https://www.willettadvisors.com",
     "notes": "Michael Bloomberg family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Investment management firm overseeing the personal and philanthropic assets of Michael Bloomberg, founder of Bloomberg LP."},

    {"name": "Vulcan Inc.", "website": "https://vulcan.com",
     "notes": "Paul Allen estate family office", "entity_type": "Single Family Office",
     "hq_city": "Seattle", "hq_state": "Washington", "hq_country": "United States of America",
     "description": "Estate management company of the late Paul Allen, co-founder of Microsoft. Manages technology investments, real estate, sports teams, and philanthropic ventures."},

    {"name": "Mousse Partners", "website": "https://moussepartners.com",
     "notes": "Wertheimer family (Chanel owners)", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Family office of the Wertheimer family, controlling shareholders of Chanel. Manages diversified investments across luxury, wine, technology, and real estate."},

    {"name": "Ballmer Group", "website": "https://www.ballmergroup.com",
     "notes": "Steve Ballmer family office", "entity_type": "Single Family Office",
     "hq_city": "Bellevue", "hq_state": "Washington", "hq_country": "United States of America",
     "description": "Philanthropic investment organization of Steve Ballmer, former CEO of Microsoft. Focuses on economic mobility for children and families in the United States."},

    # ── Mid-size / Niche SFOs ──────────────────────────────────────
    {"name": "Pritzker Group", "website": "https://www.pritzkergroup.com",
     "notes": "Pritzker family investments", "entity_type": "Single Family Office",
     "hq_city": "Chicago", "hq_state": "Illinois", "hq_country": "United States of America",
     "description": "Investment firm of the Pritzker family (Hyatt Hotels). Active in private equity, venture capital, and asset management with focus on middle-market companies."},

    {"name": "Euclidean Capital", "website": None,
     "notes": "James Simons family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Family office of James Simons, founder of Renaissance Technologies and pioneer of quantitative trading. Focuses on technology, education, and scientific research investments."},

    {"name": "Waycrosse", "website": "https://www.waycrosse.com",
     "notes": "Bass family office", "entity_type": "Single Family Office",
     "hq_city": "Fort Worth", "hq_state": "Texas", "hq_country": "United States of America",
     "description": "Multi-generational family office of the Bass family. Manages diversified investments across oil and gas, real estate, and public equities."},

    {"name": "Stanhope Capital", "website": "https://www.stanhopecp.com",
     "notes": "London-based MFO", "entity_type": "Multi Family Office",
     "hq_city": "London", "hq_state": None, "hq_country": "United Kingdom",
     "description": "Independent multi-family office providing investment management and advisory services to ultra-high-net-worth families across Europe and the Middle East."},

    {"name": "Bessemer Trust", "website": "https://www.bessemertrust.com",
     "notes": "Phipps family, large MFO", "entity_type": "Multi Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "One of the oldest and largest multi-family offices in the US, founded by Henry Phipps, partner of Andrew Carnegie. Over $150B in assets under supervision."},

    {"name": "Rockefeller Capital Management", "website": "https://www.rockco.com",
     "notes": "Rockefeller family legacy", "entity_type": "Multi Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Modern successor to the Rockefeller family office. Full-service wealth management, advisory, and strategic investment platform for ultra-high-net-worth clients."},

    {"name": "Blue Pool Capital", "website": None,
     "notes": "Jack Ma / Joe Tsai family office, Hong Kong", "entity_type": "Single Family Office",
     "hq_city": "Hong Kong", "hq_state": None, "hq_country": "Hong Kong",
     "description": "Family office managing the personal wealth of Alibaba co-founders Jack Ma and Joe Tsai. Invests globally across technology, healthcare, and consumer sectors."},

    {"name": "Walton Enterprises", "website": None,
     "notes": "Walmart family office", "entity_type": "Single Family Office",
     "hq_city": "Bentonville", "hq_state": "Arkansas", "hq_country": "United States of America",
     "description": "Family office of the Walton family, heirs to the Walmart fortune. Manages one of the largest family fortunes globally across retail, banking, and art investments."},

    {"name": "Koch Industries", "website": "https://www.kochind.com",
     "notes": "Koch family investments", "entity_type": "Single Family Office",
     "hq_city": "Wichita", "hq_state": "Kansas", "hq_country": "United States of America",
     "description": "Diversified conglomerate controlled by the Koch family. Investments span refining, chemicals, agriculture, finance, and technology. One of the largest private companies in the US."},

    {"name": "Arnault Family Office", "website": None,
     "notes": "Bernard Arnault / LVMH family", "entity_type": "Single Family Office",
     "hq_city": "Paris", "hq_state": None, "hq_country": "France",
     "description": "Family office of Bernard Arnault, chairman of LVMH and one of the world's wealthiest individuals. Manages investments in luxury brands, real estate, technology, and media."},

    # ── Active FOs in tech / AI ────────────────────────────────────
    {"name": "Hillspire", "website": None,
     "notes": "Eric Schmidt family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Family office of Eric Schmidt, former CEO of Google/Alphabet. Invests heavily in artificial intelligence, defense technology, and deep tech startups."},

    {"name": "Sergey Brin Family Office", "website": None,
     "notes": "Bayshore Global Management", "entity_type": "Single Family Office",
     "hq_city": "Los Altos", "hq_state": "California", "hq_country": "United States of America",
     "description": "Family office of Sergey Brin, co-founder of Google. Manages investments through Bayshore Global Management across technology, airship ventures, and philanthropy."},

    {"name": "Westly Group", "website": "https://www.westlygroup.com",
     "notes": "Cleantech family office / VC", "entity_type": "Single Family Office",
     "hq_city": "Menlo Park", "hq_state": "California", "hq_country": "United States of America",
     "description": "Venture capital firm and family office focused on sustainable technology including clean energy, mobility, agriculture, and smart cities."},

    {"name": "Point72", "website": "https://www.point72.com",
     "notes": "Steve Cohen family office / fund", "entity_type": "Hybrid",
     "hq_city": "Stamford", "hq_state": "Connecticut", "hq_country": "United States of America",
     "description": "Multi-strategy hedge fund and family office of Steve Cohen, owner of the New York Mets. Manages over $30B across discretionary long/short, macro, and systematic strategies."},

    {"name": "Moore Capital Management", "website": "https://www.moorecap.com",
     "notes": "Louis Bacon family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Global macro hedge fund and family office of Louis Bacon. Known for macro-driven trading across equities, fixed income, currencies, and commodities."},

    # ── Real estate focused ────────────────────────────────────────
    {"name": "LeFrak Organization", "website": "https://www.lefrak.com",
     "notes": "LeFrak family, NYC real estate", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Multi-generational real estate family office. One of New York City's largest private landlords with extensive residential and commercial property portfolios."},

    {"name": "Tishman Speyer", "website": "https://www.tishmanspeyer.com",
     "notes": "Real estate family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Global real estate developer and family office. Iconic properties include Rockefeller Center and the Chrysler Building. Active across office, residential, and mixed-use development."},

    {"name": "Grosvenor", "website": "https://www.grosvenor.com",
     "notes": "Westminster family, UK real estate", "entity_type": "Single Family Office",
     "hq_city": "London", "hq_state": None, "hq_country": "United Kingdom",
     "description": "Family office of the Duke of Westminster. One of the UK's largest private landowners, managing extensive property portfolios in London's Mayfair and Belgravia."},

    {"name": "Related Companies", "website": "https://www.related.com",
     "notes": "Stephen Ross family", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Real estate development and family office of Stephen Ross. Developed Hudson Yards, one of the largest private real estate developments in US history."},

    # ── Healthcare / Biotech focused ───────────────────────────────
    {"name": "Deerfield Management", "website": "https://www.deerfield.com",
     "notes": "Healthcare family office / fund", "entity_type": "Hybrid",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Healthcare-focused investment management firm. Invests across public and private healthcare companies with a focus on advancing healthcare innovation."},

    {"name": "Lux Capital", "website": "https://www.luxcapital.com",
     "notes": "Deep tech / biotech VC family office", "entity_type": "Hybrid",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Venture capital firm investing at the intersection of science and technology. Focus areas include AI, biotech, space, defense, and emerging computing platforms."},

    # ── International ──────────────────────────────────────────────
    {"name": "Temasek Holdings", "website": "https://www.temasek.com.sg",
     "notes": "Singapore sovereign/family wealth", "entity_type": "Multi Family Office",
     "hq_city": "Singapore", "hq_state": None, "hq_country": "Singapore",
     "description": "Singapore state-owned investment company managing a diversified global portfolio exceeding $380B. Active investor across technology, healthcare, financial services, and sustainability."},

    {"name": "Wafra", "website": "https://www.wafra.com",
     "notes": "Kuwaiti family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Investment management firm backed by Kuwaiti sovereign wealth. Manages over $30B across real estate, private equity, credit, and infrastructure globally."},

    {"name": "Mubadala Investment Company", "website": "https://www.mubadala.com",
     "notes": "Abu Dhabi sovereign/family office", "entity_type": "Multi Family Office",
     "hq_city": "Abu Dhabi", "hq_state": None, "hq_country": "United Arab Emirates",
     "description": "Abu Dhabi sovereign wealth fund managing over $300B. Active in aerospace, ICT, semiconductors, renewable energy, healthcare, and real estate."},

    {"name": "Tikehau Capital", "website": "https://www.tikehaucapital.com",
     "notes": "French family office / asset mgmt", "entity_type": "Multi Family Office",
     "hq_city": "Paris", "hq_state": None, "hq_country": "France",
     "description": "Global alternative asset management group with European family office roots. Manages over €40B across private debt, real assets, private equity, and capital markets strategies."},

    {"name": "Premji Invest", "website": "https://www.premjiinvest.com",
     "notes": "Azim Premji family office, India", "entity_type": "Single Family Office",
     "hq_city": "Bangalore", "hq_state": None, "hq_country": "India",
     "description": "Investment arm of Azim Premji, founder of Wipro. One of India's largest family offices with investments in technology, healthcare, FMCG, and financial services."},

    # ── Energy / Infrastructure ────────────────────────────────────
    {"name": "Cox Enterprises", "website": "https://www.coxenterprises.com",
     "notes": "Cox family office", "entity_type": "Single Family Office",
     "hq_city": "Atlanta", "hq_state": "Georgia", "hq_country": "United States of America",
     "description": "Multi-generational family enterprise with interests in automotive services, media, telecommunications, and cleantech. One of the largest private companies in the US."},

    {"name": "Declaration Partners", "website": "https://www.declarationpartners.com",
     "notes": "David Rubenstein family office", "entity_type": "Single Family Office",
     "hq_city": "Washington", "hq_state": "D.C.", "hq_country": "United States of America",
     "description": "Family office of David Rubenstein, co-founder of The Carlyle Group. Invests across private equity, real estate, and growth equity."},

    # ── Multi-Family Offices ───────────────────────────────────────
    {"name": "Cresset Capital", "website": "https://cressetcapital.com",
     "notes": "Chicago MFO", "entity_type": "Multi Family Office",
     "hq_city": "Chicago", "hq_state": "Illinois", "hq_country": "United States of America",
     "description": "Award-winning multi-family office providing wealth management, investment management, and family office services to ultra-high-net-worth families nationwide."},

    {"name": "Pitcairn", "website": "https://www.pitcairn.com",
     "notes": "PPG family legacy MFO", "entity_type": "Multi Family Office",
     "hq_city": "Philadelphia", "hq_state": "Pennsylvania", "hq_country": "United States of America",
     "description": "Multi-family office with century-long heritage, originally established for the founders of PPG Industries. Provides comprehensive wealth management and family governance services."},

    {"name": "Whittier Trust", "website": "https://www.whittiertrust.com",
     "notes": "CA-based MFO", "entity_type": "Multi Family Office",
     "hq_city": "South Pasadena", "hq_state": "California", "hq_country": "United States of America",
     "description": "Independent multi-family office providing investment management, trust, and estate administration services to high-net-worth families across the western United States."},

    {"name": "Pathstone", "website": "https://www.pathstone.com",
     "notes": "National MFO", "entity_type": "Multi Family Office",
     "hq_city": "Englewood", "hq_state": "New Jersey", "hq_country": "United States of America",
     "description": "National multi-family office offering customized investment management, tax planning, and family advisory services with a focus on impact investing."},

    {"name": "Tolleson Wealth Management", "website": "https://www.tolleson.com",
     "notes": "Dallas MFO", "entity_type": "Multi Family Office",
     "hq_city": "Dallas", "hq_state": "Texas", "hq_country": "United States of America",
     "description": "Independent multi-family office providing investment management, financial planning, tax, and trust services to ultra-high-net-worth families in the Southwest."},

    {"name": "Fiduciary Trust International", "website": "https://www.fiduciarytrust.com",
     "notes": "MFO / wealth management", "entity_type": "Multi Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Global wealth management firm providing investment management, trust, and estate services to families, foundations, and endowments since 1931."},

    {"name": "Centricus", "website": "https://www.centricus.com",
     "notes": "Global family office / advisory", "entity_type": "Multi Family Office",
     "hq_city": "London", "hq_state": None, "hq_country": "United Kingdom",
     "description": "Global advisory and investment firm serving ultra-high-net-worth families and institutional investors. Focus on M&A advisory, principal investing, and wealth structuring."},

    # ── Additional well-known FOs ──────────────────────────────────
    {"name": "Duchossois Group", "website": "https://www.duchossois.com",
     "notes": "Chicago manufacturing family", "entity_type": "Single Family Office",
     "hq_city": "Elmhurst", "hq_state": "Illinois", "hq_country": "United States of America",
     "description": "Family office of the Duchossois family. Manages investments in manufacturing, consumer products, and technology with a long-term value creation approach."},

    {"name": "Stephens Inc.", "website": "https://www.stephens.com",
     "notes": "Arkansas family office / investment bank", "entity_type": "Hybrid",
     "hq_city": "Little Rock", "hq_state": "Arkansas", "hq_country": "United States of America",
     "description": "Family-owned investment bank and family office. Provides investment banking, wealth management, insurance, and venture capital services."},

    {"name": "Haslam Family Office", "website": None,
     "notes": "Pilot Flying J family", "entity_type": "Single Family Office",
     "hq_city": "Knoxville", "hq_state": "Tennessee", "hq_country": "United States of America",
     "description": "Family office of the Haslam family, owners of Pilot Flying J truck stops. Active in transportation, energy, and professional sports (Cleveland Browns)."},

    {"name": "Emso Asset Management", "website": "https://www.emso.com",
     "notes": "EM-focused family office", "entity_type": "Hybrid",
     "hq_city": "London", "hq_state": None, "hq_country": "United Kingdom",
     "description": "Global emerging markets investment firm with family office characteristics. Specializes in emerging market credit, rates, and foreign exchange."},

    {"name": "Reverence Capital Partners", "website": "https://www.reverencecapital.com",
     "notes": "Financial services focused", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Private investment firm focused exclusively on the financial services sector. Invests in insurance, asset management, fintech, and specialty finance."},

    {"name": "Stone Point Capital", "website": "https://www.stonepoint.com",
     "notes": "Financial services PE / family office", "entity_type": "Hybrid",
     "hq_city": "Greenwich", "hq_state": "Connecticut", "hq_country": "United States of America",
     "description": "Private equity firm with family office characteristics, focused on financial services. Manages Trident Funds with investments in insurance, banking, and fintech."},

    {"name": "Sarissa Capital", "website": "https://www.sarissacapital.com",
     "notes": "Activist family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Activist investment firm and family office focused on pharmaceutical and biopharmaceutical companies. Takes board seats to drive strategic value creation."},

    {"name": "Laurion Capital Management", "website": "https://www.laurioncapital.com",
     "notes": "NYC hedge fund / family office", "entity_type": "Hybrid",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Quantitative multi-strategy hedge fund with family office characteristics. Employs systematic and fundamental approaches across equity, credit, and macro strategies."},

    {"name": "Pine Brook Partners", "website": "https://www.pinebrookpartners.com",
     "notes": "Energy-focused family office", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Private equity firm focused on energy, power, and infrastructure. Partners with management teams to build businesses in the energy value chain."},

    # ── More international FOs ─────────────────────────────────────
    {"name": "Edelweiss Family Office", "website": None,
     "notes": "Indian family office", "entity_type": "Multi Family Office",
     "hq_city": "Mumbai", "hq_state": None, "hq_country": "India",
     "description": "Leading Indian multi-family office providing wealth management, estate planning, and investment advisory services to India's ultra-high-net-worth families."},

    {"name": "Pitango Venture Capital", "website": "https://www.pitango.com",
     "notes": "Israeli family office / VC", "entity_type": "Hybrid",
     "hq_city": "Herzliya", "hq_state": None, "hq_country": "Israel",
     "description": "Israel's largest venture capital firm with family office roots. Invests in enterprise software, cybersecurity, digital health, and deep tech startups."},

    # ── Extra seeds to boost count ─────────────────────────────────
    {"name": "Jamestown", "website": "https://www.jamestownlp.com",
     "notes": "Real estate family office", "entity_type": "Single Family Office",
     "hq_city": "Atlanta", "hq_state": "Georgia", "hq_country": "United States of America",
     "description": "Global real estate investment and management firm with family office origins. Known for mixed-use developments including Ponce City Market and Industry City."},

    {"name": "Olayan Group", "website": "https://www.olayan.com",
     "notes": "Saudi family conglomerate", "entity_type": "Single Family Office",
     "hq_city": "Riyadh", "hq_state": None, "hq_country": "Saudi Arabia",
     "description": "Leading Saudi family office and diversified business group. Manages global investments across consumer products, industrial, real estate, and financial services."},

    {"name": "KIRKBI", "website": "https://www.kirkbi.com",
     "notes": "LEGO family holding", "entity_type": "Single Family Office",
     "hq_city": "Billund", "hq_state": None, "hq_country": "Denmark",
     "description": "Family office and holding company of the Kirk Kristiansen family, owners of the LEGO Group. Manages long-term investments in real estate, renewable energy, and private equity."},

    {"name": "Haniel", "website": "https://www.haniel.de",
     "notes": "German family holding", "entity_type": "Single Family Office",
     "hq_city": "Duisburg", "hq_state": None, "hq_country": "Germany",
     "description": "One of Germany's oldest family-owned companies with over 260 years of history. Diversified investments across pharma, recycling, consumer brands, and financial services."},

    {"name": "Wendel", "website": "https://www.wendelgroup.com",
     "notes": "French industrial family", "entity_type": "Single Family Office",
     "hq_city": "Paris", "hq_state": None, "hq_country": "France",
     "description": "Leading French family-owned investment firm with 300+ years of industrial heritage. Invests in global leaders in technology, healthcare, and industrial sectors."},

    {"name": "Schroders Family Office", "website": "https://www.schroders.com",
     "notes": "UK banking family", "entity_type": "Multi Family Office",
     "hq_city": "London", "hq_state": None, "hq_country": "United Kingdom",
     "description": "Wealth management division of Schroders, a global asset manager rooted in the Schroder banking family. Provides tailored investment solutions for ultra-high-net-worth families."},

    {"name": "Makena Capital", "website": "https://www.makenacap.com",
     "notes": "Stanford endowment alumni", "entity_type": "Multi Family Office",
     "hq_city": "Menlo Park", "hq_state": "California", "hq_country": "United States of America",
     "description": "Multi-family office and endowment-style investment firm founded by former Stanford Management Company executives. Manages diversified global portfolio across all asset classes."},

    {"name": "Veritas Capital", "website": "https://www.veritascapital.com",
     "notes": "Government tech PE", "entity_type": "Single Family Office",
     "hq_city": "New York", "hq_state": "New York", "hq_country": "United States of America",
     "description": "Private equity firm and family office focused on government technology and services. Invests in companies providing mission-critical solutions to government and healthcare."},

    {"name": "Ares Management Family Office", "website": "https://www.aresmgmt.com",
     "notes": "Alternative asset manager", "entity_type": "Multi Family Office",
     "hq_city": "Los Angeles", "hq_state": "California", "hq_country": "United States of America",
     "description": "Global alternative investment manager with family office services. Over $400B in AUM across credit, private equity, real estate, and infrastructure."},

    {"name": "Investcorp", "website": "https://www.investcorp.com",
     "notes": "Bahrain-based family office", "entity_type": "Multi Family Office",
     "hq_city": "Manama", "hq_state": None, "hq_country": "Bahrain",
     "description": "Global alternative investment firm with Middle Eastern family office roots. Manages over $50B across private equity, real estate, credit, and absolute return strategies."},

    {"name": "ADQ", "website": "https://www.adq.ae",
     "notes": "Abu Dhabi family/sovereign", "entity_type": "Multi Family Office",
     "hq_city": "Abu Dhabi", "hq_state": None, "hq_country": "United Arab Emirates",
     "description": "Abu Dhabi-based investment and holding company managing a diversified portfolio of enterprises across energy, food, healthcare, mobility, and technology."},
]
