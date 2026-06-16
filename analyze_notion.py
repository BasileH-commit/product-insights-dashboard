#!/usr/bin/env python3
"""
Weekly Product Insights Analyzer - Direct Zendesk + Modjo API Version

Data Sources:
- Zendesk: Direct API (real customer names, full ticket data)
- Modjo: Direct API (with Google Sheets fallback)

Output:
- Notion databases with full details
- Slack notification

Usage: python3 analyze_notion.py
"""

import os
import re
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from dotenv import load_dotenv

import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

# Zendesk Config
ZENDESK_SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN")
ZENDESK_EMAIL = os.getenv("ZENDESK_EMAIL")
ZENDESK_TOKEN = os.getenv("ZENDESK_TOKEN")
ZENDESK_AUTH = HTTPBasicAuth(f"{ZENDESK_EMAIL}/token", ZENDESK_TOKEN)
ZENDESK_BASE_URL = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/api/v2"

# Modjo API Config
MODJO_API_KEY = os.getenv("MODJO_API_KEY")
MODJO_BASE_URL = "https://api.modjo.ai/v1"
MODJO_HEADERS = {
    "X-API-KEY": MODJO_API_KEY,
    "Content-Type": "application/json"
}

# Legacy Google Sheets (kept for fallback)
MODJO_SHEET_ID = os.getenv("MODJO_SHEET_ID")
GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")

# Notion Config
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DEEP_ANALYSIS_DB = os.getenv("NOTION_DEEP_ANALYSIS_DB")
NOTION_METRICS_DB = os.getenv("NOTION_METRICS_DB")
NOTION_ATRISK_DB = os.getenv("NOTION_ATRISK_DB")
NOTION_PROSPECTS_DB = os.getenv("NOTION_PROSPECTS_DB")
NOTION_DASHBOARD_DB = os.getenv("NOTION_DASHBOARD_DB")
NOTION_CATEGORIES_DB = os.getenv("NOTION_CATEGORIES_DB")
NOTION_ISSUES_DB = os.getenv("NOTION_ISSUES_DB")
NOTION_QUESTIONS_DB = os.getenv("NOTION_QUESTIONS_DB")
NOTION_WEEKLY_INSIGHTS_DB = os.getenv("NOTION_WEEKLY_INSIGHTS_DB")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Use REPORTS webhook for weekly insights (goes to #product-insights)
# SLACK_WEBHOOK_URL is for #zendesk-updates (KB bot only)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL_REPORTS", "")

# Granular categories with sub-categories
CATEGORIES_DETAILED = {
    # Booking.com split
    "Booking.com – New Connections": ["new listing", "connect booking", "connexion booking", "add listing", "nouvelle annonce", "ajout booking", "new rental", "connect new", "nouvelle connexion", "capi", "add new"],
    "Booking.com – Sync Issues": ["booking sync", "booking calendar", "booking availability", "booking.com sync", "synchronisation booking", "booking error", "booking blocked"],
    "Booking.com – General": ["booking.com", "booking", "b.com", "bcom"],

    # SmilyPay / Payments
    "SmilyPay / Payment Gateway": ["smilypay", "payment", "paiement", "rib", "3ds", "virement", "versement", "transfer", "document rejected", "production", "iban", "kyc"],

    # Rental Management
    "Rental Management": ["rental", "logement", "hébergement", "restore", "restaurer", "duplicate", "dupliquer", "config", "configuration", "property"],

    # Website
    "Website / Experience": ["website", "site web", "widget", "landing", "page web", "experience site"],

    # Notifications
    "Notifications / Automations": ["notification", "email", "template", "automation", "automatisation", "alert"],

    # Airbnb split
    "Airbnb – Sync Issues": ["airbnb sync", "airbnb calendar", "airbnb photo", "airbnb listing sync", "synchronisation airbnb"],
    "Airbnb – General": ["airbnb", "air bnb"],

    # Cancellation Protection
    "Cancellation Protection": ["cancellation protection", "protection annulation", "annulation", "cancel protection"],

    # VRBO
    "Vrbo / Abritel": ["vrbo", "abritel", "homeaway"],

    # Pricing
    "Pricing": ["pricing", "prix", "price", "tarif", "rate", "markup", "mark-up"],

    # Account
    "Account / Billing": ["account", "billing", "invoice", "facture", "subscription", "abonnement"],

    # New specific categories to reduce "Other"
    "API / Integration": ["api", "integration", "webhook", "endpoint", "connect", "channel manager", "pms"],
    "Mobile App": ["mobile", "app", "ios", "android", "phone", "smartphone"],
    "Reports / Analytics": ["report", "export", "analytics", "statistics", "stat", "rapports", "statistiques"],
    "Feature Request": ["feature", "suggestion", "request", "add", "new feature", "would like", "demande"],
    "Bug / Technical Issue": ["bug", "error", "crash", "broken", "not working", "doesn't work", "ne fonctionne pas"],
    "Training / How-to": ["how to", "how do i", "comment", "tutorial", "guide", "help", "aide"],
}

# Subcategory patterns for detailed breakdown
SUBCATEGORY_PATTERNS = {
    "Booking.com – General": {
        "Reservation management": ["reservation", "booking", "réservation", "guest", "check-in", "check-out"],
        "Content updates": ["description", "content", "text", "contenu", "update info", "modify"],
        "Listing settings": ["setting", "config", "paramètre", "option", "preference"],
        "Account access": ["login", "access", "password", "account", "compte", "connexion"],
        "Photos / Media": ["photo", "image", "picture", "media", "gallery"],
        "Rates / Pricing": ["rate", "price", "prix", "tarif", "cost"],
        "Availability issues": ["availability", "disponibilité", "calendar", "blocked"],
        "General questions": [],  # catch-all
    },
    "Booking.com – New Connections": {
        "Connection errors": ["error", "fail", "can't connect", "unable", "impossible"],
        "Authentication": ["auth", "login", "credentials", "password", "token"],
        "Missing listings": ["listing not found", "can't find", "missing", "manquant"],
        "First-time setup": ["first", "initial", "setup", "onboard", "new"],
        "General connection": [],  # catch-all
    },
    "Booking.com – Sync Issues": {
        "Calendar sync": ["calendar", "calendrier", "availability", "disponibilité"],
        "Photo sync": ["photo", "image", "picture"],
        "Price sync": ["price", "prix", "tarif", "rate"],
        "Content sync": ["description", "content", "text", "info"],
        "Reservation sync": ["reservation", "booking", "réservation"],
        "General sync": [],  # catch-all
    },
    "SmilyPay / Payment Gateway": {
        "Document rejection": ["document", "rejected", "rejet", "rib", "iban", "identity", "kyc"],
        "Payment delays": ["delay", "retard", "waiting", "pending", "en attente"],
        "Transfer issues": ["transfer", "virement", "versement", "payout"],
        "3DS / Security": ["3ds", "secure", "security", "verification"],
        "Account activation": ["activate", "activation", "production", "live"],
        "General payment": [],  # catch-all
    },
    "Rental Management": {
        "Restore/Reactivate": ["restore", "restaurer", "reactivate", "réactiver", "closed"],
        "Duplicate rental": ["duplicate", "dupliquer", "copy", "copie"],
        "Configuration": ["config", "setting", "paramètre", "setup"],
        "Delete rental": ["delete", "remove", "supprimer"],
        "General management": [],  # catch-all
    },
    "Website / Experience": {
        "Widget issues": ["widget", "embed", "integration"],
        "Content display": ["content", "display", "show", "affichage", "contenu"],
        "Landing page": ["landing", "page", "site"],
        "Design / Theme": ["design", "theme", "style", "color", "look"],
        "General website": [],  # catch-all
    },
    "Notifications / Automations": {
        "Email not sent": ["not sent", "didn't receive", "non reçu", "missing email"],
        "Template customization": ["template", "customize", "modèle", "personnaliser"],
        "Automation rules": ["automation", "rule", "trigger", "condition"],
        "Email content": ["content", "text", "message", "contenu"],
        "General notifications": [],  # catch-all
    },
    "Airbnb – General": {
        "Reservation issues": ["reservation", "booking", "réservation", "guest"],
        "Listing updates": ["update", "modify", "change", "mettre à jour"],
        "Account access": ["login", "access", "password", "account"],
        "General questions": [],  # catch-all
    },
    "Airbnb – Sync Issues": {
        "Calendar sync": ["calendar", "calendrier", "availability"],
        "Photo sync": ["photo", "image", "picture"],
        "Price sync": ["price", "prix", "tarif"],
        "General sync": [],  # catch-all
    },
    "Cancellation Protection": {
        "Activation": ["activate", "setup", "enable", "activer"],
        "Claim process": ["claim", "demande", "request", "reimbursement"],
        "Coverage questions": ["cover", "coverage", "couverture", "protected"],
        "General protection": [],  # catch-all
    },
    "Vrbo / Abritel": {
        "Connection": ["connect", "connexion", "link"],
        "Sync issues": ["sync", "synchronisation", "calendar", "photo"],
        "General Vrbo": [],  # catch-all
    },
    "Pricing": {
        "Dynamic pricing": ["dynamic", "auto", "automatic", "automatique"],
        "Markup issues": ["markup", "mark-up", "margin", "commission"],
        "Price incorrect": ["wrong", "incorrect", "error", "mauvais prix"],
        "General pricing": [],  # catch-all
    },
    "Account / Billing": {
        "Invoice request": ["invoice", "facture", "receipt"],
        "Subscription": ["subscription", "abonnement", "plan", "upgrade"],
        "Account settings": ["account", "setting", "profile", "compte"],
        "General billing": [],  # catch-all
    },
}

# Fallback simple categories (for backwards compat)
CATEGORIES = {
    "Booking.com Sync": ["booking.com", "booking", "b.com", "booking-sync", "bcom", "booking sync"],
    "Payment/RIB": ["payment", "rib", "paiement", "smilypay", "transfer", "virement", "versement", "3ds"],
    "Pricing": ["pricing", "prix", "price", "tarif", "rate", "markup", "mark-up"],
    "SmilyPay Onboarding": ["onboarding", "document rejected", "iban", "kyc", "identity", "production"],
    "Airbnb Sync": ["airbnb", "airbnb sync", "airbnb listing"],
    "VRBO/Abritel": ["vrbo", "homeaway", "abritel"],
    "Notifications": ["notification", "email", "template"],
    "Website": ["website", "site web", "widget", "landing page", "page web"],
    "Account/Billing": ["account", "billing", "invoice", "facture", "subscription", "abonnement"],
}

# Common questions patterns for better extraction
QUESTION_PATTERNS = [
    (r"connect.*listing|nouvelle connexion|add.*listing|ajout.*annonce", "How do I connect a new listing to {channel}?"),
    (r"sync.*error|not syncing|synchronisation|blocked|bloqué", "Why is my {channel} listing blocked / not syncing?"),
    (r"document.*rejected|document.*refus", "My SmilyPay documents were rejected — what do I need to provide?"),
    (r"cancellation protection|protection annulation|activ.*protection", "How do I set up / activate Cancellation Protection?"),
    (r"photo.*sync|calendar.*sync|not pushing", "Why are my {channel} photos / calendar not syncing?"),
    (r"notification.*setup|configure.*notification|notif", "How do I configure notifications for check-in/checkout?"),
    (r"price.*wrong|prix.*incorrect|tarif", "Why are my prices wrong on {channel}?"),
    (r"reactivate|restore|restaurer|réactiver|closed rental", "How do I reactivate / restore a closed rental?"),
    (r"website.*content|site.*contenu|display", "How do I update my website content / display settings?"),
]

# Question keywords (to identify questions)
QUESTION_KEYWORDS = ["how", "what", "why", "when", "where", "can i", "is it possible", "comment", "pourquoi", "est-ce que", "puis-je", "?"]


# ============== ZENDESK API ==============

def fetch_zendesk_organizations():
    """Fetch all organizations and build ID->Name lookup."""
    print("      Fetching organizations...")
    orgs = {}
    url = f"{ZENDESK_BASE_URL}/organizations.json?per_page=100"

    while url:
        response = requests.get(url, auth=ZENDESK_AUTH)
        if response.status_code != 200:
            print(f"      ⚠️ Org fetch error: {response.status_code}")
            break

        data = response.json()
        for org in data.get("organizations", []):
            orgs[org["id"]] = org["name"]

        url = data.get("next_page")

    print(f"      → {len(orgs)} organizations loaded")
    return orgs


def fetch_zendesk_tickets(days=7, start_date=None, end_date=None):
    """Fetch recent tickets from Zendesk API.

    Args:
        days: Number of days back to fetch (if start_date/end_date not provided)
        start_date: Optional start date string in YYYY-MM-DD format
        end_date: Optional end date string in YYYY-MM-DD format
    """
    if start_date and end_date:
        print(f"      Fetching tickets from {start_date} to {end_date}...")
        query = f"type:ticket created>={start_date} created<={end_date}"
    else:
        print(f"      Fetching tickets from last {days} days...")
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        query = f"type:ticket created>{cutoff}"

    tickets = []

    # Search for recent tickets
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
        response = requests.get(url, params=params, auth=ZENDESK_AUTH)

        if response.status_code != 200:
            print(f"      ⚠️ Ticket fetch error: {response.status_code}")
            break

        data = response.json()
        results = data.get("results", [])

        if not results:
            break

        tickets.extend(results)

        if len(results) < 100:
            break

        page += 1
        if page > 10:  # Safety limit
            break

    print(f"      → {len(tickets)} tickets fetched")
    return tickets


def fetch_single_organization(org_id):
    """Fetch a single organization by ID (for orgs missing from bulk fetch)."""
    url = f"{ZENDESK_BASE_URL}/organizations/{org_id}.json"
    try:
        response = requests.get(url, auth=ZENDESK_AUTH)
        if response.status_code == 200:
            return response.json().get("organization", {}).get("name")
    except Exception:
        pass
    return None


def enrich_tickets_with_org_names(tickets, org_lookup):
    """Add organization names to tickets, fetching missing orgs on-demand."""
    missing_fetched = 0
    for ticket in tickets:
        org_id = ticket.get("organization_id")
        if org_id:
            if org_id in org_lookup:
                ticket["organization_name"] = org_lookup[org_id]
            else:
                # Fetch missing org on-demand and cache it
                org_name = fetch_single_organization(org_id)
                if org_name:
                    org_lookup[org_id] = org_name
                    ticket["organization_name"] = org_name
                    missing_fetched += 1
                else:
                    ticket["organization_name"] = None
        else:
            ticket["organization_name"] = None

    if missing_fetched > 0:
        print(f"      → Fetched {missing_fetched} missing organization(s) on-demand")
    return tickets


# ============== MODJO API ==============

def parse_date(date_str):
    """Parse date from various formats."""
    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except:
            pass
    return None


def fetch_modjo_calls_api(days=7, start_date=None, end_date=None):
    """Fetch Modjo calls from API using POST /v1/calls/exports.

    Args:
        days: Number of days back to fetch (if start_date/end_date not provided)
        start_date: Optional start date string in YYYY-MM-DD format
        end_date: Optional end date string in YYYY-MM-DD format
    """
    if start_date and end_date:
        print(f"      Fetching calls from {start_date} to {end_date}...")
        cutoff = datetime.strptime(start_date, "%Y-%m-%d")
        now = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        print(f"      Fetching calls from last {days} days...")
        cutoff = datetime.now() - timedelta(days=days)
        now = datetime.now()

    calls = []
    page = 1
    per_page = 50  # Max allowed by API

    while True:
        # Build request body per API spec
        request_body = {
            "pagination": {
                "page": page,
                "perPage": per_page
            },
            "filters": {
                "callStartDateRange": {
                    "start": cutoff.strftime("%Y-%m-%dT00:00:00.000Z"),
                    "end": now.strftime("%Y-%m-%dT23:59:59.999Z")
                }
            },
            "relations": {
                "summary": True,
                "contacts": True,
                "account": True,
                "users": True,
                "tags": True
            }
        }

        response = requests.post(
            f"{MODJO_BASE_URL}/calls/exports",
            headers=MODJO_HEADERS,
            json=request_body
        )

        if response.status_code not in [200, 201]:
            print(f"      Modjo API error: {response.status_code}")
            if response.status_code == 401:
                print("      Check your MODJO_API_KEY in .env")
            try:
                print(f"      Response: {response.text[:200]}")
            except:
                pass
            break

        data = response.json()

        # Get results from 'values' array
        results = data.get("values", [])

        if not results:
            break

        # Transform API response to match expected format
        for call in results:
            # Get account name from relations
            account_name = "Unknown"
            account_data = call.get("relations", {}).get("account")
            if account_data:
                # API returns account as single object, not list
                if isinstance(account_data, dict):
                    account_name = account_data.get("name", "Unknown")
                elif isinstance(account_data, list) and len(account_data) > 0:
                    account_name = account_data[0].get("name", "Unknown")

            # Get contacts as fallback for account
            if account_name == "Unknown":
                contacts = call.get("relations", {}).get("contacts", [])
                if contacts and len(contacts) > 0:
                    account_name = contacts[0].get("name", "Unknown")

            # Get summary content
            summary_data = call.get("relations", {}).get("summary", {})
            summary = summary_data.get("content", "") if summary_data else ""

            # Get tags
            tags_list = call.get("relations", {}).get("tags", [])
            tags = ", ".join([t.get("name", "") for t in tags_list]) if tags_list else ""

            # Get agent from users relation (more reliable than parsing title)
            users_list = call.get("relations", {}).get("users", [])
            agent_name = users_list[0].get("name", "") if users_list else ""

            transformed = {
                "Title": call.get("title") or "Modjo Call",
                "Account": account_name,
                "Summary": summary,
                "Tags": tags,
                "Urgency": "",  # Not directly in API, would need AI scoring
                "Impact score": "",
                "Sentiment": "",
                "Transcript URL": f"https://app.modjo.ai/calls/{call.get('callId', '')}",
                "Timestamp": call.get("startDate") or "",
                "call_id": call.get("callId"),
                "duration": call.get("duration", 0),
                "agent": agent_name,  # Agent from API
            }
            calls.append(transformed)

        # Check pagination
        pagination = data.get("pagination", {})
        next_page = pagination.get("nextPage")
        last_page = pagination.get("lastPage", 1)

        if not next_page or page >= last_page:
            break

        page += 1
        if page > 50:  # Safety limit
            break

    print(f"      -> {len(calls)} calls fetched from API")
    return calls


# Legacy Google Sheets functions (fallback)
def get_sheets_client():
    """Connect to Google Sheets."""
    creds = Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_PATH,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)


def fetch_modjo_calls_sheets(gc, days=7):
    """Fetch Modjo calls from Google Sheets (fallback)."""
    cutoff = datetime.now() - timedelta(days=days)

    modjo_sheet = gc.open_by_key(MODJO_SHEET_ID).sheet1
    modjo_all = modjo_sheet.get_all_records()
    modjo = [r for r in modjo_all if parse_date(r.get("Timestamp")) and parse_date(r.get("Timestamp")) >= cutoff]

    return modjo


def fetch_modjo_calls(days=7, use_api=True, start_date=None, end_date=None):
    """Fetch Modjo calls - tries API first, falls back to Sheets."""
    if use_api and MODJO_API_KEY:
        try:
            calls = fetch_modjo_calls_api(days, start_date=start_date, end_date=end_date)
            if calls:
                return calls
            print("      -> No calls from API, trying Google Sheets fallback...")
        except Exception as e:
            print(f"      -> API error: {type(e).__name__}: {e}, trying fallback...")

    # Fallback to Google Sheets
    gc = get_sheets_client()
    return fetch_modjo_calls_sheets(gc, days)


# ============== MODJO ANALYSIS ==============

# Known agents by team
MODJO_AGENTS = {
    # Account Management Team
    "Bruno Ribier": {"email": "bruno@bookingsync.com", "team": "Account Management"},
    "Clement Guillemoto": {"email": "clement.guillemoto@bookingsync.com", "team": "Account Management"},
    "Ella Fraase Storm": {"email": "ella@bookingsync.com", "team": "Account Management"},
    "Jordan Pereira": {"email": "jordan.pereira@smily.com", "team": "Account Management"},
    "Raphael Pereira": {"email": "raphael.pereira@bookingsync.com", "team": "Account Management"},
    # Onboarding Team
    "Malika Ravate": {"email": "malika.ravate@bookingsync.com", "team": "Onboarding"},
    "Marie Caille": {"email": "marie.caille@bookingsync.com", "team": "Onboarding"},
    # Sales Team
    "Eleni Laiou": {"email": "eleni.laiou@bookingsync.com", "team": "Sales"},
    "Flo Stenström": {"email": "flo@bookingsync.com", "team": "Sales"},
    "Olivier Le Floch": {"email": "olivier@bookingsync.com", "team": "Sales"},
    "Valentin Hug": {"email": "valentin.hug@smily.com", "team": "Sales"},
}

