"""Contact validation module — verifies contacts via web search and email patterns."""

import re
import time
import socket
import smtplib
import logging
from typing import Optional, Dict, List, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

TITLE_PRIORITY = [
    (100, ["founder", "co-founder", "cofounder"]),
    (98, ["chairman", "chairwoman", "chairperson"]),
    (95, ["chief executive", "ceo"]),
    (90, ["chief investment", "cio"]),
    (85, ["chief financial", "cfo"]),
    (80, ["chief operating", "coo"]),
    (75, ["president"]),
    (70, ["managing partner", "managing director", "managing member"]),
    (65, ["general partner"]),
    (60, ["principal"]),
    (55, ["partner"]),
    (50, ["senior vice president", "svp"]),
    (45, ["vice president", "vp"]),
    (40, ["director"]),
    (35, ["head of"]),
    (30, ["senior advisor", "senior adviser"]),
    (25, ["portfolio manager", "fund manager"]),
    (20, ["advisor", "adviser"]),
    (15, ["analyst", "associate"]),
]

COMMON_ENGLISH_WORDS = {
    "jobs", "gates", "young", "long", "white", "brown", "green", "black",
    "king", "lee", "park", "stone", "hill", "wood", "field", "ford",
    "wells", "banks", "rice", "price", "rich", "love", "best", "may",
    "rose", "grant", "read", "page", "bell", "cross", "day", "ray",
    "bond", "cash", "kirk", "bush", "wolf", "bird", "fox", "hunt",
    "cook", "power", "new", "free", "fair", "west", "east", "north",
    "south", "summer", "winter", "spring", "noble", "good", "wise",
}


def select_best_contact(team_members: List[Dict], company_name: str = "") -> Optional[Dict]:
    if not team_members:
        return None
    scored = []
    for member in team_members:
        name = (member.get("name") or "").strip()
        title = (member.get("title") or "").strip()
        if not name or len(name) < 4:
            continue
        if company_name and name.lower() == company_name.lower():
            continue
        if " " not in name:
            continue
        score = _score_title(title)
        if member.get("email"):
            score += 5
        if member.get("linkedin"):
            score += 5
        scored.append((score, member))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]
    logger.info(f"Selected contact: {best.get('name')} ({best.get('title')}) from {len(team_members)} team members")
    return best


def _score_title(title: str) -> int:
    if not title:
        return 0
    title_lower = title.lower()
    for score, keywords in TITLE_PRIORITY:
        if any(kw in title_lower for kw in keywords):
            return score
    return 10


def _generate_email_patterns(first_name: str, last_name: str, domain: str) -> List[str]:
    f = first_name.lower().strip()
    l = last_name.lower().strip()
    if not f or not l or not domain:
        return []
    fi = f[0]
    li = l[0]
    return [
        f"{f}.{l}@{domain}", f"{f}{l}@{domain}", f"{f}@{domain}",
        f"{fi}{l}@{domain}", f"{f}{li}@{domain}", f"{fi}.{l}@{domain}",
        f"{l}.{f}@{domain}", f"{l}@{domain}", f"{l}{fi}@{domain}",
        f"{fi}{li}@{domain}",
    ]


def _validate_email_smtp(email: str, timeout: int = 5) -> bool:
    try:
        domain = email.split("@")[1]
        import dns.resolver
        try:
            mx_records = dns.resolver.resolve(domain, "MX")
            mx_host = str(mx_records[0].exchange).rstrip(".")
        except Exception:
            mx_host = domain
        server = smtplib.SMTP(timeout=timeout)
        server.connect(mx_host, 25)
        server.helo("verify.check")
        server.mail("verify@check.com")
        code, _ = server.rcpt(email)
        server.quit()
        return code in (250, 251)
    except ImportError:
        return False
    except smtplib.SMTPServerDisconnected:
        return False
    except socket.timeout:
        return False
    except Exception:
        return False


