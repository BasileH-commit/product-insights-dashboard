#!/usr/bin/env python3
"""
Data fetching module for the Product Insights Dashboard.
Reuses API connections from analyze_notion.py.
Supports both local .env and Streamlit Cloud secrets.
"""

import os
import requests
import calendar
from datetime import datetime, timedelta
from collections import Counter, defaultdict

# Try Streamlit secrets first (for cloud), then fall back to dotenv (local)
def get_secret(key, default=None):
    """Get secret from Streamlit Cloud or local .env"""
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    # Fall back to environment variables
    from dotenv import load_dotenv
    load_dotenv()
    return os.getenv(key, default)

# Zendesk Config
ZENDESK_SUBDOMAIN = get_secret("ZENDESK_SUBDOMAIN", "smily1")
ZENDESK_EMAIL = get_secret("ZENDESK_EMAIL")
ZENDESK_TOKEN = get_secret("ZENDESK_TOKEN")
ZENDESK_BASE_URL = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2"
ZENDESK_AUTH = (f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)

# Modjo Config
MODJO_API_KEY = get_secret("MODJO_API_KEY")
MODJO_BASE_URL = "https://api.modjo.ai/v1"
MODJO_HEADERS = {
    "X-API-KEY": MODJO_API_KEY,
    "Content-Type": "application/json"
}

# Categories (same as analyze_notion.py)
CATEGORIES_DETAILED = {
    "Booking.com – New Connections": ["new listing", "connect booking", "connexion booking", "add listing", "nouvelle annonce", "ajout booking", "new rental", "connect new", "nouvelle connexion", "capi", "add new"],
    "Booking.com – Sync Issues": ["booking sync", "booking calendar", "booking availability", "booking.com sync", "synchronisation booking", "booking error", "booking blocked"],
    "Booking.com – General": ["booking.com", "booking", "b.com", "bcom"],
    "SmilyPay / Payment Gateway": ["smilypay", "payment", "paiement", "rib", "3ds", "virement", "versement", "transfer", "document rejected", "production", "iban", "kyc"],
    "Rental Management": ["rental", "logement", "hébergement", "restore", "restaurer", "duplicate", "dupliquer", "config", "configuration", "property"],
    "Website / Experience": ["website", "site web", "widget", "landing", "page web", "experience site"],
    "Notifications / Automations": ["notification", "email", "template", "automation", "automatisation", "alert"],
    "Airbnb – Sync Issues": ["airbnb sync", "airbnb calendar", "airbnb photo", "airbnb listing sync", "synchronisation airbnb"],
    "Airbnb – General": ["airbnb", "air bnb"],
    "Cancellation Protection": ["cancellation protection", "protection annulation", "annulation", "cancel protection"],
    "Vrbo / Abritel": ["vrbo", "abritel", "homeaway"],
    "Pricing": ["pricing", "prix", "price", "tarif", "rate", "markup", "mark-up"],
    "Account / Billing": ["account", "billing", "invoice", "facture", "subscription", "abonnement"],
}


def fetch_zendesk_organizations():
    """Fetch all organizations and build ID->Name lookup."""
    orgs = {}
    url = f"{ZENDESK_BASE_URL}/organizations.json?per_page=100"

    while url:
        try:
            response = requests.get(url, auth=ZENDESK_AUTH, timeout=30)
            if response.status_code != 200:
                break

            data = response.json()
            for org in data.get("organizations", []):
                orgs[org["id"]] = org["name"]

            url = data.get("next_page")
        except Exception:
            break

    return orgs


def fetch_single_organization(org_id):
    """Fetch a single organization by ID."""
    url = f"{ZENDESK_BASE_URL}/organizations/{org_id}.json"
    try:
        response = requests.get(url, auth=ZENDESK_AUTH, timeout=10)
        if response.status_code == 200:
            return response.json().get("organization", {}).get("name")
    except Exception:
        pass
    return None