# Agent name variations/aliases for matching
AGENT_ALIASES = {
    "bruno": "Bruno Ribier",
    "clement": "Clement Guillemoto",
    "ella": "Ella Fraase Storm",
    "jordan": "Jordan Pereira",
    "raphael pereira": "Raphael Pereira",
    "raphael": "Raphael Pereira",
    "malika": "Malika Ravate",
    "marie": "Marie Caille",
    "eleni": "Eleni Laiou",
    "flo": "Flo Stenström",
    "olivier": "Olivier Le Floch",
    "valentin": "Valentin Hug",
}


def match_agent_name(raw_name):
    """Match a raw agent name to a known agent."""
    if not raw_name:
        return None

    raw_lower = raw_name.lower().strip()

    # Direct match
    for agent in MODJO_AGENTS:
        if agent.lower() == raw_lower:
            return agent

    # Partial match on aliases
    for alias, agent in AGENT_ALIASES.items():
        if alias in raw_lower:
            return agent

    # Check if any known agent first name is in the raw name
    for agent in MODJO_AGENTS:
        first_name = agent.split()[0].lower()
        last_name = agent.split()[-1].lower() if len(agent.split()) > 1 else ""
        # Match "FirstName LastName" pattern
        if first_name in raw_lower and last_name and last_name in raw_lower:
            return agent

    return None


# Modjo call type categories
MODJO_CALL_TYPES = {
    "Sales / Demo": ["demo", "découverte", "présentation", "tarif", "pricing", "devis", "abonnement", "offre", "commercial", "prospect", "nouveau client", "intéressé"],
    "Onboarding": ["onboarding", "mise en place", "configuration", "démarrage", "formation", "setup", "paramétrage", "premier pas", "prise en main"],
    "Support": ["problème", "bug", "erreur", "ne fonctionne pas", "bloqué", "issue", "incident", "aide", "support", "dépannage"],
    "Account Management": ["suivi", "point", "bilan", "satisfaction", "feedback", "renouvellement", "upgrade", "évolution"],
    "Churn Risk": ["résiliation", "annulation", "cancel", "quitter", "arrêter", "fin de contrat", "pas satisfait", "déçu", "concurrent"],
}

# Topics/themes for Modjo calls
MODJO_TOPICS = {
    "Channel Sync (Booking/Airbnb/Vrbo)": ["booking.com", "airbnb", "vrbo", "abritel", "channel", "ota", "sync", "synchronisation", "calendrier", "disponibilité"],
    "Payments / SmilyPay": ["paiement", "payment", "smilypay", "virement", "caution", "dépôt", "transaction", "rib", "iban"],
    "Pricing & Revenue": ["prix", "tarif", "pricing", "revenue", "yield", "markup", "commission", "marge"],
    "Website & Direct Booking": ["site web", "website", "réservation directe", "direct booking", "widget", "moteur de réservation"],
    "Automation & Notifications": ["automation", "automatisation", "notification", "email", "message", "template", "workflow"],
    "Security": ["sécurité", "piratage", "hack", "mot de passe", "accès", "phishing", "fraude"],
    "Integrations": ["intégration", "api", "connecteur", "zapier", "crm", "pms"],
    "Mobile App": ["application", "mobile", "app", "smartphone"],
    "Reporting & Analytics": ["rapport", "statistique", "analytics", "dashboard", "tableau de bord", "kpi"],
}

# Sales-specific patterns
SALES_AGENTS = ["Eleni Laiou", "Flo Stenström", "Olivier Le Floch", "Valentin Hug"]

# Competitor solutions to track
COMPETITORS = {
    "Guesty": ["guesty"],
    "Avantio": ["avantio", "aventio"],
    "GuestReady": ["guestready", "guest ready"],
    "Hostfully": ["hostfully"],
    "Hospitable": ["hospitable"],
    "Lodgify": ["lodgify", "logify"],
    "HostAway": ["hostaway", "host away"],
    "OwnerRez": ["ownerrez", "owner rez"],
    "Beds24": ["beds24", "beds 24"],
    "Smoobu": ["smoobu"],
    "Superhote": ["superhote", "super hote"],
    "Lodgix": ["lodgix"],
    "Escapia": ["escapia"],
    "Hostify": ["hostify"],
    "Uplisting": ["uplisting"],
    "Your.Rentals": ["your.rentals", "yourrentals"],
    "Tokeet": ["tokeet"],
    "Eviivo": ["eviivo"],
    "Kigo": ["kigo"],
    "Rentals United": ["rentals united"],
    "Libo": ["libo"],
    "Icnea": ["icnea"],
    "Guestify": ["guestify"],
    "Amenitiz": ["amenitiz"],
    "PriceLabs": ["pricelab", "pricelabs"],
    "Beyond Pricing": ["beyond pricing", "beyond"],
    "Wheelhouse": ["wheelhouse"],
}

# Objection patterns and how sales typically responds
OBJECTION_PATTERNS = [
    ("trop cher", "Price too high"),
    ("prix élevé", "Price too high"),
    ("tarif élevé", "Price too high"),
    ("budget", "Budget concern"),
    ("moins cher", "Cheaper alternative"),
    ("concurrent", "Competitor comparison"),
    ("hésit", "Hesitation"),
    ("réfléchir", "Needs to think"),
    ("pas sûr", "Not sure"),
    ("pas convaincu", "Not convinced"),
    ("complexe", "Complexity concern"),
    ("compliqué", "Complexity concern"),
    ("migration", "Migration concern"),
    ("temps", "Time concern"),
    ("équipe", "Team/resources concern"),
    ("formation", "Training concern"),
    ("support", "Support concern"),
    ("engagement", "Commitment concern"),
    ("contrat", "Contract concern"),
]

# Sales response patterns
SALES_RESPONSE_PATTERNS = [
    ("remise", "Offered discount"),
    ("réduction", "Offered discount"),
    ("-25%", "Offered discount"),
    ("-30%", "Offered discount"),
    ("-40%", "Offered discount"),
    ("-50%", "Offered discount"),
    ("offre spéciale", "Special offer"),
    ("accompagnement", "Highlighted support"),
    ("onboarding", "Highlighted onboarding"),
    ("migration", "Migration assistance"),
    ("démo", "Offered demo"),
    ("essai", "Offered trial"),
    ("test", "Offered trial"),
    ("différencie", "Differentiation"),
    ("avantage", "Highlighted advantage"),
    ("français", "French company advantage"),
    ("automatisation", "Automation benefits"),
]

# Lead "wants" indicators
LEAD_WANTS_INDICATORS = [
    ("cherche", "Looking for"),
    ("recherche", "Searching for"),
    ("besoin", "Needs"),
    ("veut", "Wants"),
    ("souhaite", "Wishes"),
    ("aimerait", "Would like"),
    ("intéressé par", "Interested in"),
    ("important pour", "Important for"),
    ("priorité", "Priority"),
    ("objectif", "Goal"),
]

# Sales pitch quality indicators (positive)
PITCH_POSITIVE = [
    "très intéressé", "convaincu", "enthousiaste", "impressionné", "parfait",
    "exactement ce que", "correspond", "répond à", "satisfait", "content",
    "prêt à", "signer", "commencer", "onboarder", "démarrer",
]

# Sales pitch friction indicators (negative)
PITCH_FRICTION = [
    "hésit", "pas sûr", "trop cher", "prix élevé", "concurrent", "moins cher",
    "pas convaincu", "réfléchir", "compliqué", "complexe", "peur",
    "inquiet", "doute", "réserve", "objection",
]


def extract_sales_insights(calls, insights):
    """Extract sales-specific insights from calls made by sales team."""
    sales_insights = {
        "calls": [],
        "lead_questions": [],
        "lead_complaints": [],
        "lead_wants": [],
        "pitch_scores": [],
        "competitors_mentioned": [],  # Track competitor mentions
        "objection_responses": [],    # Track objections and how sales responded
        "total_calls": 0,
    }

    for call in calls:
        agent = call.get("agent", "")
        matched_agent = match_agent_name(agent)

        # Only process calls from sales team
        if not matched_agent or matched_agent not in SALES_AGENTS:
            continue

        summary = call.get("Summary", "")
        account = call.get("Account", "Unknown")
        title = call.get("Title", "")
        summary_lower = summary.lower()

        sales_insights["total_calls"] += 1
        sales_insights["calls"].append(call)

        # Extract lead questions (lines with ?)
        for line in summary.split("\n"):
            line_clean = line.strip().strip("-").strip("*").strip()
            if "?" in line_clean and len(line_clean) > 20:
                # Filter out internal/agent questions, keep lead questions
                if not any(x in line_clean.lower() for x in ["smily", "raphaël", "valentin", "eleni", "olivier"]):
                    sales_insights["lead_questions"].append({
                        "question": line_clean[:150],
                        "account": account,
                        "agent": matched_agent,
                    })

        # Extract what leads want
        for indicator, indicator_type in LEAD_WANTS_INDICATORS:
            if indicator in summary_lower:
                verbatim = extract_verbatim_context(summary, indicator, before=20, after=150)
                if verbatim:
                    sales_insights["lead_wants"].append({
                        "verbatim": verbatim,
                        "type": indicator_type,
                        "account": account,
                        "agent": matched_agent,
                    })
                    break

        # Extract lead complaints/frictions during sales
        for indicator, indicator_type in PAIN_INDICATORS:
            if indicator in summary_lower:
                verbatim = extract_verbatim_context(summary, indicator, before=30, after=120)
                if verbatim:
                    sales_insights["lead_complaints"].append({
                        "verbatim": verbatim,
                        "type": indicator_type,
                        "account": account,
                        "agent": matched_agent,
                    })
                    break

        # Calculate pitch score for this call
        positive_count = sum(1 for p in PITCH_POSITIVE if p in summary_lower)
        negative_count = sum(1 for p in PITCH_FRICTION if p in summary_lower)

        # Score: 0-100 based on positive vs negative indicators
        if positive_count + negative_count > 0:
            score = (positive_count / (positive_count + negative_count)) * 100
        else:
            score = 50  # Neutral

        # Adjust based on call outcome hints
        if any(x in summary_lower for x in ["signer", "commencer", "onboard", "démarrer le"]):
            score = min(100, score + 20)
        if any(x in summary_lower for x in ["concurrent", "pas intéressé", "refus"]):
            score = max(0, score - 20)

        sales_insights["pitch_scores"].append({
            "score": score,
            "agent": matched_agent,
            "account": account,
            "positive_signals": positive_count,
            "friction_signals": negative_count,
        })

        # Track competitor mentions
        for competitor, keywords in COMPETITORS.items():
            if any(kw in summary_lower for kw in keywords):
                # Extract context around the competitor mention
                verbatim = None
                for kw in keywords:
                    if kw in summary_lower:
                        verbatim = extract_verbatim_context(summary, kw, before=30, after=150)
                        break
                sales_insights["competitors_mentioned"].append({
                    "competitor": competitor,
                    "account": account,
                    "agent": matched_agent,
                    "verbatim": verbatim or f"Mentioned {competitor}",
                    "call_title": title,
                })

        # Track objections and how sales responded
        for objection_pattern, objection_type in OBJECTION_PATTERNS:
            if objection_pattern in summary_lower:
                # Look for sales response in the same call
                response_found = None
                for response_pattern, response_type in SALES_RESPONSE_PATTERNS:
                    if response_pattern in summary_lower:
                        response_found = response_type
                        break

                objection_verbatim = extract_verbatim_context(summary, objection_pattern, before=20, after=100)
                sales_insights["objection_responses"].append({
                    "objection_type": objection_type,
                    "objection_verbatim": objection_verbatim or objection_pattern,
                    "response": response_found or "No clear response recorded",
                    "account": account,
                    "agent": matched_agent,
                })
                break  # One objection per call to avoid duplicates

    return sales_insights


def extract_topic_details(calls, topic_name, topic_keywords):
    """Extract detailed questions, complaints, and issues for a specific topic."""
    details = {
        "questions": [],
        "complaints": [],
        "issues": [],
    }

    for call in calls:
        summary = call.get("Summary", "")
        summary_lower = summary.lower()
        account = call.get("Account", "Unknown")

        # Check if this call mentions the topic
        if not any(kw in summary_lower for kw in topic_keywords):
            continue

        # Extract questions related to this topic
        for line in summary.split("\n"):
            line_clean = line.strip().strip("-").strip("*").strip()
            line_clean = re.sub(r'\*\*', '', line_clean)
            if "?" in line_clean and len(line_clean) > 15:
                # Check if question is related to topic
                if any(kw in line_clean.lower() for kw in topic_keywords):
                    details["questions"].append({
                        "text": line_clean[:120],
                        "account": account,
                    })

        # Extract complaints/issues related to this topic
        for indicator, indicator_type in PAIN_INDICATORS[:8]:  # Use top indicators
            if indicator in summary_lower:
                # Find context around the indicator
                idx = summary_lower.find(indicator)
                # Check if topic keywords are nearby
                context_start = max(0, idx - 100)
                context_end = min(len(summary), idx + 150)
                context = summary[context_start:context_end]

                if any(kw in context.lower() for kw in topic_keywords):
                    verbatim = extract_verbatim_context(summary, indicator, before=40, after=100)
                    if verbatim:
                        details["complaints"].append({
                            "text": verbatim[:150],
                            "type": indicator_type,
                            "account": account,
                        })
                        break

    # Deduplicate and limit
    seen_q = set()
    details["questions"] = [q for q in details["questions"] if not (q["text"] in seen_q or seen_q.add(q["text"]))][:5]
    seen_c = set()
    details["complaints"] = [c for c in details["complaints"] if not (c["text"] in seen_c or seen_c.add(c["text"]))][:5]

    return details


# Pain point indicators with context extraction patterns
PAIN_INDICATORS = [
    ("problème", "Issue"),
    ("difficile", "Difficulty"),
    ("compliqué", "Complexity"),
    ("frustré", "Frustration"),
    ("déçu", "Disappointment"),
    ("pas clair", "Confusion"),
    ("confusion", "Confusion"),
    ("bug", "Bug"),
    ("erreur", "Error"),
    ("bloqué", "Blocked"),
    ("impossible", "Limitation"),
    ("lent", "Performance"),
    ("manque", "Missing feature"),
    ("ne marche pas", "Not working"),
    ("ne fonctionne pas", "Not working"),
]

# Feature request indicators
FEATURE_INDICATORS = [
    ("serait bien de", "Would be nice"),
    ("serait bien d'", "Would be nice"),
    ("il faudrait", "Should have"),
    ("ce serait top", "Would be great"),
    ("on aimerait", "Would like"),
    ("besoin de", "Need"),
    ("vous pourriez", "Could you"),
    ("est-ce possible", "Is it possible"),
    ("fonctionnalité", "Feature"),
    ("amélioration", "Improvement"),
    ("suggestion", "Suggestion"),
    ("ajouter", "Add"),
    ("manque", "Missing"),
]


def categorize_modjo_call(summary_text):
    """Categorize a Modjo call based on its summary."""
    text_lower = summary_text.lower()

    # Determine call type
    call_type = "Other"
    for ctype, keywords in MODJO_CALL_TYPES.items():
        if any(kw in text_lower for kw in keywords):
            call_type = ctype
            break

    # Determine topics
    topics = []
    for topic, keywords in MODJO_TOPICS.items():
        if any(kw in text_lower for kw in keywords):
            topics.append(topic)

    if not topics:
        topics = ["General"]

    return call_type, topics


def extract_verbatim_context(summary, indicator, before=80, after=150):
    """Extract a clean verbatim quote around an indicator."""
    summary_lower = summary.lower()
    idx = summary_lower.find(indicator.lower())
    if idx == -1:
        return None

    # Find sentence boundaries
    start = max(0, idx - before)
    end = min(len(summary), idx + after)

    # Try to start at beginning of sentence
    for i in range(idx, start, -1):
        if summary[i] in '.!?\n':
            start = i + 1
            break

    # Try to end at end of sentence
    for i in range(idx + len(indicator), min(end + 50, len(summary))):
        if summary[i] in '.!?\n':
            end = i + 1
            break

    context = summary[start:end].strip()
    # Clean up markdown artifacts
    context = re.sub(r'^[\-\*#]+\s*', '', context)
    context = re.sub(r'\*\*', '', context)
    context = context.strip()

    return context if len(context) > 20 else None


def summarize_pain_point(context, indicator_type):
    """Create a short summary of a pain point."""
    context_lower = context.lower()

    # Try to extract the core issue
    if "booking" in context_lower or "airbnb" in context_lower:
        return f"{indicator_type} with channel sync/OTA"
    elif "paiement" in context_lower or "payment" in context_lower:
        return f"{indicator_type} with payments"
    elif "sync" in context_lower:
        return f"{indicator_type} with synchronization"
    elif "prix" in context_lower or "tarif" in context_lower:
        return f"{indicator_type} with pricing"
    elif "site" in context_lower or "website" in context_lower:
        return f"{indicator_type} with website"
    else:
        # Extract first few meaningful words
        words = context.split()[:8]
        return f"{indicator_type}: {' '.join(words)}..."


def extract_modjo_insights(calls):
    """Extract insights from Modjo calls: pain points, questions, feature requests."""
    insights = {
        "pain_points": [],  # List of individual pain points with details
        "feature_requests": [],  # List of individual feature requests
        "questions": defaultdict(lambda: {"count": 0, "accounts": set()}),
        "topics": defaultdict(lambda: {"calls": set(), "count": 0}),  # Track unique calls per topic
        "call_types": Counter(),
        "accounts": Counter(),
        "agents": defaultdict(lambda: {"calls": 0, "accounts": set(), "duration": 0, "call_types": Counter()}),
    }

    for call in calls:
        summary = call.get("Summary", "")
        account = call.get("Account", "Unknown")
        title = call.get("Title", "")
        call_id = call.get("call_id", title)
        duration = call.get("duration", 0)
        agent = call.get("agent", "")

        # Extract agent name from title if not set (format: "Agent Name and Customer Name")
        raw_agent = agent
        if not raw_agent and " and " in title:
            raw_agent = title.split(" and ")[0].strip()

        # Match to known agent
        matched_agent = match_agent_name(raw_agent)
        agent = matched_agent if matched_agent else raw_agent if raw_agent else "Unknown"

        # Get call type and topics
        call_type, topics = categorize_modjo_call(summary)
        insights["call_types"][call_type] += 1

        # Track topics by unique calls
        for topic in topics:
            insights["topics"][topic]["calls"].add(call_id)
            insights["topics"][topic]["count"] += 1

        # Count by account
        insights["accounts"][account] += 1

        # Track agent performance (only for known agents)
        if matched_agent:
            insights["agents"][agent]["calls"] += 1
            insights["agents"][agent]["accounts"].add(account)
            insights["agents"][agent]["duration"] += duration
            insights["agents"][agent]["call_types"][call_type] += 1
            agent_info = MODJO_AGENTS.get(agent, {})
            insights["agents"][agent]["email"] = agent_info.get("email", "")
            insights["agents"][agent]["team"] = agent_info.get("team", "Unknown")

        # Extract pain points from summary with better verbatim
        summary_lower = summary.lower()
        for indicator, indicator_type in PAIN_INDICATORS:
            if indicator in summary_lower:
                verbatim = extract_verbatim_context(summary, indicator)
                if verbatim:
                    pain_summary = summarize_pain_point(verbatim, indicator_type)
                    topic = topics[0] if topics else "General"

                    insights["pain_points"].append({
                        "verbatim": verbatim,
                        "summary": pain_summary,
                        "type": indicator_type,
                        "topic": topic,
                        "account": account,
                        "agent": agent,
                        "call_title": title,
                        "call_id": call_id,
                    })
                break  # Only capture first pain point per call

        # Extract feature requests with better verbatim
        for indicator, indicator_type in FEATURE_INDICATORS:
            if indicator in summary_lower:
                verbatim = extract_verbatim_context(summary, indicator, before=40, after=180)
                if verbatim:
                    topic = topics[0] if topics else "General"

                    insights["feature_requests"].append({
                        "verbatim": verbatim,
                        "type": indicator_type,
                        "topic": topic,
                        "account": account,
                        "agent": agent,
                        "call_title": title,
                        "call_id": call_id,
                    })
                break  # Only capture first feature request per call

        # Extract questions (lines ending with ?)
        for line in summary.split("\n"):
            if "?" in line and len(line) > 20:
                clean_q = line.strip().strip("-").strip("*").strip()
                clean_q = re.sub(r'\*\*', '', clean_q)
                if len(clean_q) > 15:
                    insights["questions"][clean_q[:100]]["count"] += 1
                    insights["questions"][clean_q[:100]]["accounts"].add(account)

    return insights


