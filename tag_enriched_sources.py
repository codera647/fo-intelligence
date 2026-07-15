"""Tag 02_enriched.json with source attribution for LinkedIn, emails, and corporate data.

Adds metadata fields to each record:
  - _corporate_linkedin_source: "website_crawl" | null
  - _extracted_emails_source:   "website_crawl" | null
  - _linkedin_profiles_source:  "website_crawl" | null
  - _team_emails_source:        "website_crawl" | null  (if team_members have real emails)
  - _team_linkedin_source:      "website_crawl" | null  (if team_members have LinkedIn URLs)
  - _aum_source:                "PipelineRoad" | "website_crawl" | "unknown"
  - _needs_tavily_enrichment:   True if missing contact emails/LinkedIn/corporate data
  - _tavily_enrichment_targets: list of what Tavily should look for

Run:
    python tag_enriched_sources.py

Input:  data/pipeline/02_enriched_family_offices.json
Output: data/pipeline/02_enriched_family_offices.json  (overwritten, backup created)
"""

import json
import shutil
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent / "data" / "pipeline"
INPUT_PATH = PIPELINE_DIR / "02_enriched_family_offices.json"
BACKUP_PATH = PIPELINE_DIR / "02_enriched_family_offices.pre_tag_backup.json"

# Placeholder patterns — these are NOT real contacts
PLACEHOLDER_NAMES = {
    "full name", "john doe", "jane doe", "name", "first last",
    "team member", "contact person", "unknown", "n/a",
    "leadership team", "management team", "executive team",
}

PLACEHOLDER_EMAILS = {
    "email@domain.com", "email@domain.com or null",
    "null", "n/a", "", "info@example.com",
}


def _is_real_email(email):
    """Check if an email is a real extracted email, not a placeholder."""
    if not email or not isinstance(email, str):
        return False
    email_lower = email.strip().lower()
    if email_lower in PLACEHOLDER_EMAILS:
        return False
    if "@" not in email or "." not in email.split("@")[-1]:
        return False
    return True


def _is_real_name(name):
    """Check if a contact name is real, not a placeholder."""
    if not name or not isinstance(name, str):
        return False
    name_lower = name.strip().lower()
    if name_lower in PLACEHOLDER_NAMES:
        return False
    if len(name.strip().split()) < 2:
        return False
    return True


def _is_real_linkedin(url):
    """Check if a LinkedIn URL is real."""
    if not url or not isinstance(url, str):
        return False
    url_lower = url.strip().lower()
    if "linkedin.com" not in url_lower:
        return False
    if url_lower in ("https://linkedin.com/in/... or null", "null"):
        return False
    return True