def find_email_for_contact(contact_name: str, domain: str, known_emails: List[str] = None) -> Optional[Dict]:
    if not contact_name or not domain:
        return None
    name_parts = contact_name.strip().split()
    if len(name_parts) < 2:
        return None
    first_name = name_parts[0]
    last_name = name_parts[-1]
    domain = domain.lower().strip()
    if domain.startswith("www."):
        domain = domain[4:]
    if known_emails:
        for email in known_emails:
            email_local = email.split("@")[0].lower()
            f = first_name.lower()
            l = last_name.lower()
            if any([
                email_local == f"{f}.{l}", email_local == f"{f}{l}",
                email_local == f"{f[0]}{l}", email_local == f"{f}", email_local == f"{l}",
            ]):
                return {"email": email, "confidence": "High", "source": "Website match"}
    detected_pattern = None
    if known_emails:
        detected_pattern = _detect_email_pattern(known_emails, domain)
    if detected_pattern:
        candidates = [_apply_pattern(detected_pattern, first_name, last_name, domain)]
        candidates += _generate_email_patterns(first_name, last_name, domain)
    else:
        candidates = _generate_email_patterns(first_name, last_name, domain)
    for email in candidates:
        if not email:
            continue
        if _validate_email_smtp(email):
            return {"email": email, "confidence": "Verified", "source": "Pattern + SMTP validation"}
        time.sleep(0.3)
    if detected_pattern:
        best_guess = _apply_pattern(detected_pattern, first_name, last_name, domain)
        if best_guess:
            return {"email": best_guess, "confidence": "Medium", "source": "Pattern match (unverified)"}
    return None


def _detect_email_pattern(emails: List[str], domain: str) -> Optional[str]:
    patterns_found = {}
    for email in emails:
        if "@" not in email:
            continue
        local, email_domain = email.split("@", 1)
        if email_domain.lower() != domain.lower():
            continue
        local = local.lower()
        if "." in local:
            parts = local.split(".")
            if len(parts) == 2 and parts[0].isalpha() and parts[1].isalpha():
                if len(parts[0]) > 1 and len(parts[1]) > 1:
                    patterns_found["first.last"] = patterns_found.get("first.last", 0) + 1
                elif len(parts[0]) == 1:
                    patterns_found["f.last"] = patterns_found.get("f.last", 0) + 1
        elif local.isalpha():
            if len(local) <= 3:
                patterns_found["initials"] = patterns_found.get("initials", 0) + 1
            else:
                patterns_found["firstlast"] = patterns_found.get("firstlast", 0) + 1
    if patterns_found:
        return max(patterns_found, key=patterns_found.get)
    return None


def _apply_pattern(pattern: str, first: str, last: str, domain: str) -> Optional[str]:
    f = first.lower()
    l = last.lower()
    pattern_map = {
        "first.last": f"{f}.{l}@{domain}",
        "f.last": f"{f[0]}.{l}@{domain}",
        "firstlast": f"{f}{l}@{domain}",
        "flast": f"{f[0]}{l}@{domain}",
        "first": f"{f}@{domain}",
        "initials": f"{f[0]}{l[0]}@{domain}",
    }
    return pattern_map.get(pattern)