def analyze_modjo_trends(calls_this_week, calls_last_week, calls_30d):
    """Analyze Modjo call trends WoW and MoM."""
    # This week analysis
    insights_tw = extract_modjo_insights(calls_this_week)

    # Last week analysis
    insights_lw = extract_modjo_insights(calls_last_week)

    # 30 day analysis (for MoM average)
    insights_30d = extract_modjo_insights(calls_30d)

    # Convert topics to sorted list with call counts
    topics_tw_sorted = sorted(
        [(topic, len(data["calls"]), data["count"]) for topic, data in insights_tw["topics"].items()],
        key=lambda x: -x[1]
    )
    topics_lw_dict = {topic: len(data["calls"]) for topic, data in insights_lw["topics"].items()}

    # Sort agents by call count
    agents_sorted = sorted(
        [(agent, data) for agent, data in insights_tw["agents"].items()],
        key=lambda x: -x[1]["calls"]
    )
    agents_lw_dict = {agent: data["calls"] for agent, data in insights_lw["agents"].items()}

    # Extract sales-specific insights
    sales_insights = extract_sales_insights(calls_this_week, insights_tw)

    # Extract detailed info for top 3 topics
    topic_details = {}
    for topic, num_calls, mentions in topics_tw_sorted[:3]:
        keywords = MODJO_TOPICS.get(topic, [topic.lower()])
        topic_details[topic] = extract_topic_details(calls_this_week, topic, keywords)

    trends = {
        "total_calls": {
            "this_week": len(calls_this_week),
            "last_week": len(calls_last_week),
            "month_avg": len(calls_30d) / 4.3,
        },
        "call_types": {
            "this_week": insights_tw["call_types"],
            "last_week": insights_lw["call_types"],
        },
        "topics": {
            "this_week": topics_tw_sorted,
            "last_week": topics_lw_dict,
        },
        "topic_details": topic_details,  # Detailed Q&A for top 3 topics
        "top_accounts": insights_tw["accounts"].most_common(10),
        "pain_points": insights_tw["pain_points"],
        "feature_requests": insights_tw["feature_requests"],
        "questions": sorted(insights_tw["questions"].items(), key=lambda x: -x[1]["count"])[:15],
        "agents": {
            "this_week": agents_sorted,
            "last_week": agents_lw_dict,
        },
        "sales": sales_insights,  # Sales-specific insights
    }

    return trends, insights_tw


def notion_create_modjo_summary_page(date_str, calls_tw, calls_lw, trends, insights, date_range=None):
    """Create a dedicated Modjo insights page in Notion."""
    total_tw = len(calls_tw)
    total_lw = len(calls_lw)
    change = calculate_evolution(total_tw, total_lw)
    trend_emoji = get_trend_emoji(change)

    # Format title with date range if provided
    if date_range:
        page_title = f"Modjo Call Insights — {date_range}"
    else:
        page_title = f"Modjo Call Insights — {date_str}"

    children = []

    # Header
    children.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {"content": page_title}}]}
    })

    # Overview callout
    children.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": f"{total_tw} calls this week {trend_emoji} {change:+.0f}% vs last week ({total_lw})"}}],
            "icon": {"emoji": "📞"}
        }
    })

    # Call Types section
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📊 Call Types"}}]}
    })

    call_types_tw = trends["call_types"]["this_week"]
    call_types_lw = trends["call_types"]["last_week"]

    for call_type, count in call_types_tw.most_common(6):
        pct = count / total_tw * 100 if total_tw > 0 else 0
        lw_count = call_types_lw.get(call_type, 0)
        wow = calculate_evolution(count, lw_count)
        wow_str = f"{get_trend_emoji(wow)} {wow:+.0f}%" if lw_count > 0 else "🆕"

        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{call_type}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — {count} calls ({pct:.0f}%) | {wow_str}"}}
            ]}
        })

    # Topics section - now shows number of calls with details for top 3
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🏷️ Top Topics Discussed"}}]}
    })

    topics_tw = trends["topics"]["this_week"]  # List of (topic, num_calls, mentions)
    topics_lw = trends["topics"]["last_week"]  # Dict of topic -> num_calls
    topic_details = trends.get("topic_details", {})

    for i, (topic, num_calls, mentions) in enumerate(topics_tw[:8]):
        pct = num_calls / total_tw * 100 if total_tw > 0 else 0
        lw_count = topics_lw.get(topic, 0)
        wow = calculate_evolution(num_calls, lw_count)
        wow_str = f"{get_trend_emoji(wow)} {wow:+.0f}%" if lw_count > 0 else "🆕"

        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{topic}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — mentioned in {num_calls} calls ({pct:.0f}%) | {wow_str}"}}
            ]}
        })

        # Add detailed questions/complaints for top 3 topics
        if i < 3 and topic in topic_details:
            details = topic_details[topic]

            # Add questions
            if details["questions"]:
                children.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": f"❓ Questions about {topic}"}, "annotations": {"italic": True}}],
                        "children": [
                            {
                                "object": "block",
                                "type": "bulleted_list_item",
                                "bulleted_list_item": {"rich_text": [
                                    {"type": "text", "text": {"content": f'"{q["text"]}"'}, "annotations": {"italic": True}},
                                    {"type": "text", "text": {"content": f' — {q["account"]}'}}
                                ]}
                            } for q in details["questions"][:4]
                        ]
                    }
                })

            # Add complaints/issues
            if details["complaints"]:
                children.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": f"⚠️ Issues with {topic}"}, "annotations": {"italic": True}}],
                        "children": [
                            {
                                "object": "block",
                                "type": "bulleted_list_item",
                                "bulleted_list_item": {"rich_text": [
                                    {"type": "text", "text": {"content": f'[{c["type"]}] "{c["text"]}"'}, "annotations": {"italic": True}},
                                    {"type": "text", "text": {"content": f' — {c["account"]}'}}
                                ]}
                            } for c in details["complaints"][:4]
                        ]
                    }
                })

    # Agent Performance section
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "👤 Agent Performance"}}]}
    })

    agents_tw = trends["agents"]["this_week"]
    agents_lw = trends["agents"]["last_week"]

    # Group agents by team
    agents_by_team = defaultdict(list)
    for agent, data in agents_tw:
        team = data.get("team", "Unknown")
        agents_by_team[team].append((agent, data))

    # Display by team
    for team in ["Sales", "Account Management", "Onboarding"]:
        if team not in agents_by_team:
            continue

        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": f"📌 {team}"}, "annotations": {"bold": True, "underline": True}}]}
        })

        for agent, data in agents_by_team[team]:
            calls = data["calls"]
            accounts = len(data["accounts"])
            total_mins = data["duration"] // 60
            avg_mins = total_mins // calls if calls > 0 else 0

            # Get top call type for this agent
            top_type = data["call_types"].most_common(1)
            top_type_str = top_type[0][0] if top_type else "N/A"

            lw_calls = agents_lw.get(agent, 0)
            wow = calculate_evolution(calls, lw_calls)
            wow_str = f"{get_trend_emoji(wow)} {wow:+.0f}%" if lw_calls > 0 else "🆕"

            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [
                    {"type": "text", "text": {"content": f"{agent}"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f" — {calls} calls, {accounts} accounts, ~{avg_mins}min avg | {top_type_str} | {wow_str}"}}
                ]}
            })

    # ============ SALES FOCUS SECTION ============
    sales = trends.get("sales", {})
    if sales.get("total_calls", 0) > 0:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🎯 Sales Focus"}}]}
        })

        # Sales overview with pitch score
        pitch_scores = sales.get("pitch_scores", [])
        if pitch_scores:
            avg_score = sum(p["score"] for p in pitch_scores) / len(pitch_scores)
            score_emoji = "🟢" if avg_score >= 70 else "🟡" if avg_score >= 50 else "🔴"
            positive_total = sum(p["positive_signals"] for p in pitch_scores)
            friction_total = sum(p["friction_signals"] for p in pitch_scores)

            children.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": f"Sales Pitch Score: {avg_score:.0f}/100 {score_emoji}\n{sales['total_calls']} sales calls | {positive_total} positive signals | {friction_total} friction signals"}}],
                    "icon": {"emoji": "📊"},
                    "color": "green_background" if avg_score >= 70 else "yellow_background" if avg_score >= 50 else "red_background"
                }
            })

        # Top Questions from Leads
        if sales.get("lead_questions"):
            children.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": "❓ Top Questions from Leads"}}]}
            })

            for q in sales["lead_questions"][:6]:
                children.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [
                        {"type": "text", "text": {"content": f'"{q["question"]}"'}, "annotations": {"italic": True}},
                        {"type": "text", "text": {"content": f' — {q["account"]}'}}
                    ]}
                })

        # What Leads Want from Smily
        if sales.get("lead_wants"):
            children.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🎁 What Leads Want from Smily"}}]}
            })

            for w in sales["lead_wants"][:6]:
                children.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"[{w['type']}] "}, "annotations": {"bold": True}},
                            {"type": "text", "text": {"content": f'"{w["verbatim"][:180]}"\n\n'}, "annotations": {"italic": True}},
                            {"type": "text", "text": {"content": f"— {w['account']}"}}
                        ],
                        "icon": {"emoji": "💬"},
                        "color": "purple_background"
                    }
                })

        # Lead Complaints/Frictions
        if sales.get("lead_complaints"):
            children.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": "⚡ Lead Objections & Frictions"}}]}
            })

            for c in sales["lead_complaints"][:5]:
                children.append({
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"[{c['type']}] "}, "annotations": {"bold": True}},
                            {"type": "text", "text": {"content": f'"{c["verbatim"][:150]}"\n\n'}, "annotations": {"italic": True}},
                            {"type": "text", "text": {"content": f"— {c['account']}"}}
                        ],
                        "icon": {"emoji": "⚠️"},
                        "color": "orange_background"
                    }
                })

        # Competitor Landscape
        if sales.get("competitors_mentioned"):
            children.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🏁 Competitor Landscape"}}]}
            })

            # Group by competitor and count
            competitor_counts = defaultdict(list)
            for cm in sales["competitors_mentioned"]:
                competitor_counts[cm["competitor"]].append(cm)

            # Sort by frequency
            competitor_sorted = sorted(competitor_counts.items(), key=lambda x: -len(x[1]))

            # Summary callout
            total_mentions = len(sales["competitors_mentioned"])
            top_competitors = [f"{c} ({len(leads)})" for c, leads in competitor_sorted[:5]]
            children.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": f"{total_mentions} leads mentioned competitors: {', '.join(top_competitors)}"}}],
                    "icon": {"emoji": "🎯"},
                    "color": "blue_background"
                }
            })

            # Show details per competitor (top 5)
            for competitor, mentions in competitor_sorted[:5]:
                unique_accounts = set(m["account"] for m in mentions)
                account_list = ", ".join(list(unique_accounts)[:3])
                more_accounts = f" +{len(unique_accounts)-3} more" if len(unique_accounts) > 3 else ""

                children.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"{competitor}"}, "annotations": {"bold": True}},
                            {"type": "text", "text": {"content": f" — {len(mentions)} leads ({account_list}{more_accounts})"}}
                        ],
                        "children": [
                            {
                                "object": "block",
                                "type": "callout",
                                "callout": {
                                    "rich_text": [
                                        {"type": "text", "text": {"content": f'"{m["verbatim"][:200]}"\n\n'}, "annotations": {"italic": True}},
                                        {"type": "text", "text": {"content": f"— {m['account']} ({m['agent']})"}}
                                    ],
                                    "icon": {"emoji": "💬"},
                                    "color": "gray_background"
                                }
                            } for m in mentions[:3]
                        ]
                    }
                })

        # Objections & Sales Responses
        if sales.get("objection_responses"):
            children.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🛡️ Objections & Sales Responses"}}]}
            })

            # Group by objection type
            objection_groups = defaultdict(list)
            for obj in sales["objection_responses"]:
                objection_groups[obj["objection_type"]].append(obj)

            # Sort by frequency
            objection_sorted = sorted(objection_groups.items(), key=lambda x: -len(x[1]))

            for objection_type, objections in objection_sorted[:6]:
                # Count responses
                response_counts = Counter(obj["response"] for obj in objections)
                top_response = response_counts.most_common(1)[0] if response_counts else ("N/A", 0)

                children.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"❌ {objection_type}"}, "annotations": {"bold": True}},
                            {"type": "text", "text": {"content": f" — {len(objections)} occurrences"}}
                        ],
                        "children": [
                            {
                                "object": "block",
                                "type": "callout",
                                "callout": {
                                    "rich_text": [{"type": "text", "text": {"content": f"Top response: {top_response[0]} ({top_response[1]}x)"}}],
                                    "icon": {"emoji": "✅"},
                                    "color": "green_background"
                                }
                            }
                        ] + [
                            {
                                "object": "block",
                                "type": "bulleted_list_item",
                                "bulleted_list_item": {"rich_text": [
                                    {"type": "text", "text": {"content": f'"{obj["objection_verbatim"][:100]}"'}, "annotations": {"italic": True}},
                                    {"type": "text", "text": {"content": f' → {obj["response"]} — {obj["account"]}'}}
                                ]}
                            } for obj in objections[:3]
                        ]
                    }
                })

    # Top Accounts section
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🏢 Most Active Accounts"}}]}
    })

    for account, count in trends["top_accounts"][:8]:
        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{account}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — {count} calls"}}
            ]}
        })

    # Pain Points section - improved with proper verbatim
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "😤 Pain Points & Complaints"}}]}
    })

    # Group pain points by topic
    pain_by_topic = defaultdict(list)
    for pp in trends["pain_points"]:
        pain_by_topic[pp["topic"]].append(pp)

    # Sort by count and display
    pain_sorted = sorted(pain_by_topic.items(), key=lambda x: -len(x[1]))

    for topic, pain_list in pain_sorted[:5]:
        unique_accounts = set(pp["account"] for pp in pain_list)
        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{topic}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — {len(pain_list)} issues from {len(unique_accounts)} accounts"}}
            ]}
        })

        # Add detailed examples (up to 2 per topic)
        for pp in pain_list[:2]:
            summary_text = pp["summary"]
            verbatim = pp["verbatim"][:200] if len(pp["verbatim"]) > 200 else pp["verbatim"]
            account = pp["account"]

            children.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"{summary_text}\n\n"}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f'"{verbatim}"\n\n'}, "annotations": {"italic": True}},
                        {"type": "text", "text": {"content": f"— {account}"}}
                    ],
                    "icon": {"emoji": "🔴"},
                    "color": "red_background"
                }
            })

    # Feature Requests section - improved with proper verbatim
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "💡 Feature Requests & Suggestions"}}]}
    })

    # Group feature requests by topic
    feat_by_topic = defaultdict(list)
    for fr in trends["feature_requests"]:
        feat_by_topic[fr["topic"]].append(fr)

    feat_sorted = sorted(feat_by_topic.items(), key=lambda x: -len(x[1]))

    for topic, feat_list in feat_sorted[:5]:
        unique_accounts = set(fr["account"] for fr in feat_list)
        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{topic}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — {len(feat_list)} requests from {len(unique_accounts)} accounts"}}
            ]}
        })

        # Add detailed examples (up to 2 per topic)
        for fr in feat_list[:2]:
            verbatim = fr["verbatim"][:250] if len(fr["verbatim"]) > 250 else fr["verbatim"]
            account = fr["account"]
            req_type = fr["type"]

            children.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"[{req_type}] "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f'"{verbatim}"\n\n'}, "annotations": {"italic": True}},
                        {"type": "text", "text": {"content": f"— {account}"}}
                    ],
                    "icon": {"emoji": "💭"},
                    "color": "blue_background"
                }
            })

    # Top Questions section
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "❓ Top Questions Asked"}}]}
    })

    for i, (question, data) in enumerate(trends["questions"][:10], 1):
        children.append({
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"\"{question}\""}, "annotations": {"italic": True}},
                {"type": "text", "text": {"content": f" ({data['count']}x)"}}
            ]}
        })

    # Create the page
    page_data = {
        "parent": {"page_id": os.getenv("NOTION_PAGE_ID")},
        "properties": {
            "title": {"title": [{"text": {"content": page_title}}]}
        },
        "children": children[:100]  # Notion limit
    }

    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        json=page_data
    )

    if response.status_code == 200:
        return response.json().get("url")
    else:
        print(f"      Notion page error: {response.status_code} - {response.text[:200]}")
        return None


def generate_modjo_summary_report(calls_tw, calls_lw, trends):
    """Generate a text summary report for Modjo insights."""
    total_tw = len(calls_tw)
    total_lw = len(calls_lw)
    change = calculate_evolution(total_tw, total_lw)
    trend = "📈" if change > 0 else "📉" if change < 0 else "➡️"

    report = []
    report.append("=" * 70)
    report.append("📞 MODJO WEEKLY CALL INSIGHTS")
    report.append("=" * 70)
    report.append("")
    report.append(f"📊 Total Calls: {total_tw} ({trend} {change:+.1f}% vs last week's {total_lw})")
    report.append("")

    # Call Types
    report.append("📋 CALL TYPES")
    report.append("-" * 70)
    for call_type, count in trends["call_types"]["this_week"].most_common(6):
        pct = count / total_tw * 100 if total_tw > 0 else 0
        lw_count = trends["call_types"]["last_week"].get(call_type, 0)
        wow = calculate_evolution(count, lw_count)
        report.append(f"  • {call_type}: {count} ({pct:.0f}%) {get_trend_emoji(wow)}{wow:+.0f}%")
    report.append("")

    # Topics - now shows call counts
    report.append("🏷️ TOP TOPICS (by # of calls)")
    report.append("-" * 70)
    for topic, num_calls, mentions in trends["topics"]["this_week"][:8]:
        pct = num_calls / total_tw * 100 if total_tw > 0 else 0
        report.append(f"  • {topic}: {num_calls} calls ({pct:.0f}%)")
    report.append("")

    # Agent Performance by Team
    report.append("👤 AGENT PERFORMANCE")
    report.append("-" * 70)

    # Group by team
    agents_by_team = defaultdict(list)
    for agent, data in trends["agents"]["this_week"]:
        team = data.get("team", "Unknown")
        agents_by_team[team].append((agent, data))

    for team in ["Sales", "Account Management", "Onboarding"]:
        if team not in agents_by_team:
            continue
        report.append(f"  [{team}]")
        for agent, data in agents_by_team[team]:
            calls = data["calls"]
            accounts = len(data["accounts"])
            avg_mins = (data["duration"] // 60) // calls if calls > 0 else 0
            lw_calls = trends["agents"]["last_week"].get(agent, 0)
            wow = calculate_evolution(calls, lw_calls)
            report.append(f"    • {agent}: {calls} calls, {accounts} accounts, ~{avg_mins}min avg {get_trend_emoji(wow)}{wow:+.0f}%")
    report.append("")

    # Top Accounts
    report.append("🏢 MOST ACTIVE ACCOUNTS")
    report.append("-" * 70)
    for account, count in trends["top_accounts"][:8]:
        report.append(f"  • {account}: {count} calls")
    report.append("")

    # Pain Points - improved grouping
    report.append("😤 PAIN POINTS")
    report.append("-" * 70)
    pain_by_topic = defaultdict(list)
    for pp in trends["pain_points"]:
        pain_by_topic[pp["topic"]].append(pp)
    for topic, pains in sorted(pain_by_topic.items(), key=lambda x: -len(x[1]))[:5]:
        accounts = set(p["account"] for p in pains)
        report.append(f"  • {topic}: {len(pains)} issues ({len(accounts)} accounts)")
        if pains:
            report.append(f"    → \"{pains[0]['summary']}\"")
    report.append("")

    # Feature Requests - improved grouping
    report.append("💡 FEATURE REQUESTS")
    report.append("-" * 70)
    feat_by_topic = defaultdict(list)
    for fr in trends["feature_requests"]:
        feat_by_topic[fr["topic"]].append(fr)
    for topic, feats in sorted(feat_by_topic.items(), key=lambda x: -len(x[1]))[:5]:
        accounts = set(f["account"] for f in feats)
        report.append(f"  • {topic}: {len(feats)} requests ({len(accounts)} accounts)")
        if feats:
            verbatim = feats[0]['verbatim'][:80]
            report.append(f"    → \"{verbatim}...\"")
    report.append("")

    report.append("=" * 70)

    return "\n".join(report)


def run_modjo_analysis(week_start=None, week_end=None):
    """Run the Modjo analysis and create Notion report.

    Args:
        week_start: Start date for the week (YYYY-MM-DD)
        week_end: End date for the week (YYYY-MM-DD)
    """
    print("\n" + "=" * 60)
    print("📞 MODJO CALL ANALYSIS")
    print("=" * 60)

    if week_start and week_end:
        today = week_end
        # Calculate week before
        week_before_start = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        week_before_end = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        week_before_start = None
        week_before_end = None

    # Fetch this week's calls
    print("\n[1/4] Fetching Modjo calls (this week)...")
    if week_start and week_end:
        calls_tw = fetch_modjo_calls(use_api=True, start_date=week_start, end_date=week_end)
    else:
        calls_tw = fetch_modjo_calls(days=7, use_api=True)
    print(f"      -> {len(calls_tw)} calls this week")

    # Fetch last week's calls (for WoW)
    print("[2/4] Fetching Modjo calls (last week)...")
    if week_before_start and week_before_end:
        calls_lw = fetch_modjo_calls(use_api=True, start_date=week_before_start, end_date=week_before_end)
    else:
        calls_14d = fetch_modjo_calls(days=14, use_api=True)
        tw_ids = {c.get("call_id") for c in calls_tw}
        calls_lw = [c for c in calls_14d if c.get("call_id") not in tw_ids]
    print(f"      -> {len(calls_lw)} calls last week")

    # Fetch 30 days (for MoM)
    print("[3/4] Fetching Modjo calls (last 30 days)...")
    calls_30d = fetch_modjo_calls(days=30, use_api=True)
    print(f"      -> {len(calls_30d)} calls last 30 days")

    # Analyze trends
    print("[4/4] Analyzing trends and generating report...")
    trends, insights = analyze_modjo_trends(calls_tw, calls_lw, calls_30d)

    # Print summary report
    report = generate_modjo_summary_report(calls_tw, calls_lw, trends)
    print("\n" + report)

    # Create Notion page
    print("\nCreating Modjo Notion page...")
    date_range_str = f"{week_start} to {week_end}" if week_start and week_end else None
    url = notion_create_modjo_summary_page(today, calls_tw, calls_lw, trends, insights, date_range=date_range_str)

    if url:
        print(f"      -> Modjo insights page created: {url}")

        # Update Recent Reports section to show this at the top
        report_title = f"Modjo Call Insights — {date_range_str}" if date_range_str else f"Modjo Call Insights — {today}"
        notion_update_recent_reports_section(
            url,
            report_title,
            "Modjo",
            date_str=today
        )

        # Send Slack notification
        print("      -> Sending Modjo summary to Slack...")
        date_range_str = f"{week_start} to {week_end}" if week_start and week_end else None
        if send_slack_modjo_summary(trends, url, date_range=date_range_str):
            print("      -> Modjo Slack summary sent")
        else:
            print("      -> Modjo Slack summary failed")
    else:
        print("      -> Failed to create Notion page")

    # Return URL and data for weekly insights
    return url, trends, insights, calls_tw, calls_lw


# ============== ANALYSIS ==============

def categorize(text):
    """Categorize text by keywords."""
    text_lower = text.lower()
    matches = []
    for category, keywords in CATEGORIES.items():
        if any(kw in text_lower for kw in keywords):
            matches.append(category)
    return matches if matches else ["Other"]


def categorize_detailed(text):
    """Categorize text with detailed sub-categories."""
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
        "API / Integration",
        "Mobile App",
        "Reports / Analytics",
        "Feature Request",
        "Bug / Technical Issue",
        "Training / How-to",
        "Booking.com – General",
        "Airbnb – General",
    ]

    for category in ordered_categories:
        keywords = CATEGORIES_DETAILED.get(category, [])
        if any(kw in text_lower for kw in keywords):
            return category

    return "Other"