def tag_record(rec):
    """Add source attribution and Tavily enrichment flags to a record."""
    crawl_status = rec.get("crawl_status", "")
    source = rec.get("source", "unknown")
    is_enriched = crawl_status == "Enriched"

    # ── Corporate LinkedIn source ──
    corp_linkedin = rec.get("corporate_linkedin")
    if corp_linkedin and _is_real_linkedin(corp_linkedin):
        rec["_corporate_linkedin_source"] = "website_crawl"
    else:
        rec["_corporate_linkedin_source"] = None

    # ── Extracted emails source ──
    extracted_emails = rec.get("extracted_emails", [])
    real_extracted = [e for e in extracted_emails if _is_real_email(e)]
    if real_extracted:
        rec["_extracted_emails_source"] = "website_crawl"
    else:
        rec["_extracted_emails_source"] = None

    # ── LinkedIn profiles source ──
    linkedin_profiles = rec.get("linkedin_profiles", [])
    real_profiles = [u for u in linkedin_profiles if _is_real_linkedin(u)]
    if real_profiles:
        rec["_linkedin_profiles_source"] = "website_crawl"
    else:
        rec["_linkedin_profiles_source"] = None

    # ── Team member emails/LinkedIn from web crawl ──
    team = rec.get("team_members", [])
    team_has_real_email = False
    team_has_real_linkedin = False
    real_team_count = 0

    for member in team:
        if not _is_real_name(member.get("name")):
            continue
        real_team_count += 1
        if _is_real_email(member.get("email")):
            team_has_real_email = True
        if _is_real_linkedin(member.get("linkedin_url")):
            team_has_real_linkedin = True

    rec["_team_emails_source"] = "website_crawl" if (team_has_real_email and is_enriched) else None
    rec["_team_linkedin_source"] = "website_crawl" if (team_has_real_linkedin and is_enriched) else None
    rec["_real_team_member_count"] = real_team_count

    # ── AUM source — fix from dates to actual source name ──
    if source == "PipelineRoad":
        rec["_aum_source"] = "PipelineRoad"
    elif is_enriched and rec.get("website"):
        rec["_aum_source"] = "PipelineRoad"  # AUM always comes from PipelineRoad discovery
    else:
        rec["_aum_source"] = "PipelineRoad"  # All AUM in this dataset is from PipelineRoad

    # ── Determine what Tavily should enrich ──
    tavily_targets = []

    # Need corporate LinkedIn?
    if not rec["_corporate_linkedin_source"]:
        tavily_targets.append("corporate_linkedin")

    # Need contact emails?
    if not real_extracted and not team_has_real_email:
        tavily_targets.append("contact_emails")

    # Need LinkedIn profiles for team members?
    if not real_profiles and not team_has_real_linkedin:
        tavily_targets.append("team_linkedin_profiles")

    # Need recent activity?
    activity = rec.get("recent_activity", {})
    if not activity or not activity.get("title"):
        tavily_targets.append("recent_activity")

    # Need real team members at all?
    if real_team_count == 0:
        tavily_targets.append("team_discovery")

    rec["_needs_tavily_enrichment"] = len(tavily_targets) > 0
    rec["_tavily_enrichment_targets"] = tavily_targets

    # ── Summary source quality tier ──
    has_any_contact_data = (
        rec["_corporate_linkedin_source"]
        or rec["_extracted_emails_source"]
        or rec["_linkedin_profiles_source"]
        or rec["_team_emails_source"]
        or rec["_team_linkedin_source"]
    )

    if has_any_contact_data and real_team_count >= 2:
        rec["_contact_data_tier"] = "rich"      # Multiple sources from web
    elif has_any_contact_data:
        rec["_contact_data_tier"] = "partial"   # Some web data but gaps
    elif is_enriched:
        rec["_contact_data_tier"] = "crawled_no_contacts"  # Website crawled but no contacts found
    elif crawl_status == "CrawlFailed":
        rec["_contact_data_tier"] = "crawl_failed"  # Website exists but couldn't crawl
    else:
        rec["_contact_data_tier"] = "no_website"    # No website at all

    return rec


def main():
    # Load
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"Loaded {len(records)} records from {INPUT_PATH}")

    # Backup
    shutil.copy2(INPUT_PATH, BACKUP_PATH)
    print(f"Backup saved → {BACKUP_PATH}")

    # Tag all records
    tagged = [tag_record(rec) for rec in records]

    # Save
    with open(INPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(tagged, f, indent=2, ensure_ascii=False)

    print(f"Saved tagged records → {INPUT_PATH}")

    # ── Summary stats ──
    tiers = {}
    needs_tavily = 0
    tavily_target_counts = {}
    source_counts = {
        "corporate_linkedin": 0,
        "extracted_emails": 0,
        "linkedin_profiles": 0,
        "team_emails": 0,
        "team_linkedin": 0,
    }

    for rec in tagged:
        tier = rec.get("_contact_data_tier", "unknown")
        tiers[tier] = tiers.get(tier, 0) + 1

        if rec.get("_needs_tavily_enrichment"):
            needs_tavily += 1

        for target in rec.get("_tavily_enrichment_targets", []):
            tavily_target_counts[target] = tavily_target_counts.get(target, 0) + 1

        if rec.get("_corporate_linkedin_source"):
            source_counts["corporate_linkedin"] += 1
        if rec.get("_extracted_emails_source"):
            source_counts["extracted_emails"] += 1
        if rec.get("_linkedin_profiles_source"):
            source_counts["linkedin_profiles"] += 1
        if rec.get("_team_emails_source"):
            source_counts["team_emails"] += 1
        if rec.get("_team_linkedin_source"):
            source_counts["team_linkedin"] += 1

    print()
    print("=" * 55)
    print("SOURCE ATTRIBUTION SUMMARY")
    print("=" * 55)
    print()
    print("Web-crawled data found:")
    for key, count in source_counts.items():
        bar = "█" * count
        print(f"  {key:25s}: {count:3d} {bar}")

    print()
    print("Contact data tier distribution:")
    for tier in ["rich", "partial", "crawled_no_contacts", "crawl_failed", "no_website"]:
        count = tiers.get(tier, 0)
        bar = "█" * count
        print(f"  {tier:25s}: {count:3d} {bar}")

    print()
    print(f"FOs needing Tavily enrichment: {needs_tavily}/{len(tagged)}")
    print()
    print("Tavily enrichment targets:")
    for target, count in sorted(tavily_target_counts.items(), key=lambda x: -x[1]):
        print(f"  {target:25s}: {count:3d} FOs")

    print()
    print("=" * 55)


if __name__ == "__main__":
    main()