def verify_linkedin_profile(contact_name: str, company_name: str) -> Optional[str]:
    from ..discovery.web_search import _brave_search
    if not contact_name or contact_name.lower() in ("unknown", "n/a"):
        return None
    name_parts = contact_name.lower().split()
    if len(name_parts) < 2:
        return None
    first_name = name_parts[0]
    last_name = name_parts[-1]
    middle_parts = name_parts[1:-1] if len(name_parts) > 2 else []
    generic_company_words = {
        "investment", "investments", "capital", "group", "management",
        "partners", "holdings", "fund", "funds", "family", "office",
        "advisors", "advisory", "wealth", "asset", "assets", "private",
        "global", "international", "trust", "foundation", "ventures",
        "equity", "financial", "services", "company", "corporation",
        "llc", "inc", "ltd", "the",
    }
    company_words = [
        w.lower() for w in company_name.split()
        if len(w) > 2 and w.lower() not in generic_company_words
    ]
    query = f'"{contact_name}" "{company_name}" site:linkedin.com/in/'
    try:
        results = _brave_search(query, max_results=10)
        candidates = []
        for r in results:
            url = r.get("url", "")
            title = r.get("title", "")
            description = r.get("text", "")
            if "linkedin.com/in/" not in url.lower():
                continue
            score = 0
            slug = _extract_linkedin_slug(url)
            slug_lower = slug.lower().replace("-", " ")
            first_in_slug = first_name in slug_lower
            last_in_slug = last_name in slug_lower
            if first_in_slug and last_in_slug:
                score += 50
            elif first_in_slug or last_in_slug:
                matched_part = first_name if first_in_slug else last_name
                if matched_part in COMMON_ENGLISH_WORDS:
                    score += 5
                else:
                    score += 20
            else:
                continue
            for mp in middle_parts:
                if mp in slug_lower and mp not in COMMON_ENGLISH_WORDS:
                    score += 10
            title_lower = title.lower()
            if first_name in title_lower and last_name in title_lower:
                score += 30
            elif last_name in title_lower and last_name not in COMMON_ENGLISH_WORDS:
                score += 15
            elif first_name in title_lower and first_name not in COMMON_ENGLISH_WORDS:
                score += 10
            combined_text = f"{title} {description}".lower()
            if company_words:
                matched_company_words = sum(1 for w in company_words if w in combined_text)
                if matched_company_words >= 2:
                    score += 20
                elif matched_company_words == 1:
                    score += 12
            else:
                if company_name.lower() in combined_text:
                    score += 15
            candidates.append((score, url))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_url = candidates[0]
        MIN_SCORE = 40
        if best_score < MIN_SCORE:
            return None
        clean_url = best_url.split("?")[0]
        if not clean_url.endswith("/"):
            clean_url += "/"
        logger.info(f"Verified LinkedIn (score={best_score}): {contact_name} @ {company_name} -> {clean_url}")
        return clean_url
    except Exception as e:
        logger.debug(f"LinkedIn verification failed for '{contact_name}': {e}")
    return None


def _extract_linkedin_slug(url: str) -> str:
    try:
        path = urlparse(url).path
        slug = path.replace("/in/", "").strip("/")
        slug = slug.split("/")[0]
        return slug
    except Exception:
        return ""


def validate_contact(
    contact_name: str, company_name: str, website_url: str = None,
    known_emails: List[str] = None, team_members: List[Dict] = None,
) -> Dict:
    result = {
        "contact_name": contact_name, "contact_title": None,
        "contact_linkedin": None, "contact_email": None,
        "email_confidence": "Not Found", "email_source": None,
    }
    if team_members and len(team_members) > 0:
        best_member = select_best_contact(team_members, company_name)
        if best_member:
            if not contact_name or contact_name.lower() in ("unknown", "n/a", "none"):
                result["contact_name"] = best_member["name"]
                result["contact_title"] = best_member.get("title")
                contact_name = best_member["name"]
            else:
                existing_lower = contact_name.lower().strip()
                member_lower = best_member["name"].lower().strip()
                if existing_lower == member_lower:
                    result["contact_title"] = best_member.get("title")
                elif _score_title(best_member.get("title", "")) > 60:
                    result["contact_name"] = best_member["name"]
                    result["contact_title"] = best_member.get("title")
                    contact_name = best_member["name"]
            if best_member.get("linkedin") and contact_name == best_member["name"]:
                result["contact_linkedin"] = best_member["linkedin"]
            if best_member.get("email") and contact_name == best_member["name"]:
                result["contact_email"] = best_member["email"]
                result["email_confidence"] = "High"
                result["email_source"] = "Website team page"
    if not contact_name or contact_name.lower() in ("unknown", "n/a", "none"):
        return result
    if not result["contact_linkedin"]:
        linkedin = verify_linkedin_profile(contact_name, company_name)
        if linkedin:
            result["contact_linkedin"] = linkedin
        time.sleep(0.3)
    if not result["contact_email"] and website_url:
        domain = urlparse(website_url).netloc
        if domain.startswith("www."):
            domain = domain[4:]
        email_result = find_email_for_contact(contact_name, domain, known_emails)
        if email_result:
            result["contact_email"] = email_result["email"]
            result["email_confidence"] = email_result["confidence"]
            result["email_source"] = email_result["source"]
    return result