def extract_subcategory(ticket, parent_category):
    """Extract subcategory for a ticket based on its parent category."""
    if parent_category not in SUBCATEGORY_PATTERNS:
        return "General"

    subject = ticket.get("subject", "").lower()
    description = (ticket.get("description") or "")[:200].lower()
    combined = f"{subject} {description}"

    subcategories = SUBCATEGORY_PATTERNS[parent_category]

    # Check each subcategory pattern
    for subcat, keywords in subcategories.items():
        if not keywords:  # This is the catch-all
            continue
        if any(kw in combined for kw in keywords):
            return subcat

    # Return the catch-all (last item)
    catch_all = list(subcategories.keys())[-1]
    return catch_all


def get_category_breakdown_with_subcategories(tickets_tw, tickets_lw, top_n=7):
    """Get category counts with subcategories for each."""
    categories_tw = Counter()
    categories_lw = Counter()
    subcategories_tw = defaultdict(lambda: defaultdict(lambda: {"count": 0, "tickets": []}))
    subcategories_lw = defaultdict(lambda: Counter())

    # Count tickets and collect examples
    for ticket in tickets_tw:
        # Use categorize_detailed to get the category
        subject = ticket.get("subject", "")
        desc = ticket.get("description", "")[:200] if ticket.get("description") else ""
        cat = categorize_detailed(f"{subject} {desc}")
        categories_tw[cat] += 1

        # Extract subcategory
        subcat = extract_subcategory(ticket, cat)
        subcategories_tw[cat][subcat]["count"] += 1
        # Store ticket for examples (limit to 3 per subcategory)
        if len(subcategories_tw[cat][subcat]["tickets"]) < 3:
            subcategories_tw[cat][subcat]["tickets"].append(ticket)

    for ticket in tickets_lw:
        # Use categorize_detailed to get the category
        subject = ticket.get("subject", "")
        desc = ticket.get("description", "")[:200] if ticket.get("description") else ""
        cat = categorize_detailed(f"{subject} {desc}")
        categories_lw[cat] += 1

        subcat = extract_subcategory(ticket, cat)
        subcategories_lw[cat][subcat] += 1

    # Build result with top categories
    result = []
    total_tickets = sum(categories_tw.values())

    for cat in sorted(categories_tw.keys(), key=lambda x: -categories_tw[x])[:top_n]:
        tw = categories_tw[cat]
        lw = categories_lw.get(cat, 0)
        pct = (tw / total_tickets * 100) if total_tickets > 0 else 0

        if lw > 0:
            wow_pct = ((tw - lw) / lw) * 100
            wow_str = f"{wow_pct:+.0f}%"
        elif tw > 0:
            wow_str = "🆕 New"
        else:
            wow_str = "—"

        # Get top subcategories
        subcats = []
        total_in_cat = sum(s["count"] for s in subcategories_tw[cat].values())

        for subcat in sorted(subcategories_tw[cat].keys(),
                            key=lambda x: -subcategories_tw[cat][x]["count"])[:3]:
            subcat_data = subcategories_tw[cat][subcat]
            subcat_count = subcat_data["count"]
            subcat_pct = (subcat_count / total_in_cat * 100) if total_in_cat > 0 else 0

            # Get example issues
            examples = [t.get("subject", "")[:50] for t in subcat_data["tickets"][:2]]

            subcats.append({
                "name": subcat,
                "count": subcat_count,
                "percentage": subcat_pct,
                "examples": examples
            })

        result.append({
            "category": cat,
            "count": tw,
            "last_period": lw,
            "percentage": pct,
            "wow": wow_str,
            "subcategories": subcats
        })

    return result


def get_customer_volumes(tickets):
    """Get ticket counts per customer."""
    customer_counts = Counter()

    for ticket in tickets:
        org_name = ticket.get("organization_name")
        if org_name:
            customer_counts[org_name] += 1

    return customer_counts.most_common(10)


def extract_readable_questions(tickets):
    """Extract and normalize questions into readable format."""
    question_counts = Counter()
    question_customers = defaultdict(set)

    for ticket in tickets:
        subject = ticket.get("subject", "").lower()
        org_name = ticket.get("organization_name")

        # Try to match against patterns
        matched = False
        for pattern, template in QUESTION_PATTERNS:
            if re.search(pattern, subject, re.IGNORECASE):
                # Detect channel from subject
                if "booking" in subject:
                    channel = "Booking.com"
                elif "airbnb" in subject:
                    channel = "Airbnb"
                elif "vrbo" in subject or "abritel" in subject:
                    channel = "Vrbo/Abritel"
                else:
                    channel = "the channel"

                question = template.format(channel=channel)
                question_counts[question] += 1
                if org_name:
                    question_customers[question].add(org_name)
                matched = True
                break

        # If no pattern matched but it's a question, use cleaned subject
        if not matched and is_question(subject):
            # Clean and normalize
            q = re.sub(r'#?\d+', '', subject).strip()
            q = re.sub(r'\[.*?\]', '', q).strip()
            q = q[:80]
            if len(q) > 15:
                question_counts[q] += 1
                if org_name:
                    question_customers[q].add(org_name)

    return question_counts, question_customers


def analyze_customer_churn_risk(tickets, tickets_lw, top_customers):
    """
    Analyze churn risk for top customers based on:
    - Ticket volume (40 points if >= 10 tickets)
    - Trend increase (35 points if > 50% growth)
    - High priority count (25 points if >= 3)
    - Solve rate (20 points if < 50%)

    Returns list of (customer, risk_data) tuples sorted by risk score.
    """
    # Build customer data for current week
    customer_data = defaultdict(lambda: {
        "tickets": [],
        "count": 0,
        "high_priority": 0,
        "solved": 0,
        "issues": Counter()
    })

    for ticket in tickets:
        org_name = ticket.get("organization_name")
        if not org_name or org_name == "Unknown":
            continue

        customer_data[org_name]["tickets"].append(ticket)
        customer_data[org_name]["count"] += 1

        if ticket.get("priority") in ["high", "urgent"]:
            customer_data[org_name]["high_priority"] += 1

        if ticket.get("status") in ["solved", "closed"]:
            customer_data[org_name]["solved"] += 1

        # Track issue subjects
        subject = ticket.get("subject", "")[:60]
        if subject:
            customer_data[org_name]["issues"][subject] += 1

    # Build last week data for trend analysis
    customer_lw = Counter()
    for ticket in tickets_lw:
        org_name = ticket.get("organization_name")
        if org_name and org_name != "Unknown":
            customer_lw[org_name] += 1

    # Calculate risk scores
    at_risk_customers = []

    for customer, top_count in top_customers[:15]:  # Analyze top 15 customers
        if customer not in customer_data:
            continue

        data = customer_data[customer]
        count = data["count"]
        high_priority = data["high_priority"]
        solved = data["solved"]
        solve_rate = (solved / count * 100) if count > 0 else 0

        # Calculate trend
        lw_count = customer_lw.get(customer, 0)
        if lw_count > 0:
            trend_pct = ((count - lw_count) / lw_count) * 100
        else:
            trend_pct = 0

        # Risk scoring
        risk_score = 0

        # Volume scoring
        if count >= 10:
            risk_score += 40
        elif count >= 5:
            risk_score += 25

        # Trend scoring (rapid increase)
        if trend_pct > 50:
            risk_score += 35
        elif trend_pct > 25:
            risk_score += 20

        # High priority scoring
        if high_priority >= 3:
            risk_score += 25
        elif high_priority >= 1:
            risk_score += 15

        # Solve rate scoring (low solve rate is bad)
        if solve_rate < 50:
            risk_score += 20
        elif solve_rate < 70:
            risk_score += 10

        # Determine risk level
        if risk_score >= 75:
            risk_level = "🔴 CRITICAL"
            risk_color = "red_background"
        elif risk_score >= 50:
            risk_level = "🟠 HIGH"
            risk_color = "orange_background"
        elif risk_score >= 30:
            risk_level = "🟡 MEDIUM"
            risk_color = "yellow_background"
        else:
            risk_level = "🟢 LOW"
            risk_color = "green_background"

        # Get top 5 issues for this customer
        top_issues = data["issues"].most_common(5)

        at_risk_customers.append((customer, {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_color": risk_color,
            "count": count,
            "lw_count": lw_count,
            "trend_pct": trend_pct,
            "high_priority": high_priority,
            "solve_rate": solve_rate,
            "top_issues": top_issues,
            "tickets": data["tickets"]
        }))

    # Sort by risk score descending, return only those with meaningful risk
    at_risk_customers.sort(key=lambda x: -x[1]["risk_score"])
    return [c for c in at_risk_customers if c[1]["risk_score"] >= 30]


def generate_actionable_insights(tickets, category_counts):
    """
    Generate actionable insights based on ticket patterns.
    Returns list of insight dictionaries with recommendations.
    """
    insights = []
    total = len(tickets)

    # Pattern 1: High volume in specific category
    if category_counts:
        top_cat, top_count = category_counts[0]
        top_pct = (top_count / total * 100) if total > 0 else 0

        if top_pct > 25:
            insights.append({
                "type": "high_volume",
                "icon": "⚠️",
                "title": f"{top_cat} dominates support volume",
                "description": f"{top_count} tickets ({top_pct:.0f}%) are related to {top_cat}",
                "recommendation": f"Consider creating dedicated FAQ or improving {top_cat} documentation to reduce ticket volume",
                "priority": "high"
            })

    # Pattern 2: Recurring issues (same subject appearing multiple times)
    subject_counts = Counter()
    for ticket in tickets:
        subject = ticket.get("subject", "")[:60]
        if subject:
            subject_counts[subject] += 1

    recurring = [(s, c) for s, c in subject_counts.most_common(10) if c >= 3]
    if recurring:
        top_recurring = recurring[0]
        insights.append({
            "type": "recurring",
            "icon": "🔁",
            "title": f"Recurring issue detected: {top_recurring[0][:40]}...",
            "description": f"This exact issue appeared {top_recurring[1]} times this week",
            "recommendation": "Investigate root cause and implement a permanent fix or create self-service solution",
            "priority": "high"
        })

    # Pattern 3: Multiple channels mentioned (integration issues)
    integration_keywords = ["sync", "connection", "calendar", "blocked", "error", "failed"]
    integration_tickets = [
        t for t in tickets
        if any(kw in t.get("subject", "").lower() for kw in integration_keywords)
    ]

    if len(integration_tickets) > total * 0.15:  # > 15% of tickets
        insights.append({
            "type": "integration",
            "icon": "🔌",
            "title": "High volume of integration/sync issues",
            "description": f"{len(integration_tickets)} tickets ({len(integration_tickets)/total*100:.0f}%) mention sync, connection, or calendar problems",
            "recommendation": "Review integration stability, error logging, and consider proactive monitoring",
            "priority": "medium"
        })

    # Pattern 4: Questions vs. bugs (understanding support nature)
    question_tickets = [t for t in tickets if is_question(t.get("subject", ""))]
    if len(question_tickets) > total * 0.3:  # > 30% are questions
        insights.append({
            "type": "questions",
            "icon": "❓",
            "title": "Many tickets are how-to questions",
            "description": f"{len(question_tickets)} tickets ({len(question_tickets)/total*100:.0f}%) are questions rather than bug reports",
            "recommendation": "Improve onboarding flow, create video tutorials, or enhance in-app help",
            "priority": "medium"
        })

    return insights


def create_executive_summary_blocks(tickets, tickets_lw, metrics, category_counts):
    """
    Create executive summary blocks for the top of the Notion report.
    Returns list of Notion block objects.
    """
    blocks = []
    total = len(tickets)
    total_lw = len(tickets_lw)
    change = ((total - total_lw) / total_lw * 100) if total_lw > 0 else 0
    trend = "📈" if change > 0 else "📉" if change < 0 else "➡️"

    solve_rate = metrics.get("solved_pct", 0)
    avg_solve_time = metrics.get("avg_solve_time", 0)

    # Determine overall health status (traffic light)
    health_score = 0
    if solve_rate >= 80:
        health_score += 40
    elif solve_rate >= 60:
        health_score += 20

    if change <= 0:  # Ticket volume not increasing
        health_score += 30
    elif change <= 10:
        health_score += 15

    if avg_solve_time <= 24:
        health_score += 30
    elif avg_solve_time <= 48:
        health_score += 15

    if health_score >= 70:
        status = "🟢 HEALTHY"
        status_color = "green_background"
    elif health_score >= 40:
        status = "🟡 NEEDS ATTENTION"
        status_color = "yellow_background"
    else:
        status = "🔴 CRITICAL"
        status_color = "red_background"

    # Header
    blocks.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📊 Executive Summary"}}]}
    })

    # Status callout
    blocks.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [
                {"type": "text", "text": {"content": f"Overall Status: {status}"}, "annotations": {"bold": True}}
            ],
            "icon": {"emoji": "🎯"},
            "color": status_color
        }
    })

    # Key metrics in a table-like format using columns
    metrics_text = f"""📬 Total Tickets: {total} ({trend} {change:+.0f}% WoW)
✅ Solve Rate: {solve_rate:.0f}%
⏱️ Avg Resolution: {avg_solve_time:.1f}h
"""

    if category_counts:
        top_3_cats = ", ".join([f"{cat} ({count})" for cat, count in category_counts[:3]])
        metrics_text += f"🔝 Top Categories: {top_3_cats}"

    blocks.append({
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": [{"type": "text", "text": {"content": metrics_text}}]}
    })

    # Divider
    blocks.append({
        "object": "block",
        "type": "divider",
        "divider": {}
    })

    return blocks


def generate_summary_report(tickets, tickets_lw, tickets_30d, category_counts, category_counts_lw,
                            top_issues, top_issues_lw, top_customers, top_customers_lw,
                            questions, agent_stats, agent_stats_lw):
    """Generate a formatted summary report with WoW/MoM evolution."""
    total = len(tickets)
    total_lw = len(tickets_lw)
    total_30d = len(tickets_30d)

    report = []
    report.append("=" * 70)
    report.append("📊 ZENDESK WEEKLY INSIGHTS SUMMARY")
    report.append("=" * 70)
    report.append("")

    # Overview
    change = ((total - total_lw) / total_lw * 100) if total_lw > 0 else 0
    trend = "📈" if change > 0 else "📉" if change < 0 else "➡️"
    report.append(f"📬 Total Tickets: {total} ({trend} {change:+.1f}% vs last week's {total_lw})")
    report.append("")

    # Convert lists to dicts for lookup
    cat_lw_dict = dict(category_counts_lw)
    cat_30d_dict = {cat: count / 4.3 for cat, count in dict(category_counts_lw).items()}  # Monthly avg

    # Top Categories with WoW/MoM
    report.append("🗂️ TOP CATEGORIES")
    report.append("-" * 70)
    report.append(f"  {'#':<3} {'Category':<35} {'Tickets':>7} {'%':>6} {'WoW':>8} {'MoM':>8}")
    report.append("  " + "-" * 67)

    for i, (cat, count) in enumerate(category_counts[:10], 1):
        pct = count / total * 100 if total > 0 else 0
        lw_count = cat_lw_dict.get(cat, 0)
        wow = calculate_evolution(count, lw_count)
        wow_emoji = get_trend_emoji(wow)
        # For MoM, use 30d average
        mom_avg = cat_30d_dict.get(cat, 0)
        mom = calculate_evolution(count, mom_avg) if mom_avg > 0 else 0
        mom_emoji = get_trend_emoji(mom)

        report.append(f"  {i:<3} {cat:<35} {count:>7} {pct:>5.1f}% {wow_emoji}{wow:>+5.0f}% {mom_emoji}{mom:>+5.0f}%")

    # Category insights
    booking_total = sum(c for cat, c in category_counts if "Booking" in cat)
    if booking_total > 0:
        report.append("")
        report.append(f"  💡 Booking.com accounts for ~{booking_total/total*100:.0f}% of all tickets")

    report.append("")

    # Top Issues with WoW
    issues_lw_dict = {issue: data["count"] for issue, data in top_issues_lw}
    report.append("🔥 TOP ISSUES")
    report.append("-" * 70)

    for issue, data in top_issues[:7]:
        customers = data["Customers"]
        lw_count = issues_lw_dict.get(issue, 0)
        if lw_count == 0:
            trend_str = "🆕 New"
        else:
            wow = calculate_evolution(data["count"], lw_count)
            trend_str = f"{get_trend_emoji(wow)} {wow:+.0f}%"

        report.append(f"  • {issue[:55]}")
        report.append(f"    → {data['count']} tickets, {customers} customers | {trend_str}")

    report.append("")

    # Top Customers with WoW
    customers_lw_dict = dict(top_customers_lw)
    report.append("🏢 TOP CUSTOMERS BY VOLUME")
    report.append("-" * 70)
    report.append(f"  {'Customer':<45} {'Tickets':>7} {'WoW':>10}")
    report.append("  " + "-" * 62)

    for customer, count in top_customers[:10]:
        lw_count = customers_lw_dict.get(customer, 0)
        if lw_count == 0:
            trend_str = "🆕 New"
        else:
            wow = calculate_evolution(count, lw_count)
            trend_str = f"{get_trend_emoji(wow)} {wow:+.0f}%"
        report.append(f"  {customer[:45]:<45} {count:>7} {trend_str:>10}")

    if top_customers and top_customers[0][1] > 5:
        report.append("")
        report.append(f"  ⚠️ {top_customers[0][0]} — worth a dedicated look")

    report.append("")

    # Agent Stats
    agents_lw_dict = dict(agent_stats_lw)
    report.append("👤 AGENT PERFORMANCE")
    report.append("-" * 70)
    report.append(f"  {'Agent':<30} {'Assigned':>8} {'Solved':>8} {'Rate':>6} {'WoW':>10}")
    report.append("  " + "-" * 62)

    for agent, stats in agent_stats[:10]:
        assigned = stats["assigned"]
        solved = stats["solved"]
        rate = (solved / assigned * 100) if assigned > 0 else 0

        lw_stats = agents_lw_dict.get(agent, {"assigned": 0})
        lw_assigned = lw_stats.get("assigned", 0) if isinstance(lw_stats, dict) else 0
        if lw_assigned == 0:
            trend_str = "🆕"
        else:
            wow = calculate_evolution(assigned, lw_assigned)
            trend_str = f"{get_trend_emoji(wow)} {wow:+.0f}%"

        report.append(f"  {agent[:30]:<30} {assigned:>8} {solved:>8} {rate:>5.0f}% {trend_str:>10}")

    report.append("")

    # Top Questions
    report.append("❓ TOP QUESTIONS RAISED")
    report.append("-" * 70)
    for i, (question, count) in enumerate(questions[:10], 1):
        report.append(f"  {i}. \"{question}\"")

    report.append("")
    report.append("=" * 70)

    return "\n".join(report)