def fetch_zendesk_users():
    """Fetch all agents/users including admins."""
    users = {}

    # Fetch agents and admins
    for role in ["agent", "admin"]:
        url = f"{ZENDESK_BASE_URL}/users.json?role={role}&per_page=100"

        while url:
            try:
                response = requests.get(url, auth=ZENDESK_AUTH, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    for user in data.get("users", []):
                        users[user["id"]] = user["name"]
                    url = data.get("next_page")
                else:
                    break
            except Exception:
                break

    return users


def fetch_single_user(user_id):
    """Fetch a single user by ID."""
    url = f"{ZENDESK_BASE_URL}/users/{user_id}.json"
    try:
        response = requests.get(url, auth=ZENDESK_AUTH, timeout=10)
        if response.status_code == 200:
            return response.json().get("user", {}).get("name")
    except Exception:
        pass
    return None


def fetch_ticket_comments(ticket_id):
    """Fetch comments for a specific ticket to analyze CS responses."""
    url = f"{ZENDESK_BASE_URL}/tickets/{ticket_id}/comments.json"
    try:
        response = requests.get(url, auth=ZENDESK_AUTH, timeout=10)
        if response.status_code == 200:
            return response.json().get("comments", [])
    except Exception:
        pass
    return []


def fetch_zendesk_tickets(days=None, start_date=None, end_date=None):
    """
    Fetch recent tickets from Zendesk API.

    Args:
        days: Number of days back (if using day-based mode)
        start_date: Start date as datetime object (if using date range mode)
        end_date: End date as datetime object (if using date range mode)
    """
    if start_date and end_date:
        # Use date range
        cutoff_start = start_date.strftime("%Y-%m-%d")
        cutoff_end = end_date.strftime("%Y-%m-%d")
        query = f"type:ticket created>={cutoff_start} created<={cutoff_end}"
    else:
        # Use days back (default behavior)
        if days is None:
            days = 7
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        query = f"type:ticket created>{cutoff}"

    tickets = []

    url = f"{ZENDESK_BASE_URL}/search.json"
    params = {
        "query": query,
        "per_page": 100,
        "sort_by": "created_at",
        "sort_order": "desc"
    }

    page = 1
    while True:
        params["page"] = page
        try:
            response = requests.get(url, params=params, auth=ZENDESK_AUTH, timeout=30)

            if response.status_code != 200:
                break

            data = response.json()
            results = data.get("results", [])

            if not results:
                break

            tickets.extend(results)

            if len(results) < 100:
                break

            page += 1
            if page > 10:
                break
        except Exception:
            break

    return tickets


def enrich_tickets_with_org_names(tickets, org_lookup):
    """Add organization names to tickets, fetching missing orgs on-demand."""
    for ticket in tickets:
        org_id = ticket.get("organization_id")
        if org_id:
            if org_id in org_lookup:
                ticket["organization_name"] = org_lookup[org_id]
            else:
                org_name = fetch_single_organization(org_id)
                if org_name:
                    org_lookup[org_id] = org_name
                    ticket["organization_name"] = org_name
                else:
                    ticket["organization_name"] = None
        else:
            ticket["organization_name"] = None
    return tickets


def enrich_tickets_with_agent_names(tickets, agent_lookup):
    """Add agent names to tickets, fetching missing agents on-demand."""
    for ticket in tickets:
        assignee_id = ticket.get("assignee_id")
        if assignee_id:
            if assignee_id in agent_lookup:
                ticket["agent_name"] = agent_lookup[assignee_id]
            else:
                # Fetch missing agent on-demand
                agent_name = fetch_single_user(assignee_id)
                if agent_name:
                    agent_lookup[assignee_id] = agent_name
                    ticket["agent_name"] = agent_name
                else:
                    ticket["agent_name"] = None
        else:
            ticket["agent_name"] = None
    return tickets


def fetch_modjo_calls(days=None, start_date=None, end_date=None):
    """
    Fetch calls from Modjo API.

    Args:
        days: Number of days back (if using day-based mode)
        start_date: Start date as datetime object (if using date range mode)
        end_date: End date as datetime object (if using date range mode)
    """
    if not MODJO_API_KEY:
        return []

    if start_date and end_date:
        # Use date range
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
    else:
        # Use days back (default behavior)
        if days is None:
            days = 7
        start_date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date_str = datetime.now().strftime("%Y-%m-%d")

    url = f"{MODJO_BASE_URL}/calls/search"
    payload = {
        "filters": {
            "date": {
                "start": start_date_str,
                "end": end_date_str
            }
        },
        "page": 1,
        "pageSize": 100
    }

    calls = []

    try:
        response = requests.post(url, headers=MODJO_HEADERS, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            calls = data.get("calls", []) or data.get("data", []) or []
    except Exception:
        pass

    return calls


def categorize_detailed(text):
    """Classify text into a detailed category."""
    text_lower = text.lower()

    # Check categories in order (more specific first)
    ordered_categories = [
        "Booking.com – New Connections",
        "Booking.com – Sync Issues",
        "SmilyPay / Payment Gateway",
        "Airbnb – Sync Issues",
        "Cancellation Protection",
        "Notifications / Automations",
        "Rental Management",
        "Website / Experience",
        "Pricing",
        "Account / Billing",
        "Vrbo / Abritel",
        "Booking.com – General",
        "Airbnb – General",
    ]

    for category in ordered_categories:
        keywords = CATEGORIES_DETAILED.get(category, [])
        if any(kw in text_lower for kw in keywords):
            return category

    return "Other"


def fetch_all_data(mode="days", days_back=None, year=None, month=None):
    """
    Fetch all data needed for the dashboard.

    Supports two modes:
    - mode="days": Fetches last N days vs previous N days
    - mode="month": Fetches specific calendar month vs previous calendar month

    Args:
        mode: "days" or "month"
        days_back: Number of days (for mode="days")
        year: Year (for mode="month")
        month: Month 1-12 (for mode="month")
    """
    # Fetch lookups
    org_lookup = fetch_zendesk_organizations()
    agent_lookup = fetch_zendesk_users()

    if mode == "month":
        # Calculate calendar month boundaries
        # First day of selected month
        first_day_this_month = datetime(year, month, 1)

        # Last day of selected month
        last_day_num = calendar.monthrange(year, month)[1]
        last_day_this_month = datetime(year, month, last_day_num, 23, 59, 59)

        # Calculate previous month
        if month == 1:
            prev_year = year - 1
            prev_month = 12
        else:
            prev_year = year
            prev_month = month - 1

        first_day_prev_month = datetime(prev_year, prev_month, 1)
        last_day_prev_num = calendar.monthrange(prev_year, prev_month)[1]
        last_day_prev_month = datetime(prev_year, prev_month, last_day_prev_num, 23, 59, 59)

        # Fetch tickets for both months - fetch separately for clarity
        now = datetime.now()

        # Fetch current month tickets (up to today if current month, full month if past)
        if year == now.year and month == now.month:
            end_date_this_month = now
        else:
            end_date_this_month = last_day_this_month

        # Fetch this month's tickets
        tickets_this_period = fetch_zendesk_tickets(start_date=first_day_this_month, end_date=end_date_this_month)
        tickets_this_period = enrich_tickets_with_org_names(tickets_this_period, org_lookup)
        tickets_this_period = enrich_tickets_with_agent_names(tickets_this_period, agent_lookup)

        # Fetch previous month's tickets
        tickets_prev_period = fetch_zendesk_tickets(start_date=first_day_prev_month, end_date=last_day_prev_month)
        tickets_prev_period = enrich_tickets_with_org_names(tickets_prev_period, org_lookup)
        tickets_prev_period = enrich_tickets_with_agent_names(tickets_prev_period, agent_lookup)

        # Fetch Modjo calls for both months
        modjo_this_period = fetch_modjo_calls(start_date=first_day_this_month, end_date=end_date_this_month)
        modjo_prev_period = fetch_modjo_calls(start_date=first_day_prev_month, end_date=last_day_prev_month)

    else:  # mode == "days"
        if days_back is None:
            days_back = 7

        # Fetch this period's tickets
        tickets_this_period = fetch_zendesk_tickets(days=days_back)
        tickets_this_period = enrich_tickets_with_org_names(tickets_this_period, org_lookup)
        tickets_this_period = enrich_tickets_with_agent_names(tickets_this_period, agent_lookup)

        # Fetch previous period's tickets (for comparison)
        tickets_all = fetch_zendesk_tickets(days=days_back * 2)
        tickets_all = enrich_tickets_with_org_names(tickets_all, org_lookup)
        tickets_all = enrich_tickets_with_agent_names(tickets_all, agent_lookup)

        # Separate this period and last period
        this_period_ids = {t["id"] for t in tickets_this_period}
        tickets_prev_period = [t for t in tickets_all if t["id"] not in this_period_ids]

        # Fetch Modjo calls
        modjo_this_period = fetch_modjo_calls(days=days_back)
        modjo_prev_period = fetch_modjo_calls(days=days_back * 2)
        modjo_prev_period = [c for c in modjo_prev_period if c not in modjo_this_period]

    # Categorize tickets
    categories_this_period = Counter()
    categories_prev_period = Counter()

    for ticket in tickets_this_period:
        text = f"{ticket.get('subject', '')} {(ticket.get('description') or '')[:200]}"
        cat = categorize_detailed(text)
        ticket["category"] = cat
        categories_this_period[cat] += 1

    for ticket in tickets_prev_period:
        text = f"{ticket.get('subject', '')} {(ticket.get('description') or '')[:200]}"
        cat = categorize_detailed(text)
        ticket["category"] = cat
        categories_prev_period[cat] += 1

    # Return data structure (keep keys for backward compatibility)
    return {
        "tickets_this_week": tickets_this_period,
        "tickets_last_week": tickets_prev_period,
        "categories_this_week": dict(categories_this_period),
        "categories_last_week": dict(categories_prev_period),
        "modjo_this_week": modjo_this_period,
        "modjo_last_week": modjo_prev_period,
        "org_lookup": org_lookup,
        "agent_lookup": agent_lookup,
    }


def get_category_breakdown(tickets_tw, tickets_lw):
    """Get category counts with comparison."""
    categories_tw = Counter()
    categories_lw = Counter()

    for ticket in tickets_tw:
        cat = ticket.get("category", "Other")
        categories_tw[cat] += 1

    for ticket in tickets_lw:
        cat = ticket.get("category", "Other")
        categories_lw[cat] += 1

    result = []
    all_cats = set(list(categories_tw.keys()) + list(categories_lw.keys()))

    for cat in all_cats:
        tw = categories_tw.get(cat, 0)
        lw = categories_lw.get(cat, 0)
        delta = tw - lw

        if lw > 0:
            wow_pct = ((tw - lw) / lw) * 100
            wow_str = f"{wow_pct:+.1f}%"
        elif tw > 0:
            wow_str = "🆕 New"
        else:
            wow_str = "—"

        result.append({
            "Category": cat,
            "This Period": tw,
            "Last Period": lw,
            "Δ": delta,
            "Change %": wow_str
        })

    return sorted(result, key=lambda x: -x["This Period"])


def get_subcategory_breakdown(tickets_tw, tickets_lw, parent_category):
    """Get subcategory breakdown for a specific category."""
    # Subcategories are based on common subject patterns
    subcats_tw = Counter()
    subcats_lw = Counter()

    def extract_subcategory(subject):
        """Extract a subcategory from subject."""
        subject_lower = subject.lower()

        # Common subcategory patterns
        patterns = {
            "Adding new channel": ["add", "new", "connect", "nouvelle"],
            "Rates/Pricing sync": ["rate", "price", "tarif", "prix"],
            "Calendar sync": ["calendar", "availability", "disponibilité", "calendrier"],
            "Photos sync": ["photo", "image", "picture"],
            "Listing blocked": ["blocked", "bloqué", "suspended", "suspendu"],
            "Mapping issues": ["mapping", "match", "link"],
            "Reservations": ["reservation", "booking", "réservation"],
            "Configuration": ["config", "setup", "paramètre", "setting"],
            "Documents": ["document", "kyc", "identity", "iban"],
            "Payments": ["payment", "paiement", "transfer", "virement"],
            "Notifications": ["notification", "email", "alert"],
        }

        for subcat, keywords in patterns.items():
            if any(kw in subject_lower for kw in keywords):
                return subcat

        return "Other"

    # Filter tickets by parent category
    for ticket in tickets_tw:
        if ticket.get("category") == parent_category:
            subcat = extract_subcategory(ticket.get("subject", ""))
            subcats_tw[subcat] += 1

    for ticket in tickets_lw:
        if ticket.get("category") == parent_category:
            subcat = extract_subcategory(ticket.get("subject", ""))
            subcats_lw[subcat] += 1

    result = []
    all_subcats = set(list(subcats_tw.keys()) + list(subcats_lw.keys()))

    for subcat in all_subcats:
        tw = subcats_tw.get(subcat, 0)
        lw = subcats_lw.get(subcat, 0)
        delta = tw - lw

        if lw > 0:
            wow_pct = ((tw - lw) / lw) * 100
            wow_str = f"{wow_pct:+.1f}%"
        elif tw > 0:
            wow_str = "🆕 New"
        else:
            wow_str = "—"

        result.append({
            "Subcategory": subcat,
            "This Period": tw,
            "Last Period": lw,
            "Δ": delta,
            "Change %": wow_str
        })

    return sorted(result, key=lambda x: -x["This Period"])


def get_top_issues(tickets_tw, tickets_lw, limit=15):
    """Get top issues by ticket count."""
    issues_tw = defaultdict(lambda: {"count": 0, "customers": set()})
    issues_lw = defaultdict(lambda: {"count": 0})

    for ticket in tickets_tw:
        subject = ticket.get("subject", "")[:60]
        if subject:
            issues_tw[subject]["count"] += 1
            org_name = ticket.get("organization_name")
            if org_name:
                issues_tw[subject]["customers"].add(org_name)

    for ticket in tickets_lw:
        subject = ticket.get("subject", "")[:60]
        if subject:
            issues_lw[subject]["count"] += 1

    result = []
    for issue, data in sorted(issues_tw.items(), key=lambda x: -x[1]["count"])[:limit]:
        tw = data["count"]
        lw = issues_lw.get(issue, {}).get("count", 0)

        if lw > 0:
            delta_pct = ((tw - lw) / lw) * 100
            if delta_pct > 0:
                trend = f"▲ +{delta_pct:.0f}%"
            elif delta_pct < 0:
                trend = f"▼ {delta_pct:.0f}%"
            else:
                trend = "➡️ 0%"
        else:
            trend = "🆕 New"

        result.append({
            "Issue": issue,
            "Count": tw,
            "Customers": len(data["customers"]),
            "Trend": trend
        })

    return result


def get_top_customers(tickets_tw, tickets_lw, limit=15):
    """Get top customers by ticket volume."""
    customers_tw = Counter()
    customers_lw = Counter()

    for ticket in tickets_tw:
        org_name = ticket.get("organization_name")
        if org_name:
            customers_tw[org_name] += 1

    for ticket in tickets_lw:
        org_name = ticket.get("organization_name")
        if org_name:
            customers_lw[org_name] += 1

    result = []
    for customer, count in customers_tw.most_common(limit):
        lw = customers_lw.get(customer, 0)

        if lw > 0:
            delta_pct = ((count - lw) / lw) * 100
            if delta_pct > 0:
                trend = f"▲ +{delta_pct:.0f}%"
            elif delta_pct < 0:
                trend = f"▼ {delta_pct:.0f}%"
            else:
                trend = "➡️ 0%"
        else:
            trend = "🆕 New"

        result.append({
            "Customer": customer,
            "Tickets": count,
            "Last Period": lw,
            "Trend": trend
        })

    return result


def get_agent_stats(tickets_tw, tickets_lw):
    """Get agent performance statistics."""
    agents_tw = defaultdict(lambda: {"assigned": 0, "solved": 0})
    agents_lw = defaultdict(lambda: {"assigned": 0})

    for ticket in tickets_tw:
        agent = ticket.get("agent_name")
        if agent:
            agents_tw[agent]["assigned"] += 1
            if ticket.get("status") == "solved":
                agents_tw[agent]["solved"] += 1

    for ticket in tickets_lw:
        agent = ticket.get("agent_name")
        if agent:
            agents_lw[agent]["assigned"] += 1

    result = []
    for agent, data in sorted(agents_tw.items(), key=lambda x: -x[1]["assigned"]):
        assigned = data["assigned"]
        solved = data["solved"]
        rate = (solved / assigned * 100) if assigned > 0 else 0

        lw_assigned = agents_lw.get(agent, {}).get("assigned", 0)
        if lw_assigned > 0:
            delta_pct = ((assigned - lw_assigned) / lw_assigned) * 100
            trend = f"{delta_pct:+.0f}%"
        else:
            trend = "🆕 New"

        result.append({
            "Agent": agent,
            "Assigned": assigned,
            "Solved": solved,
            "Solve Rate": f"{rate:.0f}%",
            "Change": trend
        })

    return result


def get_modjo_summary(calls_tw, calls_lw):
    """Get Modjo call summary."""
    return {
        "total_this_week": len(calls_tw),
        "total_last_week": len(calls_lw),
        "change": len(calls_tw) - len(calls_lw)
    }


def generate_actionable_insights(tickets_tw, tickets_lw, categories_tw, categories_lw):
    """
    Analyze ticket patterns and generate actionable insights and opportunities.

    Returns a list of insight dictionaries with:
    - category: The category/area of concern
    - severity: "high", "medium", "low"
    - trend: "growing", "stable", "declining"
    - insight: Description of the issue
    - action: Suggested action to take
    - impact: Potential impact of addressing this
    """
    insights = []

    # 1. Analyze high-volume categories
    total_tickets = len(tickets_tw)
    for category, count in categories_tw.items():
        if count == 0:
            continue

        percentage = (count / total_tickets * 100) if total_tickets > 0 else 0
        prev_count = categories_lw.get(category, 0)

        # Calculate growth rate
        if prev_count > 0:
            growth_rate = ((count - prev_count) / prev_count) * 100
        else:
            growth_rate = 100 if count > 0 else 0

        # High volume categories (>15% of tickets)
        if percentage > 15:
            if "Booking.com" in category:
                if "New Connections" in category:
                    insights.append({
                        "category": "Booking.com Onboarding",
                        "severity": "high" if growth_rate > 20 else "medium",
                        "trend": "growing" if growth_rate > 10 else "stable",
                        "insight": f"{count} tickets ({percentage:.1f}%) about connecting new Booking.com listings. {growth_rate:+.0f}% change.",
                        "action": "Review onboarding flow UX. Check for common blockers in connection wizard. Consider in-app video tutorial.",
                        "impact": "Could reduce 30-40% of support tickets if self-service is improved."
                    })
                elif "Sync Issues" in category:
                    insights.append({
                        "category": "Booking.com Sync Reliability",
                        "severity": "high",
                        "trend": "growing" if growth_rate > 10 else "stable",
                        "insight": f"{count} sync issues ({percentage:.1f}%). Common problems: calendar, photos, availability.",
                        "action": "Deep dive into Booking.com API error logs. Identify most common sync failures. Implement auto-retry logic.",
                        "impact": "Sync reliability is critical for trust. High priority to investigate API response patterns."
                    })
                else:
                    insights.append({
                        "category": "Booking.com General",
                        "severity": "medium",
                        "trend": "growing" if growth_rate > 10 else "stable",
                        "insight": f"{count} general Booking.com tickets ({percentage:.1f}%).",
                        "action": "Analyze ticket subjects to identify specific sub-patterns. May need better categorization.",
                        "impact": "Breaking down generic issues into specific problems will help prioritize fixes."
                    })

            elif "SmilyPay" in category or "Payment" in category:
                insights.append({
                    "category": "SmilyPay KYC/Documents",
                    "severity": "high" if growth_rate > 15 else "medium",
                    "trend": "growing" if growth_rate > 10 else "stable",
                    "insight": f"{count} payment/document issues ({percentage:.1f}%). Often document rejections.",
                    "action": "Review KYC requirements clarity. Add better error messages explaining why documents are rejected. Create FAQ.",
                    "impact": "Payment setup friction directly impacts revenue. Streamlining KYC could reduce 25-30% of these tickets."
                })

        # Fast-growing categories (>50% growth regardless of volume)
        if growth_rate > 50 and count > 3:
            insights.append({
                "category": category,
                "severity": "medium",
                "trend": "growing",
                "insight": f"{category} growing rapidly: {growth_rate:+.0f}% ({prev_count} → {count} tickets).",
                "action": f"Investigate recent changes or issues in {category}. May indicate new bug or changed workflow.",
                "impact": "Early detection of emerging issues. Address before it becomes high-volume."
            })

    # 2. Analyze recurring issue patterns from subjects
    issue_patterns = defaultdict(int)
    for ticket in tickets_tw:
        subject = ticket.get("subject", "").lower()

        # Pattern matching for common issues
        if "sync" in subject or "synchronisation" in subject:
            issue_patterns["sync_issues"] += 1
        if "connect" in subject or "connexion" in subject or "add" in subject:
            issue_patterns["connection_issues"] += 1
        if "document" in subject and ("reject" in subject or "rejet" in subject):
            issue_patterns["document_rejection"] += 1
        if "blocked" in subject or "bloqué" in subject or "suspended" in subject:
            issue_patterns["listing_blocked"] += 1
        if "calendar" in subject or "calendrier" in subject or "availability" in subject:
            issue_patterns["calendar_issues"] += 1
        if "photo" in subject or "image" in subject:
            issue_patterns["photo_issues"] += 1
        if "price" in subject or "prix" in subject or "tarif" in subject:
            issue_patterns["pricing_issues"] += 1

    # Generate insights from patterns
    if issue_patterns["sync_issues"] > total_tickets * 0.10:
        insights.append({
            "category": "Sync Reliability",
            "severity": "high",
            "trend": "stable",
            "insight": f"{issue_patterns['sync_issues']} tickets mention sync issues. Cross-channel problem.",
            "action": "Audit sync infrastructure. Check API rate limits, error handling, and retry logic. Monitor sync job success rates.",
            "impact": "Sync is core functionality. Reliability improvements affect all channels (Booking, Airbnb, Vrbo)."
        })

    if issue_patterns["document_rejection"] > 5:
        insights.append({
            "category": "Payment Onboarding UX",
            "severity": "medium",
            "trend": "stable",
            "insight": f"{issue_patterns['document_rejection']} tickets about rejected documents.",
            "action": "Improve document upload UX: show examples, clarify requirements, add validation before submission.",
            "impact": "Smoother payment onboarding = faster time-to-revenue for customers."
        })

    if issue_patterns["listing_blocked"] > 5:
        insights.append({
            "category": "Listing Moderation",
            "severity": "high",
            "trend": "stable",
            "insight": f"{issue_patterns['listing_blocked']} tickets about blocked/suspended listings.",
            "action": "Review common reasons for blocking. Add proactive warnings before listing gets blocked. Improve error messaging.",
            "impact": "Blocked listings = lost revenue for customers. Better prevention reduces panic tickets."
        })

    # 3. Analyze customer concentration risk
    customer_tickets = Counter()
    for ticket in tickets_tw:
        org = ticket.get("organization_name")
        if org:
            customer_tickets[org] += 1

    top_customer, top_count = customer_tickets.most_common(1)[0] if customer_tickets else (None, 0)
    if top_count > total_tickets * 0.10:  # One customer >10% of tickets
        insights.append({
            "category": "Customer Success",
            "severity": "medium",
            "trend": "stable",
            "insight": f"Top customer '{top_customer}' has {top_count} tickets ({top_count/total_tickets*100:.1f}%).",
            "action": "Schedule call with this customer. Identify systemic issues or training gaps. Consider dedicated support.",
            "impact": "High-volume customers may churn if issues persist. Proactive engagement critical."
        })

    # 4. Identify opportunities from declining categories (good news)
    declining_categories = []
    for category, count in categories_tw.items():
        prev_count = categories_lw.get(category, 0)
        if prev_count > 10 and count > 0:
            decline_rate = ((count - prev_count) / prev_count) * 100
            if decline_rate < -30:
                declining_categories.append((category, decline_rate, prev_count, count))

    if declining_categories:
        best_improvement = max(declining_categories, key=lambda x: abs(x[1]))
        insights.append({
            "category": "Success Story",
            "severity": "low",
            "trend": "declining",
            "insight": f"✅ {best_improvement[0]} decreased {best_improvement[1]:.0f}% ({best_improvement[2]} → {best_improvement[3]}).",
            "action": "Document what changed. Was it a bug fix, UX improvement, or documentation? Replicate for other categories.",
            "impact": "Learn from successes to improve other problem areas."
        })

    # 5. Check for notification/automation opportunities
    if issue_patterns["connection_issues"] > total_tickets * 0.15:
        insights.append({
            "category": "Self-Service Onboarding",
            "severity": "medium",
            "trend": "stable",
            "insight": f"{issue_patterns['connection_issues']} connection/setup tickets. Onboarding friction.",
            "action": "Add interactive onboarding checklist. Create video walkthroughs. Implement in-app tooltips for first connection.",
            "impact": "Better onboarding = faster activation, lower support burden, improved NPS."
        })

    # Sort by severity (high first) and trend (growing first)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    trend_order = {"growing": 0, "stable": 1, "declining": 2}

    insights.sort(key=lambda x: (severity_order[x["severity"]], trend_order[x["trend"]]))

    return insights


def deep_dive_analysis(tickets, max_sample=30):
    """
    Deep dive into ticket content to extract:
    - Specific real issues reported
    - Which app/platform has the issue
    - Solutions provided by CS team

    Args:
        tickets: List of tickets to analyze
        max_sample: Maximum number of tickets to deep dive (to avoid API limits)

    Returns:
        List of deep dive findings with issue, app, and solution
    """
    findings = []

    # Focus on solved tickets to see resolutions
    solved_tickets = [t for t in tickets if t.get("status") == "solved"]

    # Sample tickets if too many (prioritize recent and high priority)
    if len(solved_tickets) > max_sample:
        # Sort by priority and recency
        priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        solved_tickets = sorted(
            solved_tickets,
            key=lambda t: (
                priority_order.get(t.get("priority", "normal"), 2),
                t.get("created_at", "")
            ),
            reverse=True
        )[:max_sample]

    # Analyze each ticket
    for ticket in solved_tickets:
        subject = ticket.get("subject", "")
        description = ticket.get("description", "") or ""
        ticket_id = ticket.get("id")

        # Identify the app/platform
        app = "Unknown"
        subject_lower = subject.lower()
        desc_lower = description.lower()
        combined = f"{subject_lower} {desc_lower}"

        if "booking.com" in combined or "booking" in combined or "b.com" in combined:
            app = "Booking.com"
        elif "airbnb" in combined or "air bnb" in combined:
            app = "Airbnb"
        elif "vrbo" in combined or "abritel" in combined:
            app = "Vrbo/Abritel"
        elif "smilypay" in combined or "payment" in combined or "iban" in combined or "kyc" in combined:
            app = "SmilyPay"
        elif "website" in combined or "widget" in combined or "landing" in combined:
            app = "Website/Widget"
        elif "notification" in combined or "email" in combined:
            app = "Notifications"
        elif "pricing" in combined or "price" in combined or "tarif" in combined:
            app = "Pricing Engine"

        # Extract specific issue type
        issue_type = "General"
        if "sync" in combined or "synchronisation" in combined:
            issue_type = "Sync Issue"
        elif "connect" in combined or "connexion" in combined or "add" in combined and "listing" in combined:
            issue_type = "Connection/Onboarding"
        elif "block" in combined or "bloqué" in combined or "suspended" in combined:
            issue_type = "Listing Blocked"
        elif "calendar" in combined or "availability" in combined or "disponibilité" in combined:
            issue_type = "Calendar/Availability"
        elif "photo" in combined or "image" in combined:
            issue_type = "Photo Upload/Sync"
        elif "document" in combined and ("reject" in combined or "rejet" in combined):
            issue_type = "Document Rejection"
        elif "price" in combined or "tarif" in combined or "rate" in combined:
            issue_type = "Pricing Issue"
        elif "reservation" in combined or "booking" in subject_lower and "new" not in combined:
            issue_type = "Reservation Issue"

        # Fetch comments to find CS solution (limit API calls)
        solution = None
        comments = fetch_ticket_comments(ticket_id)

        # Analyze CS team responses (look for agent responses, not customer)
        for comment in comments:
            if not comment.get("public", True):
                continue  # Skip internal notes

            author_id = comment.get("author_id")
            body = comment.get("body", "").lower()

            # Simple heuristic: if it's not the requester and has helpful keywords
            if len(body) > 50:  # Meaningful response
                # Look for solution indicators
                if any(keyword in body for keyword in [
                    "resolved", "fixed", "corrigé", "résolu",
                    "should work", "try", "please check",
                    "updated", "mis à jour", "modified",
                    "reconnect", "reconnecter", "refresh",
                    "contact", "reach out", "escalate"
                ]):
                    # Extract key solution phrases
                    if "reconnect" in body or "reconnecter" in body:
                        solution = "Reconnect listing/account"
                    elif "refresh" in body or "rafraîchir" in body:
                        solution = "Refresh connection/sync"
                    elif "updated" in body or "mis à jour" in body or "modified" in body:
                        solution = "Updated configuration/settings"
                    elif "contact" in body and ("booking" in body or "airbnb" in body or "vrbo" in body):
                        solution = "Escalate to channel partner"
                    elif "document" in body and ("upload" in body or "provide" in body):
                        solution = "Re-upload required documents"
                    elif "mapping" in body or "match" in body:
                        solution = "Fix listing mapping"
                    elif "duplicate" in body:
                        solution = "Remove duplicate listing"
                    elif "permission" in body or "access" in body:
                        solution = "Fix account permissions"
                    elif "api" in body or "technical" in body:
                        solution = "Technical fix/API issue"
                    else:
                        solution = "CS team manual intervention"
                    break

        # Create finding
        finding = {
            "app": app,
            "issue_type": issue_type,
            "subject": subject[:100],  # Truncate long subjects
            "solution": solution or "Unknown/No clear resolution",
            "ticket_id": ticket_id,
            "priority": ticket.get("priority", "normal"),
            "customer": ticket.get("organization_name", "Unknown")
        }

        findings.append(finding)

    return findings


def analyze_deep_dive_patterns(findings):
    """
    Analyze deep dive findings to extract patterns and actionable recommendations.

    Returns structured insights by app and issue type with common solutions.
    """
    if not findings:
        return []

    # Group by app and issue type
    patterns = defaultdict(lambda: {
        "count": 0,
        "issues": defaultdict(int),
        "solutions": defaultdict(int),
        "examples": []
    })

    for finding in findings:
        app = finding["app"]
        issue_type = finding["issue_type"]
        solution = finding["solution"]

        patterns[app]["count"] += 1
        patterns[app]["issues"][issue_type] += 1
        patterns[app]["solutions"][solution] += 1

        # Keep a few examples
        if len(patterns[app]["examples"]) < 3:
            patterns[app]["examples"].append({
                "subject": finding["subject"],
                "issue": issue_type,
                "solution": solution,
                "customer": finding["customer"]
            })

    # Generate structured recommendations
    recommendations = []

    for app, data in sorted(patterns.items(), key=lambda x: -x[1]["count"]):
        if data["count"] < 2:  # Skip low-volume apps
            continue

        # Find top issue and solution
        top_issue = max(data["issues"].items(), key=lambda x: x[1])
        top_solution = max(data["solutions"].items(), key=lambda x: x[1])

        # Calculate solution effectiveness
        solution_diversity = len(data["solutions"])
        manual_intervention_count = data["solutions"].get("CS team manual intervention", 0)

        # Determine opportunity
        opportunity = None
        if top_issue[0] == "Connection/Onboarding":
            opportunity = "Improve onboarding UX with step-by-step wizard and validation"
        elif top_issue[0] == "Sync Issue":
            opportunity = "Implement auto-retry logic and better error messages"
        elif top_issue[0] == "Document Rejection":
            opportunity = "Add document validation before upload, show examples"
        elif top_issue[0] == "Listing Blocked":
            opportunity = "Proactive warnings before blocking, clearer unblock process"
        elif top_issue[0] == "Calendar/Availability":
            opportunity = "Automated sync health checks, one-click refresh button"
        elif top_solution[0] == "Reconnect listing/account":
            opportunity = "Add self-service reconnect button in UI"
        elif solution_diversity > 5:
            opportunity = "Issues too varied - may need better categorization or multiple fixes"
        elif manual_intervention_count > data["count"] * 0.5:
            opportunity = "High manual intervention - investigate automation opportunities"

        rec = {
            "app": app,
            "total_issues": data["count"],
            "top_issue": top_issue[0],
            "top_issue_count": top_issue[1],
            "top_solution": top_solution[0],
            "top_solution_count": top_solution[1],
            "solution_types": len(data["solutions"]),
            "manual_intervention_rate": f"{manual_intervention_count / data['count'] * 100:.0f}%",
            "opportunity": opportunity,
            "examples": data["examples"]
        }

        recommendations.append(rec)

    return recommendations