def is_high_priority(ticket):
    """Check if ticket is high priority/urgency."""
    priority = str(ticket.get("priority", "")).lower()
    tags = ticket.get("tags", [])

    if priority in ["urgent", "high"]:
        return True
    if "urgent" in tags or "high" in tags:
        return True
    return False


def analyze_zendesk_tickets(tickets):
    """
    Analyze Zendesk tickets with full data.
    Returns themes grouped by category with occurrences and examples.
    """
    themes = defaultdict(lambda: defaultdict(lambda: {
        "count": 0,
        "accounts": set(),
        "examples": [],
        "high_priority_count": 0,
        "statuses": Counter(),
        "tags": Counter(),
    }))

    for ticket in tickets:
        subject = ticket.get("subject", "")
        description = ticket.get("description", "")[:500] if ticket.get("description") else ""
        tags = ticket.get("tags", [])

        text = f"{subject} {description} {' '.join(tags)}"
        categories = categorize(text)

        # Get organization name (real customer name)
        org_name = ticket.get("organization_name")
        account_display = org_name if org_name else f"Ticket #{ticket.get('id')}"

        # Use subject as theme (first 60 chars)
        theme = subject[:60] if subject else "No Subject"

        ticket_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/agent/tickets/{ticket.get('id')}"

        for cat in categories:
            themes[cat][theme]["count"] += 1
            themes[cat][theme]["accounts"].add(account_display)
            themes[cat][theme]["statuses"][ticket.get("status", "unknown")] += 1

            for tag in tags[:5]:
                themes[cat][theme]["tags"][tag] += 1

            if is_high_priority(ticket):
                themes[cat][theme]["high_priority_count"] += 1

            # Add example (limit to 5)
            if len(themes[cat][theme]["examples"]) < 5:
                themes[cat][theme]["examples"].append({
                    "verbatim": f"{subject}: {description[:150]}",
                    "link": ticket_url,
                    "source": "Zendesk",
                    "account": account_display,
                    "status": ticket.get("status"),
                    "priority": ticket.get("priority"),
                    "created": ticket.get("created_at"),
                })

    return themes


def analyze_modjo_calls(calls):
    """Analyze Modjo calls."""
    themes = defaultdict(lambda: defaultdict(lambda: {
        "count": 0,
        "accounts": set(),
        "examples": [],
        "high_priority_count": 0,
    }))

    for call in calls:
        title = call.get("Title", "")
        summary = call.get("Summary", "")[:500]
        tags_str = call.get("Tags", "")

        text = f"{title} {summary} {tags_str}"
        categories = categorize(text)

        # Extract name from title (e.g., "Bruno Ribier and Fabien Lebreton")
        account_display = title[:50] if title else "Unknown"

        theme = title[:60] if title else "Call"
        url = call.get("Transcript URL", "")

        urgency = str(call.get("Urgency", "")).lower()
        is_high = urgency in ["4", "5", "high", "urgent"]

        for cat in categories:
            themes[cat][theme]["count"] += 1
            themes[cat][theme]["accounts"].add(account_display)

            if is_high:
                themes[cat][theme]["high_priority_count"] += 1

            if len(themes[cat][theme]["examples"]) < 5:
                themes[cat][theme]["examples"].append({
                    "verbatim": f"{title}: {summary[:150]}",
                    "link": url,
                    "source": "Modjo",
                    "account": account_display,
                })

    return themes


def merge_themes(zendesk_themes, modjo_themes):
    """Merge themes from both sources."""
    merged = defaultdict(lambda: defaultdict(lambda: {
        "count": 0,
        "accounts": set(),
        "examples": [],
        "high_priority_count": 0,
    }))

    # Add Zendesk themes
    for cat, themes in zendesk_themes.items():
        for theme, data in themes.items():
            merged[cat][theme]["count"] += data["count"]
            merged[cat][theme]["accounts"].update(data["accounts"])
            merged[cat][theme]["examples"].extend(data["examples"][:3])
            merged[cat][theme]["high_priority_count"] += data["high_priority_count"]

    # Add Modjo themes
    for cat, themes in modjo_themes.items():
        for theme, data in themes.items():
            merged[cat][theme]["count"] += data["count"]
            merged[cat][theme]["accounts"].update(data["accounts"])
            merged[cat][theme]["examples"].extend(data["examples"][:2])
            merged[cat][theme]["high_priority_count"] += data["high_priority_count"]

    return merged


def count_by_category(zendesk_themes, modjo_themes):
    """Count totals per category."""
    counts = Counter()

    for cat, themes in zendesk_themes.items():
        for theme, data in themes.items():
            counts[cat] += data["count"]

    for cat, themes in modjo_themes.items():
        for theme, data in themes.items():
            counts[cat] += data["count"]

    return counts


def is_question(text):
    """Check if text is a question."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in QUESTION_KEYWORDS)


def extract_questions(tickets):
    """Extract questions from ticket subjects."""
    questions = defaultdict(lambda: {"count": 0, "customers": set(), "category": "Other", "sample": None})

    for ticket in tickets:
        subject = ticket.get("subject", "")
        if is_question(subject):
            # Normalize question (remove ticket numbers, clean up)
            q = re.sub(r'#?\d+', '', subject).strip()[:80]
            if len(q) > 10:  # Skip very short questions
                questions[q]["count"] += 1
                org_name = ticket.get("organization_name")
                if org_name:
                    questions[q]["customers"].add(org_name)
                categories = categorize(subject)
                questions[q]["category"] = categories[0] if categories else "Other"
                if not questions[q]["sample"]:
                    questions[q]["sample"] = ticket.get("id")

    return questions


def calculate_solve_metrics(tickets):
    """Calculate solve time and status metrics."""
    total = len(tickets)
    if total == 0:
        return {"total": 0, "solved_pct": 0, "pending_pct": 0, "open_pct": 0, "avg_solve_time": 0}

    statuses = Counter(t.get("status", "unknown") for t in tickets)

    # Calculate average solve time (for solved tickets)
    solve_times = []
    for t in tickets:
        if t.get("status") == "solved" and t.get("created_at") and t.get("updated_at"):
            try:
                created = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
                updated = datetime.fromisoformat(t["updated_at"].replace("Z", "+00:00"))
                hours = (updated - created).total_seconds() / 3600
                if hours > 0:
                    solve_times.append(hours)
            except:
                pass

    avg_solve = sum(solve_times) / len(solve_times) if solve_times else 0

    return {
        "total": total,
        "solved_pct": round((statuses.get("solved", 0) + statuses.get("closed", 0)) / total * 100, 1),
        "pending_pct": round(statuses.get("pending", 0) / total * 100, 1),
        "open_pct": round((statuses.get("open", 0) + statuses.get("new", 0)) / total * 100, 1),
        "avg_solve_time": round(avg_solve, 1),
        "status_counts": dict(statuses),
    }


def calculate_evolution(current, previous):
    """Calculate percentage change."""
    if previous == 0:
        return 0 if current == 0 else 100
    return round((current - previous) / previous * 100, 1)


def get_trend_emoji(change):
    """Get trend emoji based on change percentage."""
    if change > 10:
        return "📈"
    elif change < -10:
        return "📉"
    else:
        return "➡️"


def get_top_issues(tickets, org_lookup, limit=10, tickets_lw=None):
    """Get top issues by occurrence count with enhanced context."""
    if tickets_lw is None:
        tickets_lw = []

    # Group by normalized subject patterns
    issues_tw = defaultdict(lambda: {
        "count": 0,
        "customers": set(),
        "examples": [],
        "tickets": []
    })
    issues_lw = defaultdict(lambda: {"count": 0})

    # Collect current period issues
    for ticket in tickets:
        subject = ticket.get("subject", "")
        if not subject:
            continue

        # Normalize subject for grouping (first 80 chars)
        normalized_subject = subject[:80]

        issues_tw[normalized_subject]["count"] += 1
        org_name = ticket.get("organization_name")
        if org_name:
            issues_tw[normalized_subject]["customers"].add(org_name)

        # Store full ticket for detailed analysis
        if len(issues_tw[normalized_subject]["tickets"]) < 5:
            issues_tw[normalized_subject]["tickets"].append(ticket)

    # Collect last period issues
    for ticket in tickets_lw:
        subject = ticket.get("subject", "")[:80]
        if subject:
            issues_lw[subject]["count"] += 1

    # Build enhanced result
    result = []
    for issue, data in sorted(issues_tw.items(), key=lambda x: -x[1]["count"])[:limit]:
        tw = data["count"]
        lw = issues_lw.get(issue, {}).get("count", 0)

        # Determine if new
        is_new = lw == 0

        # Calculate trend
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

        # Get example ticket subjects (2-3 variations)
        example_subjects = []
        seen = set()
        for ticket in data["tickets"][:3]:
            subj = ticket.get("subject", "")[:60]
            if subj and subj not in seen:
                example_subjects.append(subj)
                seen.add(subj)

        # Get top affected customers
        customer_list = sorted(data["customers"])[:5]

        result.append((issue, {
            "count": tw,
            "Customers": len(data["customers"]),
            "Trend": trend,
            "IsNew": is_new,
            "Examples": example_subjects,
            "AffectedCustomers": customer_list
        }))

    return result


def get_agent_stats(tickets):
    """Get ticket stats per agent (assignee)."""
    agent_stats = defaultdict(lambda: {"assigned": 0, "solved": 0})

    for ticket in tickets:
        assignee = ticket.get("assignee_id")
        if assignee:
            # Use assignee name if available, otherwise ID
            agent_name = f"Agent {assignee}"
            agent_stats[agent_name]["assigned"] += 1
            if ticket.get("status") in ["solved", "closed"]:
                agent_stats[agent_name]["solved"] += 1

    return agent_stats


def fetch_zendesk_users():
    """Fetch Zendesk users (agents and admins) for name lookup."""
    print("      Fetching agents...")
    users = {}

    # Fetch agents
    for role in ["agent", "admin"]:
        url = f"{ZENDESK_BASE_URL}/users.json?role={role}&per_page=100"
        while url:
            response = requests.get(url, auth=ZENDESK_AUTH)
            if response.status_code != 200:
                break
            data = response.json()
            for user in data.get("users", []):
                users[user["id"]] = user.get("name", f"Agent {user['id']}")
            url = data.get("next_page")

    print(f"      → {len(users)} agents loaded")
    return users


def fetch_user_by_id(user_id):
    """Fetch a single user by ID."""
    url = f"{ZENDESK_BASE_URL}/users/{user_id}.json"
    response = requests.get(url, auth=ZENDESK_AUTH)
    if response.status_code == 200:
        user = response.json().get("user", {})
        return user.get("name", f"Agent {user_id}")
    return None


def enrich_agent_lookup(tickets, agent_lookup):
    """Ensure all assignees in tickets have names in the lookup."""
    missing_ids = set()

    for ticket in tickets:
        assignee_id = ticket.get("assignee_id")
        if assignee_id and assignee_id not in agent_lookup:
            missing_ids.add(assignee_id)

    # Fetch missing users
    for user_id in missing_ids:
        name = fetch_user_by_id(user_id)
        if name:
            agent_lookup[user_id] = name

    if missing_ids:
        print(f"      → Fetched {len(missing_ids)} additional agent names")

    return agent_lookup


def get_agent_stats_with_names(tickets, agent_lookup):
    """Get ticket stats per agent with real names."""
    agent_stats = defaultdict(lambda: {"assigned": 0, "solved": 0})

    for ticket in tickets:
        assignee_id = ticket.get("assignee_id")
        if assignee_id:
            agent_name = agent_lookup.get(assignee_id, f"Agent {assignee_id}")
            agent_stats[agent_name]["assigned"] += 1
            if ticket.get("status") in ["solved", "closed"]:
                agent_stats[agent_name]["solved"] += 1

    # Sort by assigned count
    sorted_agents = sorted(agent_stats.items(), key=lambda x: -x[1]["assigned"])
    return sorted_agents


# ============== NOTION ==============

def notion_create_page(db_id, properties):
    """Create a page in a Notion database."""
    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers=NOTION_HEADERS,
        json={"parent": {"database_id": db_id}, "properties": properties}
    )
    return response.status_code == 200


def notion_add_metrics(date_str, calls, tickets, high_priority, categories):
    """Add weekly metrics to Notion."""
    return notion_create_page(NOTION_METRICS_DB, {
        "Week": {"title": [{"text": {"content": f"Week of {date_str}"}}]},
        "Date": {"date": {"start": date_str}},
        "Calls": {"number": calls},
        "Tickets": {"number": tickets},
        "High Urgency": {"number": high_priority},
        "Booking Sync": {"number": categories.get("Booking.com Sync", 0)},
        "Payment RIB": {"number": categories.get("Payment/RIB", 0)},
        "Pricing Bugs": {"number": categories.get("Pricing Bugs", 0)},
        "Airbnb Sync": {"number": categories.get("Airbnb Sync", 0)},
        "VRBO Issues": {"number": categories.get("VRBO Issues", 0)},
        "Notifications": {"number": categories.get("Notifications", 0)},
        "Other": {"number": categories.get("Other", 0)},
    })


def notion_add_analysis(date_str, item, section, priority, category, details, status,
                        occurrences, accounts, examples):
    """Add analysis entry to Notion."""

    # Format accounts
    accounts_list = list(accounts)[:15]
    accounts_text = ", ".join(accounts_list)
    if len(accounts) > 15:
        accounts_text += f" (+{len(accounts)-15} more)"

    # Format examples with links
    examples_text = ""
    for i, ex in enumerate(examples[:3], 1):
        examples_text += f"{i}. [{ex['source']}] {ex['verbatim'][:100]}\n"
        if ex.get('link'):
            examples_text += f"   → {ex['link']}\n"
        examples_text += f"   Customer: {ex.get('account', 'N/A')}\n\n"

    return notion_create_page(NOTION_DEEP_ANALYSIS_DB, {
        "Item": {"title": [{"text": {"content": item[:100]}}]},
        "Week": {"date": {"start": date_str}},
        "Section": {"select": {"name": section}},
        "Priority": {"select": {"name": priority}},
        "Category": {"select": {"name": category}},
        "Details": {"rich_text": [{"text": {"content": details[:2000]}}]},
        "Status": {"select": {"name": status}},
        "Occurrences": {"number": occurrences},
        "Accounts Affected": {"rich_text": [{"text": {"content": accounts_text[:2000]}}]},
        "Examples": {"rich_text": [{"text": {"content": examples_text[:2000]}}]},
    })


def notion_add_atrisk(date_str, account, risk_level, signal, action, status):
    """Add at-risk account."""
    return notion_create_page(NOTION_ATRISK_DB, {
        "Account": {"title": [{"text": {"content": account}}]},
        "First Flagged": {"date": {"start": date_str}},
        "Last Updated": {"date": {"start": date_str}},
        "Risk Level": {"select": {"name": risk_level}},
        "Signal": {"rich_text": [{"text": {"content": signal[:2000]}}]},
        "Action Needed": {"rich_text": [{"text": {"content": action[:2000]}}]},
        "Status": {"select": {"name": status}},
    })


def notion_add_dashboard(date_str, metrics, last_week_metrics=None):
    """Add weekly dashboard metrics."""
    wow_change = ""
    if last_week_metrics:
        change = calculate_evolution(metrics["total"], last_week_metrics["total"])
        wow_change = f"{get_trend_emoji(change)} {change:+.1f}%"

    return notion_create_page(NOTION_DASHBOARD_DB, {
        "Week": {"title": [{"text": {"content": f"Week of {date_str}"}}]},
        "Date": {"date": {"start": date_str}},
        "Total Tickets": {"number": metrics["total"]},
        "Solved %": {"number": metrics["solved_pct"]},
        "Pending %": {"number": metrics["pending_pct"]},
        "Open %": {"number": metrics["open_pct"]},
        "Avg Solve Time (hrs)": {"number": metrics["avg_solve_time"]},
        "WoW Change": {"rich_text": [{"text": {"content": wow_change}}]},
    })


def notion_add_category(date_str, category, ticket_count, pct_of_total, rank,
                         last_week_count=0, last_month_avg=0):
    """Add category to categories database."""
    wow_change = calculate_evolution(ticket_count, last_week_count)
    mom_change = calculate_evolution(ticket_count, last_month_avg)

    return notion_create_page(NOTION_CATEGORIES_DB, {
        "Category": {"title": [{"text": {"content": category}}]},
        "Week": {"date": {"start": date_str}},
        "Tickets": {"number": ticket_count},
        "% of Total": {"number": round(pct_of_total, 1)},
        "Rank": {"number": rank},
        "WoW Change": {"rich_text": [{"text": {"content": f"{get_trend_emoji(wow_change)} {wow_change:+.1f}%"}}]},
        "MoM Change": {"rich_text": [{"text": {"content": f"{get_trend_emoji(mom_change)} {mom_change:+.1f}%"}}]},
        "Last Week": {"number": last_week_count},
        "Last Month Avg": {"number": round(last_month_avg, 1)},
    })


def notion_add_issue(date_str, issue, ticket_count, customers, rank, last_week_count=0):
    """Add issue to issues database."""
    wow_change = calculate_evolution(ticket_count, last_week_count)

    # Trend indicator
    if last_week_count == 0:
        trend = "🆕 New"
    else:
        trend = f"{get_trend_emoji(wow_change)} {wow_change:+.1f}%"

    customers_list = list(customers)[:10]
    customers_text = ", ".join(customers_list)
    if len(customers) > 10:
        customers_text += f" (+{len(customers)-10} more)"

    return notion_create_page(NOTION_ISSUES_DB, {
        "Issue": {"title": [{"text": {"content": issue[:100]}}]},
        "Week": {"date": {"start": date_str}},
        "Tickets": {"number": ticket_count},
        "Customers": {"rich_text": [{"text": {"content": customers_text[:2000]}}]},
        "Customer Count": {"number": len(customers)},
        "Rank": {"number": rank},
        "Trend": {"rich_text": [{"text": {"content": trend}}]},
        "Last Week": {"number": last_week_count},
    })


def notion_add_question(date_str, question, ticket_count, customers, category, rank, sample_ticket_id=None):
    """Add question to questions database."""
    customers_list = list(customers)[:5]
    customers_text = ", ".join(customers_list)
    if len(customers) > 5:
        customers_text += f" (+{len(customers)-5} more)"

    sample_url = ""
    if sample_ticket_id:
        sample_url = f"https://{ZENDESK_SUBDOMAIN}.zendesk.com/agent/tickets/{sample_ticket_id}"

    return notion_create_page(NOTION_QUESTIONS_DB, {
        "Question": {"title": [{"text": {"content": question[:100]}}]},
        "Week": {"date": {"start": date_str}},
        "Tickets": {"number": ticket_count},
        "Customers": {"rich_text": [{"text": {"content": customers_text[:500]}}]},
        "Category": {"select": {"name": category}},
        "Rank": {"number": rank},
        "Sample Ticket": {"url": sample_url} if sample_url else {"url": None},
    })


def analyze_category_deep_dive(tickets, category_counts):
    """Analyze top 10 categories to identify sub-issues and patterns."""

    # Group tickets by category
    by_category = defaultdict(list)
    for t in tickets:
        subject = t.get('subject', '')
        description = t.get('description', '') or ''
        text = f'{subject} {description}'
        cat = categorize_detailed(text)
        by_category[cat].append(t)

    # Get top 10 categories
    top_cats = [cat for cat, count in category_counts[:10]]

    deep_dive = {}

    for cat in top_cats:
        cat_tickets = by_category.get(cat, [])
        if not cat_tickets:
            continue

        issues = defaultdict(list)

        for t in cat_tickets:
            subject = t.get('subject', '')
            desc = (t.get('description', '') or '')
            ticket_id = t.get('id')
            url = f'https://{ZENDESK_SUBDOMAIN}.zendesk.com/agent/tickets/{ticket_id}'
            status = t.get('status', 'unknown')
            priority = t.get('priority', 'normal')
            org = t.get('organization', {})
            org_name = org.get('name', 'Unknown') if isinstance(org, dict) else 'Unknown'

            # Extract a meaningful excerpt from description (first 150 chars, cleaned)
            desc_clean = desc.replace('\n', ' ').replace('\r', ' ').strip()
            # Remove common email prefixes/signatures
            for prefix in ['Hi,', 'Hello,', 'Bonjour,', 'Dear', 'Hi team', 'Hello team']:
                if desc_clean.startswith(prefix):
                    desc_clean = desc_clean[len(prefix):].strip()
            excerpt = desc_clean[:150] + '...' if len(desc_clean) > 150 else desc_clean

            desc_lower = desc.lower()
            subject_lower = subject.lower()
            combined = f'{subject_lower} {desc_lower}'

            # Build ticket info dict with rich details
            ticket_info = {
                'subject': subject,
                'url': url,
                'id': ticket_id,
                'status': status,
                'priority': priority,
                'org': org_name,
                'excerpt': excerpt,
            }

            # Classify based on category
            if 'New Connections' in cat:
                if 'add new' in combined or 'nouvelle' in combined or 'ajouter' in combined:
                    issues['New listing connection'].append(ticket_info)
                elif 'sync' in combined or 'synchron' in combined:
                    issues['Sync existing listing'].append(ticket_info)
                else:
                    issues['Connection request'].append(ticket_info)

            elif 'SmilyPay' in cat or 'Payment' in cat:
                if 'document rejected' in combined or 'document refus' in combined:
                    issues['Document rejected (KYC)'].append(ticket_info)
                elif 'chargeback' in combined:
                    issues['Chargeback'].append(ticket_info)
                elif 'production' in combined and 'rejected' not in combined:
                    issues['Go to production'].append(ticket_info)
                elif 'paiement' in combined or 'payment' in combined or 'virement' in combined:
                    issues['Payment issue'].append(ticket_info)
                else:
                    issues['Other payment'].append(ticket_info)

            elif 'Booking.com' in cat and 'New' not in cat:
                if 'sync' in combined or 'synchron' in combined or 'bloqué' in combined or 'blocked' in combined:
                    issues['Sync/blocked issues'].append(ticket_info)
                elif 'calendar' in combined or 'calendrier' in combined or 'disponibilité' in combined:
                    issues['Calendar/availability'].append(ticket_info)
                elif 'price' in combined or 'prix' in combined or 'tarif' in combined or 'markup' in combined:
                    issues['Pricing issues'].append(ticket_info)
                elif 'photo' in combined or 'image' in combined:
                    issues['Photo sync'].append(ticket_info)
                else:
                    issues['Other Booking.com'].append(ticket_info)

            elif 'Rental' in cat:
                if 'disconnect' in combined or 'déconnect' in combined:
                    issues['Disconnect listing'].append(ticket_info)
                elif 'restore' in combined or 'restaurer' in combined:
                    issues['Restore rental'].append(ticket_info)
                elif 'duplicate' in combined or 'dupliquer' in combined:
                    issues['Duplicate'].append(ticket_info)
                else:
                    issues['Other rental config'].append(ticket_info)

            elif 'Airbnb' in cat:
                if 'sync' in combined or 'synchron' in combined:
                    issues['Sync issues'].append(ticket_info)
                elif 'photo' in combined:
                    issues['Photo sync'].append(ticket_info)
                else:
                    issues['Other Airbnb'].append(ticket_info)

            elif 'Mobile App' in cat:
                if 'login' in combined or 'sign in' in combined or 'connexion' in combined:
                    issues['Login issues'].append(ticket_info)
                elif 'crash' in combined or 'bug' in combined or 'erreur' in combined:
                    issues['Crashes/Bugs'].append(ticket_info)
                elif 'notification' in combined:
                    issues['Push notifications'].append(ticket_info)
                else:
                    issues['Other mobile'].append(ticket_info)

            elif 'Feature Request' in cat:
                if 'channel' in combined or 'ota' in combined:
                    issues['Channel/OTA feature'].append(ticket_info)
                elif 'report' in combined or 'export' in combined:
                    issues['Reporting feature'].append(ticket_info)
                elif 'automation' in combined or 'automatic' in combined:
                    issues['Automation feature'].append(ticket_info)
                else:
                    issues['Other feature'].append(ticket_info)

            elif 'Notification' in cat or 'Automation' in cat:
                if 'check-in' in combined or 'checkin' in combined:
                    issues['Check-in notifications'].append(ticket_info)
                elif 'checkout' in combined:
                    issues['Check-out notifications'].append(ticket_info)
                elif 'message' in combined or 'email' in combined:
                    issues['Automated messages'].append(ticket_info)
                else:
                    issues['Other notifications'].append(ticket_info)

            elif 'API' in cat or 'Integration' in cat:
                if 'webhook' in combined:
                    issues['Webhook issues'].append(ticket_info)
                elif 'api key' in combined or 'token' in combined or 'auth' in combined:
                    issues['Authentication'].append(ticket_info)
                elif 'rate limit' in combined:
                    issues['Rate limiting'].append(ticket_info)
                else:
                    issues['Other API'].append(ticket_info)

            else:
                # Generic classification for unmapped categories
                if 'unlock' in combined or 'débloquer' in combined or 'blocked' in combined or 'bloqué' in combined:
                    issues['Unlock/unblock request'].append(ticket_info)
                elif 'urgent' in combined or 'asap' in combined:
                    issues['Urgent request'].append(ticket_info)
                elif 'access' in combined or 'accès' in combined or 'permission' in combined:
                    issues['Access/permissions'].append(ticket_info)
                elif 'config' in combined or 'setting' in combined or 'paramètre' in combined:
                    issues['Configuration'].append(ticket_info)
                elif 'error' in combined or 'erreur' in combined or 'bug' in combined:
                    issues['Error/Bug'].append(ticket_info)
                elif 'how to' in combined or 'comment' in combined:
                    issues['How-to question'].append(ticket_info)
                else:
                    # Group by first 3 words of subject for truly generic tickets
                    subject_key = ' '.join(subject.split()[:3]) if subject else 'Other'
                    issues[subject_key].append(ticket_info)

        # Sort issues by count
        sorted_issues = sorted(issues.items(), key=lambda x: -len(x[1]))

        # Group tickets within each issue type by similar subject pattern
        # to identify recurring vs one-time requests
        grouped_issues = []
        for issue_type, tix in sorted_issues:
            # Group by normalized subject
            subject_groups = defaultdict(list)
            for t in tix:
                # Normalize subject for grouping
                subj = t['subject'].lower()
                # Remove common prefixes
                for prefix in ['re:', 'fwd:', 'fw:', 'tr:', '[bookingsync]', '[smily]', 're :', 'tr :']:
                    subj = subj.replace(prefix, '')
                # Remove ticket numbers and IDs
                subj = re.sub(r'#?\d{5,}', '', subj)
                subj = re.sub(r'\[.*?\]', '', subj)
                subj = subj.strip()[:40]  # First 40 chars for grouping

                subject_groups[subj].append(t)

            # Convert to list of (pattern, tickets, occurrence_count) and sort by occurrence
            grouped_tix = []
            for pattern, tickets in subject_groups.items():
                # Use the first ticket's original subject as display
                grouped_tix.append({
                    'tickets': tickets,
                    'count': len(tickets),
                    'display_subject': tickets[0]['subject'],
                    'is_recurring': len(tickets) > 1,
                })

            # Sort by occurrence count (most recurring first)
            grouped_tix.sort(key=lambda x: -x['count'])

            grouped_issues.append((issue_type, tix, grouped_tix))

        # Determine pattern type and verdict
        total = len(cat_tickets)
        unique_patterns = len(sorted_issues)
        top_pct = len(sorted_issues[0][1]) / total * 100 if sorted_issues else 0

        if unique_patterns <= 3 or top_pct >= 50:
            pattern_type = "similar"
            verdict = f"⚠️ Mostly SAME request type — {sorted_issues[0][0]} accounts for {top_pct:.0f}% of tickets"
        elif top_pct >= 25:
            pattern_type = "mixed"
            verdict = f"🔶 Mix of requests — top issue ({sorted_issues[0][0]}) is {top_pct:.0f}%, but {unique_patterns} different patterns"
        else:
            pattern_type = "diverse"
            verdict = f"ℹ️ Diverse requests — {unique_patterns} different patterns, no dominant issue"

        # Get unique customers affected
        all_orgs = set()
        for issue_type, tix in sorted_issues:
            for t in tix:
                if t['org'] != 'Unknown':
                    all_orgs.add(t['org'])

        deep_dive[cat] = {
            'total': total,
            'issues': sorted_issues[:5],  # Top 5 sub-issues (original)
            'grouped_issues': grouped_issues[:5],  # Top 5 with grouped tickets
            'pattern_type': pattern_type,
            'top_pct': top_pct,
            'verdict': verdict,
            'unique_customers': len(all_orgs),
            'unique_patterns': unique_patterns,
        }

    return deep_dive


def notion_find_summary_page(date_str):
    """Find existing summary page for the given date by checking child pages."""
    parent_page_id = os.getenv("NOTION_PAGE_ID")

    # Get children of parent page
    response = requests.get(
        f"https://api.notion.com/v1/blocks/{parent_page_id}/children?page_size=100",
        headers=NOTION_HEADERS
    )

    if response.status_code == 200:
        results = response.json().get("results", [])
        for block in results:
            if block.get("type") == "child_page":
                title = block.get("child_page", {}).get("title", "")
                if date_str in title and "Zendesk Weekly Summary" in title:
                    return block.get("id")
    return None


def notion_delete_page_content(page_id):
    """Delete all blocks from a page."""
    # Get existing blocks
    response = requests.get(
        f"https://api.notion.com/v1/blocks/{page_id}/children",
        headers=NOTION_HEADERS
    )

    if response.status_code == 200:
        blocks = response.json().get("results", [])
        for block in blocks:
            requests.delete(
                f"https://api.notion.com/v1/blocks/{block['id']}",
                headers=NOTION_HEADERS
            )


def notion_append_blocks(page_id, children):
    """Append blocks to a page."""
    # Notion limits to 100 blocks per request
    for i in range(0, len(children), 100):
        chunk = children[i:i+100]
        requests.patch(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=NOTION_HEADERS,
            json={"children": chunk}
        )


def notion_update_recent_reports_section(new_page_url, new_page_title, report_type="Zendesk", date_str=None):
    """Insert a link to the new report at the top of the reports list.

    This function:
    1. Updates the 'Reports (last update: XX)' heading with today's date
    2. Inserts a link to the new report right after the heading (at the top)
    3. Does NOT delete any existing content
    """
    parent_page_id = os.getenv("NOTION_PAGE_ID")
    reports_heading_id = "3585d6a2-0ddc-8084-a2e0-ca5fed7e668e"  # Fixed heading ID

    # Step 1: Update the heading text with the date
    if date_str:
        try:
            response = requests.patch(
                f"https://api.notion.com/v1/blocks/{reports_heading_id}",
                headers=NOTION_HEADERS,
                json={
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": f"Reports (last update: {date_str})"}}]
                    }
                }
            )
        except:
            pass

    # Step 2: Insert a link to the report right after the heading (at the top of the list)
    icon = "📊" if report_type == "Zendesk" else "📞" if report_type == "Modjo" else "📄"

    new_block = {
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": f"{icon} "}},
                {
                    "type": "text",
                    "text": {
                        "content": new_page_title,
                        "link": {"url": new_page_url}
                    },
                    "annotations": {"bold": True}
                }
            ]
        }
    }

    try:
        response = requests.patch(
            f"https://api.notion.com/v1/blocks/{parent_page_id}/children",
            headers=NOTION_HEADERS,
            json={
                "children": [new_block],
                "after": reports_heading_id
            }
        )
        return response.status_code == 200
    except:
        return False


def notion_create_summary_page(date_str, tickets, tickets_lw, category_counts, category_counts_lw,
                                top_issues, top_issues_lw, top_customers, top_customers_lw,
                                questions, agent_stats, agent_stats_lw, metrics=None, category_deep_dive=None,
                                questions_lw=None, date_range=None):
    """Create or update a formatted summary page in Notion with WoW/MoM and enhanced insights."""
    total = len(tickets)
    total_lw = len(tickets_lw)
    change = ((total - total_lw) / total_lw * 100) if total_lw > 0 else 0
    trend = "📈" if change > 0 else "📉" if change < 0 else "➡️"

    # Calculate metrics if not provided
    if metrics is None:
        metrics = calculate_solve_metrics(tickets)

    # Format title with date range if provided
    if date_range:
        page_title = f"Zendesk Weekly Summary — {date_range}"
        header_title = f"Zendesk Weekly Insights — {date_range}"
    else:
        page_title = f"Zendesk Weekly Summary — {date_str}"
        header_title = f"Zendesk Weekly Insights — {date_str}"

    # Check if page already exists for today
    existing_page_id = notion_find_summary_page(date_str)

    # Build lookup dicts
    cat_lw_dict = dict(category_counts_lw) if category_counts_lw else {}

    # Handle top_issues_lw - list of (issue, {count, customers}) tuples
    issues_lw_dict = {}
    if top_issues_lw:
        for item in top_issues_lw:
            if len(item) == 2:
                issue, data = item
                issues_lw_dict[issue] = data.get("count", 0) if isinstance(data, dict) else 0

    customers_lw_dict = dict(top_customers_lw) if top_customers_lw else {}

    # Handle agent_stats_lw - list of (agent, {assigned, solved}) tuples
    agents_lw_dict = {}
    if agent_stats_lw:
        for item in agent_stats_lw:
            if len(item) == 2:
                agent, stats = item
                agents_lw_dict[agent] = stats

    # Build content blocks
    children = []

    # Header
    children.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {"content": header_title}}]}
    })

    # Executive Summary
    exec_summary_blocks = create_executive_summary_blocks(tickets, tickets_lw, metrics, category_counts)
    children.extend(exec_summary_blocks)

    # Original Overview (kept for context)
    children.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": f"{total} tickets this week {trend} {change:+.0f}% vs last week ({total_lw})"}}],
            "icon": {"emoji": "📬"}
        }
    })

    # Top Categories header
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🗂️ Top Categories"}}]}
    })

    # Categories with WoW
    for i, (cat, count) in enumerate(category_counts[:10], 1):
        pct = count / total * 100 if total > 0 else 0
        lw_count = cat_lw_dict.get(cat, 0)
        wow = calculate_evolution(count, lw_count)
        wow_str = f"{get_trend_emoji(wow)} {wow:+.0f}% WoW"

        children.append({
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{cat}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — {count} tickets ({pct:.1f}%) | {wow_str}"}}
            ]}
        })

    # Booking insight
    booking_total = sum(c for cat, c in category_counts if "Booking" in cat)
    booking_pct = booking_total / total * 100 if total > 0 else 0
    children.append({
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": [{"type": "text", "text": {"content": f"💡 Booking.com accounts for ~{booking_pct:.0f}% of all tickets"}}]}
    })

    # Category Deep Dive section
    if category_deep_dive:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🔍 Category Deep Dive"}}]}
        })

        for cat, data in category_deep_dive.items():
            # Category toggle with sub-issues
            sub_children = []

            # Verdict callout - prominent pattern analysis
            verdict_color = "yellow_background" if data['pattern_type'] == "similar" else "orange_background" if data['pattern_type'] == "mixed" else "blue_background"
            sub_children.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": data['verdict']}}],
                    "icon": {"emoji": "🎯"},
                    "color": verdict_color
                }
            })

            # Stats summary
            sub_children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [
                    {"type": "text", "text": {"content": f"📊 {data['total']} tickets"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f" • {data.get('unique_customers', 0)} customers affected • {data.get('unique_patterns', 0)} different request types"}}
                ]}
            })

            # Sub-issues breakdown with grouped tickets sorted by occurrence
            for issue_type, all_tix, grouped_tix in data.get('grouped_issues', [])[:5]:
                pct = len(all_tix) / data['total'] * 100

                # Get unique orgs for this issue type
                issue_orgs = set(t['org'] for t in all_tix if t['org'] != 'Unknown')
                orgs_str = f" from {len(issue_orgs)} customers" if issue_orgs else ""

                # Count recurring vs one-time
                recurring_count = sum(1 for g in grouped_tix if g['is_recurring'])
                onetime_count = len(grouped_tix) - recurring_count

                # Create ticket details list - now grouped and sorted by occurrence
                ticket_items = []

                # Summary of recurring vs one-time
                if grouped_tix:
                    summary_text = f"🔁 {recurring_count} recurring patterns, 1️⃣ {onetime_count} one-time requests"
                    ticket_items.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [
                            {"type": "text", "text": {"content": summary_text}, "annotations": {"italic": True, "color": "gray"}}
                        ]}
                    })

                for group in grouped_tix[:4]:
                    tickets = group['tickets']
                    count = group['count']
                    t = tickets[0]  # Representative ticket

                    # Occurrence indicator
                    if count > 1:
                        occurrence_badge = f"🔁 {count}x"
                        callout_color = "yellow_background"
                    else:
                        occurrence_badge = "1️⃣ One-time"
                        callout_color = "gray_background"

                    # Status emoji
                    status_emoji = "✅" if t['status'] == 'solved' else "🔄" if t['status'] == 'open' else "⏳" if t['status'] == 'pending' else "📌"
                    priority_flag = "🔴 " if t['priority'] == 'high' or t['priority'] == 'urgent' else ""

                    # Build customer list if recurring
                    if count > 1:
                        customers = list(set(tk['org'] for tk in tickets if tk['org'] != 'Unknown'))[:3]
                        customers_str = ", ".join(customers) if customers else "Multiple customers"
                        if len(set(tk['org'] for tk in tickets if tk['org'] != 'Unknown')) > 3:
                            customers_str += f" +{len(set(tk['org'] for tk in tickets if tk['org'] != 'Unknown')) - 3} more"
                    else:
                        customers_str = t['org']

                    # Ticket with rich info and occurrence badge
                    ticket_items.append({
                        "object": "block",
                        "type": "callout",
                        "callout": {
                            "rich_text": [
                                {"type": "text", "text": {"content": f"{occurrence_badge} "}, "annotations": {"bold": True}},
                                {"type": "text", "text": {"content": f"{priority_flag}{t['subject'][:55]}", "link": {"url": t['url']}}},
                                {"type": "text", "text": {"content": f"\n{status_emoji} {t['status'].title()} • {customers_str}\n"}},
                                {"type": "text", "text": {"content": f'"{t["excerpt"][:100]}"' if t.get('excerpt') else ""}, "annotations": {"italic": True, "color": "gray"}}
                            ],
                            "icon": {"emoji": "🎫"},
                            "color": callout_color
                        }
                    })

                if len(grouped_tix) > 4:
                    remaining = len(grouped_tix) - 4
                    ticket_items.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [
                            {"type": "text", "text": {"content": f"➕ {remaining} more request patterns..."}, "annotations": {"italic": True, "color": "gray"}}
                        ]}
                    })

                sub_children.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"{issue_type}"}, "annotations": {"bold": True}},
                            {"type": "text", "text": {"content": f" — {len(all_tix)} tickets ({pct:.0f}%){orgs_str}"}}
                        ],
                        "children": ticket_items
                    }
                })

            # Main category toggle
            pattern_emoji = "⚠️" if data['pattern_type'] == "similar" else "🔶" if data['pattern_type'] == "mixed" else "ℹ️"
            children.append({
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"{pattern_emoji} {cat}"}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f" — {data['total']} tickets ({data['top_pct']:.0f}% are {data['issues'][0][0] if data['issues'] else 'N/A'})"}}
                    ],
                    "children": sub_children
                }
            })

    # Actionable Insights section
    insights = generate_actionable_insights(tickets, category_counts)
    if insights:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "💡 Actionable Insights & Recommendations"}}]}
        })

        for insight in insights[:5]:  # Top 5 insights
            priority_emoji = "🔴" if insight["priority"] == "high" else "🟡"

            insight_blocks = []

            # Recommendation details
            insight_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [
                    {"type": "text", "text": {"content": f"📌 {insight['description']}"}}
                ]}
            })

            insight_blocks.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Recommendation: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": insight['recommendation']}}
                    ],
                    "icon": {"emoji": "✅"},
                    "color": "blue_background"
                }
            })

            # Main insight toggle
            children.append({
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"{priority_emoji} {insight['icon']} {insight['title']}"}, "annotations": {"bold": True}}
                    ],
                    "children": insight_blocks
                }
            })

    # Top Issues header
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🔥 Top Issues"}}]}
    })

    # Issues with WoW
    for issue, data in top_issues[:7]:
        customers_count = data["Customers"]
        lw_count = issues_lw_dict.get(issue, 0)
        if lw_count == 0:
            trend_str = "🆕 New"
        else:
            wow = calculate_evolution(data["count"], lw_count)
            trend_str = f"{get_trend_emoji(wow)} {wow:+.0f}% WoW"

        # Get example tickets and affected customers
        examples = data.get("Examples", [])[:3]  # Show up to 3 examples
        affected_customers = data.get("AffectedCustomers", [])[:5]  # Show up to 5 customers

        # Create toggle with examples
        example_blocks = []

        # Add affected customers
        if affected_customers:
            customers_str = ", ".join(affected_customers)
            example_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [
                    {"type": "text", "text": {"content": "👥 Customers: "}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": customers_str}}
                ]}
            })

        # Add example subjects/questions
        if examples:
            example_blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [
                    {"type": "text", "text": {"content": "📋 Examples:"}, "annotations": {"bold": True}}
                ]}
            })

            for idx, example in enumerate(examples, 1):
                example_blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [
                        {"type": "text", "text": {"content": f'"{example}"'}, "annotations": {"italic": True}}
                    ]}
                })

        # Create main issue item with toggle
        children.append({
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"{issue[:55]}"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f" — {data['count']} tickets, {customers_count} customers | {trend_str}"}}
                ],
                "children": example_blocks if example_blocks else [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"type": "text", "text": {"content": "No examples available"}}]}
                    }
                ]
            }
        })

    # Top Customers header
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🏢 Top Customers by Volume"}}]}
    })

    # Customers with WoW
    for customer, count in top_customers[:10]:
        lw_count = customers_lw_dict.get(customer, 0)
        if lw_count == 0:
            trend_str = "🆕 New"
        else:
            wow = calculate_evolution(count, lw_count)
            trend_str = f"{get_trend_emoji(wow)} {wow:+.0f}% WoW"

        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{customer}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — {count} tickets | {trend_str}"}}
            ]}
        })

    # Outlier callout
    if top_customers and top_customers[0][1] > 5:
        children.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": f"⚠️ {top_customers[0][0]} has {top_customers[0][1]} tickets — worth a dedicated look"}}],
                "icon": {"emoji": "⚠️"}
            }
        })

    # Churn Risk Assessment
    at_risk_customers = analyze_customer_churn_risk(tickets, tickets_lw, top_customers)

    if at_risk_customers:
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "⚠️ Customer Churn Risk Assessment"}}]}
        })

        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": f"Monitoring {len(at_risk_customers)} customers with elevated risk scores based on volume, trends, priority, and solve rate."}, "annotations": {"italic": True}}
            ]}
        })

        for customer, risk_data in at_risk_customers[:10]:  # Top 10 at-risk customers
            risk_details = []

            # Risk metrics summary
            metrics_text = f"""📊 {risk_data['count']} tickets this week ({risk_data['trend_pct']:+.0f}% WoW)
🔴 {risk_data['high_priority']} high priority | ✅ {risk_data['solve_rate']:.0f}% solve rate
⚠️ Risk Score: {risk_data['risk_score']}/100"""

            risk_details.append({
                "object": "block",
                "type": "quote",
                "quote": {"rich_text": [{"type": "text", "text": {"content": metrics_text}}]}
            })

            # Top 5 issues for this customer
            if risk_data["top_issues"]:
                risk_details.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [
                        {"type": "text", "text": {"content": "🔥 Top Issues:"}, "annotations": {"bold": True}}
                    ]}
                })

                for idx, (issue, count) in enumerate(risk_data["top_issues"][:5], 1):
                    # Find example ticket with full description
                    example_ticket = next(
                        (t for t in risk_data["tickets"] if t.get("subject", "")[:60] == issue),
                        None
                    )

                    issue_text = f"{idx}. {issue} ({count}x)"

                    if example_ticket:
                        description = example_ticket.get("description", "")
                        if description:
                            desc_clean = description.strip()[:300]
                            issue_text += f"\n\n💬 \"{desc_clean}{'...' if len(description) > 300 else ''}\""

                    risk_details.append({
                        "object": "block",
                        "type": "callout",
                        "callout": {
                            "rich_text": [{"type": "text", "text": {"content": issue_text}}],
                            "icon": {"emoji": "🎫"},
                            "color": "gray_background"
                        }
                    })

            # Recommendation based on risk level
            if risk_data["risk_score"] >= 75:
                recommendation = "🔴 CRITICAL: Schedule immediate call with customer success team. Dedicate support resources. Create action plan within 24h."
                rec_color = "red_background"
            elif risk_data["risk_score"] >= 50:
                recommendation = "🟠 HIGH: Proactive outreach recommended. Schedule check-in call this week to address concerns."
                rec_color = "orange_background"
            else:
                recommendation = "🟡 MEDIUM: Monitor closely. Consider sending satisfaction survey to gauge sentiment."
                rec_color = "yellow_background"

            risk_details.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Action: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": recommendation}}
                    ],
                    "icon": {"emoji": "💡"},
                    "color": rec_color
                }
            })

            # Main customer toggle
            children.append({
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"{risk_data['risk_level']} {customer}"}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f" — {risk_data['count']} tickets, Risk: {risk_data['risk_score']}/100"}}
                    ],
                    "children": risk_details
                }
            })

    # Agent Performance header
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "👤 Agent Performance"}}]}
    })

    # Agent stats with WoW
    for agent, stats in agent_stats[:10]:
        assigned = stats["assigned"]
        solved = stats["solved"]
        rate = (solved / assigned * 100) if assigned > 0 else 0

        lw_stats = agents_lw_dict.get(agent, {"assigned": 0})
        lw_assigned = lw_stats.get("assigned", 0) if isinstance(lw_stats, dict) else 0
        if lw_assigned == 0:
            trend_str = "🆕"
        else:
            wow = calculate_evolution(assigned, lw_assigned)
            trend_str = f"{get_trend_emoji(wow)} {wow:+.0f}%"

        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{agent}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — {assigned} assigned, {solved} solved ({rate:.0f}%) | {trend_str} WoW"}}
            ]}
        })

    # Top Questions header
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "❓ Top Questions Raised"}}]}
    })

    # Build lookup for last week questions
    questions_lw_dict = dict(questions_lw) if questions_lw else {}

    # Questions list with count and WoW
    for i, (question, count) in enumerate(questions[:10], 1):
        lw_count = questions_lw_dict.get(question, 0)
        if lw_count == 0:
            trend_str = "🆕 New"
        else:
            wow = calculate_evolution(count, lw_count)
            trend_str = f"{get_trend_emoji(wow)} {wow:+.0f}%"

        children.append({
            "object": "block",
            "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"\"{question}\""}, "annotations": {"italic": True}},
                {"type": "text", "text": {"content": f" — {count}x"}},
                {"type": "text", "text": {"content": f" | {trend_str}"}, "annotations": {"color": "gray"}}
            ]}
        })

    # Update existing page or create new one
    if existing_page_id:
        # Delete existing content and add new
        print("      → Updating existing page...")
        notion_delete_page_content(existing_page_id)
        notion_append_blocks(existing_page_id, children[:100])

        # Get page URL
        response = requests.get(
            f"https://api.notion.com/v1/pages/{existing_page_id}",
            headers=NOTION_HEADERS
        )
        if response.status_code == 200:
            return response.json().get("url")
        return f"https://notion.so/{existing_page_id.replace('-', '')}"
    else:
        # Create new page
        page_data = {
            "parent": {"page_id": os.getenv("NOTION_PAGE_ID")},
            "properties": {
                "title": {"title": [{"text": {"content": page_title}}]}
            },
            "children": children[:100]  # Notion limit
        }

        response = requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json=page_data
        )

        if response.status_code == 200:
            return response.json().get("url")
        else:
            print(f"      ⚠️ Notion page error: {response.status_code}")
            return None


# ============== SLACK ==============

def send_slack_summary(tickets, tickets_lw, category_counts, category_counts_lw,
                        top_issues, top_customers, questions, agent_stats, date_range=None):
    """Send formatted summary to Slack with enhanced granularity."""
    if not SLACK_WEBHOOK_URL or "YOUR" in SLACK_WEBHOOK_URL:
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    total = len(tickets)
    total_lw = len(tickets_lw)
    change = ((total - total_lw) / total_lw * 100) if total_lw > 0 else 0
    trend = "📈" if change > 0 else "📉" if change < 0 else "➡️"

    # Format date range if provided
    period_text = f" ({date_range})" if date_range else ""

    # Get enhanced category breakdown with subcategories
    category_breakdown = get_category_breakdown_with_subcategories(tickets, tickets_lw, top_n=7)

    # Build categories text with WoW and subcategories
    cat_lines = []
    for i, cat_data in enumerate(category_breakdown, 1):
        cat = cat_data["category"]
        count = cat_data["count"]
        pct = cat_data["percentage"]
        wow_str = cat_data["wow"]

        # Determine emoji based on WoW
        if "🆕" in wow_str:
            wow_emoji = "🆕"
            wow_display = wow_str
        else:
            wow_val = float(wow_str.replace("%", "").replace("+", ""))
            wow_emoji = "📈" if wow_val > 0 else "📉" if wow_val < 0 else "➡️"
            wow_display = f"{wow_emoji}{wow_str}"

        cat_lines.append(f"{i}. *{cat}* — {count} ({pct:.0f}%) {wow_display}")

        # Add top 3 subcategories (indented)
        for subcat in cat_data["subcategories"]:
            sub_name = subcat["name"]
            sub_count = subcat["count"]
            sub_pct = subcat["percentage"]

            # Add example if available
            example_text = ""
            if subcat["examples"]:
                example = subcat["examples"][0][:45]
                example_text = f" _\"{example}...\"_"

            cat_lines.append(f"   • {sub_name} — {sub_count} ({sub_pct:.0f}%){example_text}")

    categories_text = "\n".join(cat_lines)

    # Booking.com insight
    booking_total = sum(cat_data["count"] for cat_data in category_breakdown if "Booking" in cat_data["category"])
    booking_pct = booking_total / total * 100 if total > 0 else 0

    # Build enhanced issues text with customers and newness
    issue_lines = []
    for issue, data in top_issues[:5]:
        issue_text = issue[:50]
        count = data['count']
        is_new = data.get('IsNew', False)
        customers = data.get('AffectedCustomers', [])
        examples = data.get('Examples', [])

        # Build the line
        new_badge = "🆕 " if is_new else ""
        line = f"• {new_badge}*{issue_text}...* ({count} tickets)"

        # Add customers if available
        if customers:
            customer_str = ", ".join(customers[:3])
            if len(customers) > 3:
                customer_str += f" +{len(customers)-3} more"
            line += f"\n  _Customers: {customer_str}_"

        # Add example if available
        if examples and len(examples) > 1:
            line += f"\n  _Ex: \"{examples[0][:45]}...\"_"

        issue_lines.append(line)

    issues_text = "\n\n".join(issue_lines)

    # Build customers text
    customer_lines = []
    for customer, count in top_customers[:5]:
        customer_lines.append(f"• {customer[:35]} — {count} tickets")
    customers_text = "\n".join(customer_lines)

    # Build agent text
    agent_lines = []
    for agent, stats in agent_stats[:5]:
        rate = (stats["solved"] / stats["assigned"] * 100) if stats["assigned"] > 0 else 0
        agent_lines.append(f"• {agent[:25]} — {stats['assigned']} assigned, {stats['solved']} solved ({rate:.0f}%)")
    agents_text = "\n".join(agent_lines)

    # Build questions text
    question_lines = []
    for q, count in questions[:5]:
        question_lines.append(f"• _{q[:55]}_")
    questions_text = "\n".join(question_lines)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"📊 Zendesk Weekly Insights{period_text}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{total} tickets* this week {trend} {change:+.0f}% vs last week ({total_lw})"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*🗂️ Top Categories (with WoW)*\n{categories_text}\n\n_💡 Booking.com = ~{booking_pct:.0f}% of all tickets_"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*🔥 Top Issues*\n{issues_text}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*🏢 Top Customers*\n{customers_text}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*👤 Agent Performance*\n{agents_text}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*❓ Top Questions*\n{questions_text}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "📄 <https://www.notion.so/smilycom/Insights-from-CS-Modjo-Automated-3185d6a20ddc8084ada8f279005803b8|View Full Report in Notion>"}},
    ]

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json={"blocks": blocks})
        return response.status_code == 200
    except:
        return False


def create_weekly_insights_entry(date_str, zendesk_data, modjo_data, detailed_content):
    """Create or update a weekly insights entry in the database with metrics and detailed content."""

    # Check if entry for this week already exists
    existing_entry = None
    try:
        response = requests.post(
            f"https://api.notion.com/v1/databases/{NOTION_WEEKLY_INSIGHTS_DB}/query",
            headers=NOTION_HEADERS,
            json={
                "filter": {
                    "property": "Week",
                    "date": {"equals": date_str}
                }
            }
        )
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                existing_entry = results[0]["id"]
    except:
        pass

    # Extract Zendesk metrics
    z = zendesk_data
    tickets = z.get("tickets", 0)
    tickets_lw = z.get("tickets_lw", 0)
    tickets_wow = ((tickets - tickets_lw) / tickets_lw) if tickets_lw > 0 else 0
    high_priority = z.get("high_priority", 0)
    top_category = z.get("top_category", "Other")
    top_category_pct = z.get("top_category_pct", 0)
    solved_rate = z.get("solved_rate", 0)
    questions_count = z.get("questions_count", 0)
    at_risk_count = z.get("at_risk_count", 0)

    # Extract Modjo metrics
    m = modjo_data
    calls = m.get("calls", 0)
    calls_lw = m.get("calls_lw", 0)
    calls_wow = ((calls - calls_lw) / calls_lw) if calls_lw > 0 else 0
    sales_calls = m.get("sales_calls", 0)
    onboarding_calls = m.get("onboarding_calls", 0)
    pitch_score = m.get("pitch_score", 0)
    top_topic = m.get("top_topic", "Channel Sync")
    competitors_mentioned = m.get("competitors_mentioned", 0)
    top_competitor = m.get("top_competitor", "None")
    objections_count = m.get("objections_count", 0)
    pain_points = m.get("pain_points", 0)
    feature_requests = m.get("feature_requests", 0)

    # Determine health status
    if tickets_wow <= -0.1 and calls_wow >= 0:
        status = "🟢 Healthy"
    elif tickets_wow >= 0.2 or high_priority >= 30:
        status = "🔴 Critical"
    else:
        status = "🟡 Warning"

    # Build properties
    properties = {
        "Report": {"title": [{"text": {"content": f"Week of {date_str}"}}]},
        "Week": {"date": {"start": date_str}},
        "Status": {"select": {"name": status}},

        # Zendesk
        "Tickets": {"number": tickets},
        "Tickets WoW %": {"number": round(tickets_wow, 2)},
        "High Priority": {"number": high_priority},
        "Top Category": {"select": {"name": top_category[:100]}},
        "Top Category %": {"number": round(top_category_pct / 100, 2)},
        "Solved Rate %": {"number": round(solved_rate / 100, 2)},
        "Questions Count": {"number": questions_count},
        "At-Risk Accounts": {"number": at_risk_count},

        # Modjo
        "Calls": {"number": calls},
        "Calls WoW %": {"number": round(calls_wow, 2)},
        "Sales Calls": {"number": sales_calls},
        "Onboarding Calls": {"number": onboarding_calls},
        "Pitch Score": {"number": round(pitch_score)},
        "Top Topic": {"select": {"name": top_topic[:100]}},
        "Competitors Mentioned": {"number": competitors_mentioned},
        "Top Competitor": {"select": {"name": top_competitor[:100] if top_competitor else "None"}},
        "Objections Count": {"number": objections_count},

        # Combined
        "Pain Points": {"number": pain_points},
        "Feature Requests": {"number": feature_requests},
    }

    if existing_entry:
        # Update existing entry
        response = requests.patch(
            f"https://api.notion.com/v1/pages/{existing_entry}",
            headers=NOTION_HEADERS,
            json={"properties": properties}
        )
        page_id = existing_entry

        # Clear existing content
        notion_delete_page_content(existing_entry)
    else:
        # Create new entry
        response = requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json={
                "parent": {"database_id": NOTION_WEEKLY_INSIGHTS_DB},
                "properties": properties
            }
        )
        if response.status_code == 200:
            page_id = response.json()["id"]
        else:
            print(f"      Error creating entry: {response.status_code}")
            return None

    # Add detailed content to the page
    if detailed_content and page_id:
        # Split content into chunks of 100 blocks (Notion limit)
        for i in range(0, len(detailed_content), 100):
            chunk = detailed_content[i:i+100]
            notion_append_blocks(page_id, chunk)

    # Get URL
    try:
        resp = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS
        )
        if resp.status_code == 200:
            return resp.json().get("url")
    except:
        pass

    return f"https://notion.so/{page_id.replace('-', '')}"


def build_weekly_insights_content(date_str, zendesk_data, modjo_data, category_deep_dive, trends):
    """Build the detailed content blocks for the weekly insights entry."""
    children = []

    # Header
    children.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {"content": f"📊 Weekly Insights — {date_str}"}}]}
    })

    # Overview callout
    z = zendesk_data
    m = modjo_data
    tickets_wow = ((z['tickets'] - z['tickets_lw']) / z['tickets_lw'] * 100) if z['tickets_lw'] > 0 else 0
    calls_wow = ((m['calls'] - m['calls_lw']) / m['calls_lw'] * 100) if m['calls_lw'] > 0 else 0

    children.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": f"🎫 {z['tickets']} tickets ({get_trend_emoji(tickets_wow)} {tickets_wow:+.0f}% WoW) • 📞 {m['calls']} calls ({get_trend_emoji(calls_wow)} {calls_wow:+.0f}% WoW)"}}],
            "icon": {"emoji": "📈"},
            "color": "blue_background"
        }
    })

    # ========== ZENDESK SECTION ==========
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "🎫 Zendesk Support Insights"}}]}
    })

    # Top Categories
    children.append({
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🗂️ Top Categories"}}]}
    })

    for cat, count in z.get("categories", [])[:8]:
        pct = count / z['tickets'] * 100 if z['tickets'] > 0 else 0
        lw_count = z.get("categories_lw", {}).get(cat, 0)
        wow = calculate_evolution(count, lw_count)
        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{cat}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — {count} ({pct:.0f}%) {get_trend_emoji(wow)} {wow:+.0f}%"}}
            ]}
        })

    # Category Deep Dive
    if category_deep_dive:
        children.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🔍 Category Deep Dive"}}]}
        })

        for cat, data in category_deep_dive.items():
            sub_children = []

            # Verdict
            verdict_color = "yellow_background" if data['pattern_type'] == "similar" else "orange_background" if data['pattern_type'] == "mixed" else "blue_background"
            sub_children.append({
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": data['verdict']}}],
                    "icon": {"emoji": "🎯"},
                    "color": verdict_color
                }
            })

            # Sub-issues with occurrences
            for issue_type, all_tix, grouped_tix in data.get('grouped_issues', [])[:4]:
                pct = len(all_tix) / data['total'] * 100
                issue_items = []

                for group in grouped_tix[:3]:
                    t = group['tickets'][0]
                    count = group['count']
                    badge = f"🔁 {count}x" if count > 1 else "1️⃣"

                    issue_items.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {"rich_text": [
                            {"type": "text", "text": {"content": f"{badge} "}, "annotations": {"bold": True}},
                            {"type": "text", "text": {"content": t['subject'][:50], "link": {"url": t['url']}}},
                            {"type": "text", "text": {"content": f" • {t['org']}"}, "annotations": {"color": "gray"}}
                        ]}
                    })

                sub_children.append({
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [
                            {"type": "text", "text": {"content": f"{issue_type}"}, "annotations": {"bold": True}},
                            {"type": "text", "text": {"content": f" — {len(all_tix)} tickets ({pct:.0f}%)"}}
                        ],
                        "children": issue_items if issue_items else [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "No details"}}]}}]
                    }
                })

            pattern_emoji = "⚠️" if data['pattern_type'] == "similar" else "🔶" if data['pattern_type'] == "mixed" else "ℹ️"
            children.append({
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"{pattern_emoji} {cat}"}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f" — {data['total']} tickets"}}
                    ],
                    "children": sub_children if sub_children else [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "No breakdown available"}}]}}]
                }
            })

    # Top Questions
    if z.get("questions"):
        children.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "❓ Top Questions"}}]}
        })
        for q, count in z.get("questions", [])[:8]:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [
                    {"type": "text", "text": {"content": f'"{q}"'}, "annotations": {"italic": True}},
                    {"type": "text", "text": {"content": f" — {count}x"}}
                ]}
            })

    # ========== MODJO SECTION ==========
    children.append({
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": "📞 Modjo Call Insights"}}]}
    })

    # Call Types
    children.append({
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {"content": "📋 Call Types"}}]}
    })

    for call_type, count in m.get("call_types", [])[:5]:
        pct = count / m['calls'] * 100 if m['calls'] > 0 else 0
        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [
                {"type": "text", "text": {"content": f"{call_type}"}, "annotations": {"bold": True}},
                {"type": "text", "text": {"content": f" — {count} ({pct:.0f}%)"}}
            ]}
        })

    # Topics
    if m.get("topics"):
        children.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🏷️ Top Topics"}}]}
        })
        for topic, num_calls, mentions in m.get("topics", [])[:6]:
            pct = num_calls / m['calls'] * 100 if m['calls'] > 0 else 0
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [
                    {"type": "text", "text": {"content": f"{topic}"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f" — {num_calls} calls ({pct:.0f}%)"}}
                ]}
            })

    # Sales Focus
    if m.get("pitch_score", 0) > 0:
        children.append({
            "object": "block",
            "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": "🎯 Sales Focus"}}]}
        })

        score = m.get("pitch_score", 0)
        score_emoji = "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"
        children.append({
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": f"Pitch Score: {score:.0f}/100 {score_emoji}"}}],
                "icon": {"emoji": "📊"},
                "color": "green_background" if score >= 70 else "yellow_background" if score >= 50 else "red_background"
            }
        })

        # Competitors
        if m.get("competitors"):
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [
                    {"type": "text", "text": {"content": "🏁 Competitors: "}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": ", ".join([f"{c} ({n})" for c, n in m.get("competitors", [])[:5]])}}
                ]}
            })

        # Objections
        if m.get("objections"):
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [
                    {"type": "text", "text": {"content": "🛡️ Top Objections: "}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": ", ".join([f"{o} ({n})" for o, n in m.get("objections", [])[:5]])}}
                ]}
            })

    return children


def send_slack_modjo_summary(trends, notion_url, date_range=None):
    """Send Modjo weekly summary to Slack."""
    if not SLACK_WEBHOOK_URL or "YOUR" in SLACK_WEBHOOK_URL:
        return False

    today = datetime.now().strftime("%Y-%m-%d")

    # Format date range if provided
    period_text = f" ({date_range})" if date_range else ""

    # Extract data from trends
    total_tw = trends["total_calls"]["this_week"]
    total_lw = trends["total_calls"]["last_week"]
    change = calculate_evolution(total_tw, total_lw)
    trend_emoji = get_trend_emoji(change)

    # Call types
    call_types = trends["call_types"]["this_week"]
    call_types_lw = trends["call_types"]["last_week"]
    type_lines = []
    for call_type, count in call_types.most_common(5):
        pct = count / total_tw * 100 if total_tw > 0 else 0
        lw_count = call_types_lw.get(call_type, 0)
        wow = calculate_evolution(count, lw_count)
        type_lines.append(f"• *{call_type}* — {count} ({pct:.0f}%) {get_trend_emoji(wow)}{wow:+.0f}%")
    types_text = "\n".join(type_lines)

    # Topics
    topics = trends["topics"]["this_week"][:5]
    topic_lines = []
    for topic, num_calls, mentions in topics:
        pct = num_calls / total_tw * 100 if total_tw > 0 else 0
        topic_lines.append(f"• *{topic}* — {num_calls} calls ({pct:.0f}%)")
    topics_text = "\n".join(topic_lines)

    # Agents by team
    agents = trends["agents"]["this_week"]
    agent_lines = []
    for team in ["Sales", "Account Management", "Onboarding"]:
        team_agents = [(a, d) for a, d in agents if d.get("team") == team]
        if team_agents:
            agent_lines.append(f"*{team}:*")
            for agent, data in team_agents[:2]:
                calls = data["calls"]
                accounts = len(data["accounts"])
                agent_lines.append(f"  • {agent}: {calls} calls, {accounts} accounts")
    agents_text = "\n".join(agent_lines) if agent_lines else "No agent data"

    # Top accounts
    accounts = trends["top_accounts"][:5]
    account_lines = [f"• {acc} — {count} calls" for acc, count in accounts]
    accounts_text = "\n".join(account_lines)

    # Sales insights
    sales = trends.get("sales", {})
    sales_text = ""
    if sales.get("total_calls", 0) > 0:
        pitch_scores = sales.get("pitch_scores", [])
        if pitch_scores:
            avg_score = sum(p["score"] for p in pitch_scores) / len(pitch_scores)
            score_emoji = "🟢" if avg_score >= 70 else "🟡" if avg_score >= 50 else "🔴"
            sales_text = f"*Pitch Score:* {avg_score:.0f}/100 {score_emoji}\n"

        # Competitors
        competitors = sales.get("competitors_mentioned", [])
        if competitors:
            comp_counts = {}
            for c in competitors:
                comp_counts[c["competitor"]] = comp_counts.get(c["competitor"], 0) + 1
            top_comps = sorted(comp_counts.items(), key=lambda x: -x[1])[:3]
            comp_str = ", ".join([f"{c} ({n})" for c, n in top_comps])
            sales_text += f"*Competitors mentioned:* {comp_str}\n"

        # Objections
        objections = sales.get("objection_responses", [])
        if objections:
            obj_counts = {}
            for o in objections:
                obj_counts[o["objection_type"]] = obj_counts.get(o["objection_type"], 0) + 1
            top_objs = sorted(obj_counts.items(), key=lambda x: -x[1])[:3]
            obj_str = ", ".join([f"{o} ({n})" for o, n in top_objs])
            sales_text += f"*Top objections:* {obj_str}"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"📞 Modjo Weekly Call Insights{period_text}", "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{total_tw} calls* this week {trend_emoji} {change:+.0f}% vs last week ({total_lw})"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*📋 Call Types*\n{types_text}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*🏷️ Top Topics*\n{topics_text}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*👤 Agent Performance*\n{agents_text}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*🏢 Most Active Accounts*\n{accounts_text}"}},
    ]

    # Add sales section if available
    if sales_text:
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*🎯 Sales Insights*\n{sales_text}"}})

    # Add link to Notion
    blocks.append({"type": "divider"})
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"📄 <{notion_url}|View Full Modjo Report in Notion>"}})

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json={"blocks": blocks})
        return response.status_code == 200
    except:
        return False


def send_slack_notification(counts, modjo_count, zendesk_count, high_priority):
    """Send summary to Slack (legacy)."""
    if not SLACK_WEBHOOK_URL or "YOUR" in SLACK_WEBHOOK_URL:
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    top_issues = sorted(counts.items(), key=lambda x: -x[1])[:5]
    issues_text = "\n".join([f"• *{cat}*: {count}" for cat, count in top_issues])

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"📊 Weekly Product Insights - {today}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Data:* {modjo_count} calls, {zendesk_count} tickets ({high_priority} high priority)"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*🔥 Top Issues:*\n{issues_text}"}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "📄 <https://www.notion.so/smilycom/Insights-from-CS-Modjo-Automated-3185d6a20ddc8084ada8f279005803b8|View Full Report in Notion>"}},
    ]

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json={"blocks": blocks})
        return response.status_code == 200
    except:
        return False


# ============== MAIN ==============

def get_last_week_dates():
    """Get last week's Monday to Sunday dates."""
    today = datetime.now()
    # Get last Sunday (end of last week)
    days_since_monday = today.weekday()  # Monday is 0, Sunday is 6
    last_sunday = today - timedelta(days=days_since_monday + 1)
    # Get last Monday (start of last week)
    last_monday = last_sunday - timedelta(days=6)

    return last_monday.strftime("%Y-%m-%d"), last_sunday.strftime("%Y-%m-%d")


def main():
    print("Starting Weekly Product Insights Analysis (Enhanced)")
    print("   Data sources: Zendesk API + Modjo API")
    print()

    # Calculate last week's date range (Monday to Sunday)
    last_week_start, last_week_end = get_last_week_dates()
    print(f"   Analyzing last week: {last_week_start} to {last_week_end}")
    print()

    # Use last week's end date for "today" in reports
    today = last_week_end

    # Calculate week before last (for WoW comparison)
    week_before_start = (datetime.strptime(last_week_start, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    week_before_end = (datetime.strptime(last_week_start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")

    # Fetch Zendesk data
    print("[1/10] Connecting to Zendesk API...")
    org_lookup = fetch_zendesk_organizations()
    agent_lookup = fetch_zendesk_users()

    # We'll enrich agent lookup after fetching tickets

    print("[2/9] Fetching Zendesk tickets (last week, week before, last month)...")
    # Last week (main analysis period)
    print(f"      Fetching tickets from last week...")
    tickets = fetch_zendesk_tickets(start_date=last_week_start, end_date=last_week_end)
    tickets = enrich_tickets_with_org_names(tickets, org_lookup)
    high_priority_count = sum(1 for t in tickets if is_high_priority(t))

    # Week before last (for WoW comparison)
    print(f"      Fetching tickets from week before...")
    tickets_last_week = fetch_zendesk_tickets(start_date=week_before_start, end_date=week_before_end)
    tickets_last_week = enrich_tickets_with_org_names(tickets_last_week, org_lookup)

    # Last month (for MoM comparison)
    tickets_30d = fetch_zendesk_tickets(days=30)
    tickets_30d = enrich_tickets_with_org_names(tickets_30d, org_lookup)

    print(f"      → Last week: {len(tickets)} tickets ({high_priority_count} high priority)")
    print(f"      → Week before: {len(tickets_last_week)} tickets")
    print(f"      → Last 30 days: {len(tickets_30d)} tickets")

    # Enrich agent lookup with any missing assignees
    agent_lookup = enrich_agent_lookup(tickets + tickets_last_week, agent_lookup)

    # Fetch Modjo data
    print("[3/9] Fetching Modjo calls...")
    modjo_calls = fetch_modjo_calls(use_api=True, start_date=last_week_start, end_date=last_week_end)
    print(f"      -> {len(modjo_calls)} calls")

    # Analyze this week
    print("[4/9] Analyzing this week's data...")
    zendesk_themes = analyze_zendesk_tickets(tickets)
    modjo_themes = analyze_modjo_calls(modjo_calls)
    merged_themes = merge_themes(zendesk_themes, modjo_themes)
    counts = count_by_category(zendesk_themes, modjo_themes)
    print(f"      → {sum(len(t) for t in merged_themes.values())} unique themes identified")

    # Detailed category analysis
    detailed_counts = Counter()
    for ticket in tickets:
        subject = ticket.get("subject", "")
        desc = ticket.get("description", "")[:200] if ticket.get("description") else ""
        cat = categorize_detailed(f"{subject} {desc}")
        detailed_counts[cat] += 1

    sorted_detailed_cats = sorted(detailed_counts.items(), key=lambda x: -x[1])

    # Top customers by volume
    top_customers = get_customer_volumes(tickets)

    # Extract readable questions
    question_counts, question_customers = extract_readable_questions(tickets)
    sorted_questions = sorted(question_counts.items(), key=lambda x: -x[1])

    # Top issues with customer info (with last week comparison)
    top_issues_detailed = get_top_issues(tickets, org_lookup, limit=15, tickets_lw=tickets_last_week)

    # Agent stats
    agent_stats = get_agent_stats_with_names(tickets, agent_lookup)

    # Analyze last week (for WoW)
    zendesk_themes_lw = analyze_zendesk_tickets(tickets_last_week)
    counts_lw = Counter()
    for cat, themes in zendesk_themes_lw.items():
        for theme, data in themes.items():
            counts_lw[cat] += data["count"]

    # Detailed counts for last week
    detailed_counts_lw = Counter()
    for ticket in tickets_last_week:
        subject = ticket.get("subject", "")
        desc = ticket.get("description", "")[:200] if ticket.get("description") else ""
        cat = categorize_detailed(f"{subject} {desc}")
        detailed_counts_lw[cat] += 1

    # Analyze last month (for MoM average)
    zendesk_themes_30d = analyze_zendesk_tickets(tickets_30d)
    counts_30d = Counter()
    for cat, themes in zendesk_themes_30d.items():
        for theme, data in themes.items():
            counts_30d[cat] += data["count"]

    # Calculate metrics
    this_week_metrics = calculate_solve_metrics(tickets)
    last_week_metrics = calculate_solve_metrics(tickets_last_week)

    # Last week data for WoW comparison
    sorted_detailed_cats_lw = sorted(detailed_counts_lw.items(), key=lambda x: -x[1])
    top_customers_lw = get_customer_volumes(tickets_last_week)
    top_issues_lw = get_top_issues(tickets_last_week, org_lookup, limit=50)
    agent_stats_lw = get_agent_stats_with_names(tickets_last_week, agent_lookup)

    # Extract questions for last week (for WoW comparison)
    question_counts_lw, question_customers_lw = extract_readable_questions(tickets_last_week)
    sorted_questions_lw = sorted(question_counts_lw.items(), key=lambda x: -x[1])

    # Generate and print summary report
    print()
    summary = generate_summary_report(
        tickets, tickets_last_week, tickets_30d,
        sorted_detailed_cats, sorted_detailed_cats_lw,
        top_issues_detailed, top_issues_lw,
        top_customers, top_customers_lw,
        sorted_questions,
        agent_stats, agent_stats_lw
    )
    print(summary)
    print()

    # Write to Notion - Dashboard
    print("[5/9] Writing dashboard to Notion...")
    if notion_add_dashboard(today, this_week_metrics, last_week_metrics):
        print("      → Dashboard metrics added")

    # Write to Notion - Top Categories (using detailed categories)
    print("[6/9] Writing top categories to Notion...")
    total_tickets = len(tickets)

    for rank, (category, count) in enumerate(sorted_detailed_cats[:10], 1):
        pct_of_total = (count / total_tickets * 100) if total_tickets > 0 else 0
        last_week_count = detailed_counts_lw.get(category, 0)
        # Calculate monthly average from 30d data
        detailed_counts_30d = Counter()
        for ticket in tickets_30d:
            subject = ticket.get("subject", "")
            desc = ticket.get("description", "")[:200] if ticket.get("description") else ""
            cat = categorize_detailed(f"{subject} {desc}")
            detailed_counts_30d[cat] += 1
        last_month_avg = detailed_counts_30d.get(category, 0) / 4.3

        notion_add_category(
            today, category, count, pct_of_total, rank,
            last_week_count, last_month_avg
        )

    print(f"      → Added {len(sorted_detailed_cats[:10])} categories with evolution")

    # Write to Notion - Top Issues
    print("[7/9] Writing top issues to Notion...")
    top_issues_lw = dict(get_top_issues(tickets_last_week, org_lookup, limit=50))

    for rank, (issue, data) in enumerate(top_issues_detailed[:10], 1):
        last_week_count = top_issues_lw.get(issue, {}).get("count", 0)
        notion_add_issue(today, issue, data["count"], data["AffectedCustomers"], rank, last_week_count)

    print(f"      → Added {min(len(top_issues_detailed), 10)} issues with trends")

    # Write to Notion - Top Questions (using readable questions)
    print("[8/9] Writing top questions to Notion...")

    for rank, (question, count) in enumerate(sorted_questions[:10], 1):
        customers = question_customers.get(question, set())
        # Determine category from question text
        cat = categorize_detailed(question)
        notion_add_question(
            today, question, count, customers,
            cat, rank, None
        )

    print(f"      → Added {min(len(sorted_questions), 10)} questions")

    # Write legacy metrics (for backwards compatibility)
    if notion_add_metrics(today, len(modjo_calls), len(tickets), high_priority_count, counts):
        print("      → Legacy metrics added")

    # Write detailed analysis
    print("[8b/9] Writing detailed analysis to Notion...")
    entry_count = 0

    for category, total_count in sorted_detailed_cats:
        if category not in merged_themes:
            continue

        sorted_themes = sorted(merged_themes[category].items(), key=lambda x: -x[1]["count"])

        for theme_name, data in sorted_themes[:10]:
            count = data["count"]
            high_p = data["high_priority_count"]

            # Priority: P0=Critical, P1=High, P2=Medium, P3=Low
            if high_p >= 3 or count >= 20:
                priority = "P0"
            elif high_p >= 1 or count >= 10:
                priority = "P1"
            elif count >= 5:
                priority = "P2"
            else:
                priority = "P3"

            details = f"{count} occurrences ({high_p} high priority)"

            if notion_add_analysis(
                date_str=today,
                item=theme_name,
                section="Obstacles",
                priority=priority,
                category=category,
                details=details,
                status="Active",
                occurrences=count,
                accounts=data["accounts"],
                examples=data["examples"]
            ):
                entry_count += 1

    print(f"      → Added {entry_count} themed entries with examples")

    # Detect at-risk accounts
    print("[8c/9] Detecting at-risk accounts...")
    churn_keywords = ["résiliation", "resiliation", "cancel", "churn", "terminate", "fin abonnement", "annuler"]
    at_risk = []

    for ticket in tickets:
        subject = (ticket.get("subject") or "").lower()
        if any(kw in subject for kw in churn_keywords):
            org_name = ticket.get("organization_name") or f"Ticket #{ticket.get('id')}"
            at_risk.append({
                "account": org_name,
                "signal": ticket.get("subject"),
                "ticket_id": ticket.get("id"),
            })

    for item in at_risk[:10]:
        notion_add_atrisk(
            today,
            item["account"],
            "Critical",
            item["signal"],
            "Review account and reach out",
            "Open"
        )
    print(f"      → Added {min(len(at_risk), 10)} at-risk accounts")

    # Create Notion summary page
    print("[9/10] Creating Notion summary page...")

    # Prepare date range string
    date_range_str = f"{last_week_start} to {last_week_end}"

    # Generate category deep dive analysis
    category_deep_dive = analyze_category_deep_dive(tickets, sorted_detailed_cats)

    summary_url = notion_create_summary_page(
        today, tickets, tickets_last_week,
        sorted_detailed_cats, sorted_detailed_cats_lw,
        top_issues_detailed, top_issues_lw,
        top_customers, top_customers_lw,
        sorted_questions,
        agent_stats, agent_stats_lw,
        metrics=this_week_metrics,
        category_deep_dive=category_deep_dive,
        questions_lw=sorted_questions_lw,
        date_range=date_range_str
    )

    if summary_url:
        print(f"      → Summary page created")
        # Update Recent Reports section to show this at the top
        notion_update_recent_reports_section(
            summary_url,
            f"Zendesk Weekly Summary — {date_range_str}",
            "Zendesk",
            date_str=today
        )
    else:
        print("      → Summary page failed")

    # Slack with full summary
    print("[10/10] Sending Slack summary...")
    if send_slack_summary(
        tickets, tickets_last_week,
        sorted_detailed_cats, sorted_detailed_cats_lw,
        top_issues_detailed,
        top_customers, sorted_questions,
        agent_stats,
        date_range=date_range_str
    ):
        print("      → Slack summary sent")
    else:
        print("      → Skipped (not configured)")

    # Run dedicated Modjo analysis
    print("\n[11/11] Running Modjo call analysis...")
    modjo_result = run_modjo_analysis(week_start=last_week_start, week_end=last_week_end)
    modjo_url, modjo_trends, modjo_insights, modjo_calls_tw, modjo_calls_lw = modjo_result

    # Create Weekly Insights database entry
    print("\n[12/12] Creating Weekly Insights database entry...")

    # Prepare Zendesk data
    solved_count = sum(1 for t in tickets if t.get("status") == "solved")
    solved_rate = (solved_count / len(tickets) * 100) if tickets else 0

    zendesk_data = {
        "tickets": len(tickets),
        "tickets_lw": len(tickets_last_week),
        "high_priority": sum(1 for t in tickets if t.get("priority") in ["high", "urgent"]),
        "top_category": sorted_detailed_cats[0][0] if sorted_detailed_cats else "Other",
        "top_category_pct": (sorted_detailed_cats[0][1] / len(tickets) * 100) if sorted_detailed_cats and tickets else 0,
        "solved_rate": solved_rate,
        "questions_count": len(sorted_questions),
        "at_risk_count": len(at_risk),
        "categories": sorted_detailed_cats[:10],
        "categories_lw": dict(sorted_detailed_cats_lw),
        "questions": sorted_questions[:10],
    }

    # Prepare Modjo data
    sales_data = modjo_trends.get("sales", {})
    pitch_scores = sales_data.get("pitch_scores", [])
    avg_pitch = sum(p["score"] for p in pitch_scores) / len(pitch_scores) if pitch_scores else 0

    competitors = sales_data.get("competitors_mentioned", [])
    comp_counts = {}
    for c in competitors:
        comp_counts[c["competitor"]] = comp_counts.get(c["competitor"], 0) + 1
    top_competitors = sorted(comp_counts.items(), key=lambda x: -x[1])

    objections = sales_data.get("objection_responses", [])
    obj_counts = {}
    for o in objections:
        obj_counts[o["objection_type"]] = obj_counts.get(o["objection_type"], 0) + 1
    top_objections = sorted(obj_counts.items(), key=lambda x: -x[1])

    call_types = modjo_trends.get("call_types", {}).get("this_week", Counter())
    topics = modjo_trends.get("topics", {}).get("this_week", [])

    modjo_data = {
        "calls": modjo_trends["total_calls"]["this_week"],
        "calls_lw": modjo_trends["total_calls"]["last_week"],
        "sales_calls": call_types.get("Sales / Demo", 0),
        "onboarding_calls": call_types.get("Onboarding", 0),
        "pitch_score": avg_pitch,
        "top_topic": topics[0][0] if topics else "Channel Sync",
        "competitors_mentioned": len(competitors),
        "top_competitor": top_competitors[0][0] if top_competitors else "None",
        "objections_count": len(objections),
        "pain_points": len(modjo_insights.get("pain_points", [])),
        "feature_requests": len(modjo_insights.get("feature_requests", [])),
        "call_types": list(call_types.most_common(5)),
        "topics": topics[:8],
        "competitors": top_competitors[:5],
        "objections": top_objections[:5],
    }

    # Build detailed content
    detailed_content = build_weekly_insights_content(
        today, zendesk_data, modjo_data, category_deep_dive, modjo_trends
    )

    # Create the database entry
    weekly_url = create_weekly_insights_entry(today, zendesk_data, modjo_data, detailed_content)

    if weekly_url:
        print(f"      → Weekly Insights entry created: {weekly_url}")
    else:
        print("      → Weekly Insights entry failed")

    print()
    print("=" * 60)
    print(f"Analysis complete ({today})")
    print(f"   {entry_count} detailed entries with occurrences & examples")
    if summary_url:
        print(f"   Zendesk Summary: {summary_url}")
    if modjo_url:
        print(f"   Modjo Insights: {modjo_url}")
    if weekly_url:
        print(f"   📊 Weekly Insights DB: {weekly_url}")
    print("   View: https://www.notion.so/smilycom/Insights-from-CS-Modjo-Automated-3185d6a20ddc8084ada8f279005803b8")
    print("=" * 60)


if __name__ == "__main__":
    main()
