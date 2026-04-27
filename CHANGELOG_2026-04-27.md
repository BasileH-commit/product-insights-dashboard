# Product Insights Dashboard - Changelog
## April 27, 2026

### 🎉 Major Features

#### 📅 Month-over-Month Filtering
**What's New:**
- Toggle between **Week** and **Month** views in the sidebar
- Month view shows last 4 calendar months (e.g., April 2026, March 2026, February 2026, January 2026)
- Uses actual calendar boundaries (Jan 1-31, Feb 1-28/29, etc.)
- Proper month-over-month comparison with MoM growth percentages
- Handles edge cases like January → December year wrapping
- Shows warning when viewing incomplete current month

**Why It Matters:**
- Better for monthly reporting and business reviews
- More consistent periods (30/31 days vs rolling periods)
- Easier to align with business metrics and goals

**Where:** Sidebar → Time Period section

---

#### 💡 AI-Powered Actionable Insights
**What's New:**
Intelligent analysis engine that automatically identifies opportunities and recommends actions based on ticket patterns:

**Detects:**
- High-volume categories (>15% of tickets)
- Fast-growing issues (>50% growth)
- Recurring patterns (sync, documents, blocked listings, etc.)
- Customer concentration risks
- Success stories (declining ticket categories)
- Self-service opportunities

**Provides:**
- Severity rating (🔴 High / 🟡 Medium / 🟢 Low)
- Trend direction (📈 Growing / ➡️ Stable / 📉 Declining)
- Data-backed insights (ticket counts, percentages, growth rates)
- Specific action recommendations
- Potential impact statements

**Example Insights:**
```
🔴 Booking.com Onboarding 📈
40 tickets (17.2%) about connecting new listings. +33% growth
💡 Action: Review onboarding flow UX. Check for blockers. Add video tutorial.
🎯 Impact: Could reduce 30-40% of support tickets if self-service improved.

🟡 Payment Onboarding UX ➡️
12 tickets about rejected documents
💡 Action: Improve upload UX: show examples, add validation before submission
🎯 Impact: Smoother payment onboarding = faster time-to-revenue

🟢 Success Story 📉
✅ Notifications/Automations decreased -36% (11 → 7 tickets)
💡 Action: Document what changed. Replicate for other categories.
🎯 Impact: Learn from successes to improve other problem areas.
```

**Why It Matters:**
- Proactively identifies what to fix/improve
- Prioritizes efforts based on impact
- Learns from both problems AND successes
- Saves time in analysis and reporting

**Where:** Categories tab & Top Issues tab (after the tables)

---

#### 🔬 Deep Dive Analysis: Real Issues, Apps & Solutions
**What's New:**
On-demand analysis that digs into actual ticket content and CS team responses:

**Analyzes:**
- Up to 30 solved tickets (prioritizes urgent/high priority)
- Fetches ticket comments to see CS team solutions
- Identifies which app/platform has the issue
- Extracts specific issue types
- Finds patterns in solutions provided

**App Detection:**
- Booking.com, Airbnb, Vrbo/Abritel
- SmilyPay, Website/Widget, Notifications, Pricing Engine

**Issue Type Classification:**
- Sync Issue, Connection/Onboarding, Listing Blocked
- Calendar/Availability, Photo Upload, Document Rejection
- Pricing Issue, Reservation Issue

**Solution Patterns:**
- Reconnect listing/account
- Refresh connection/sync
- Updated configuration/settings
- Escalate to channel partner
- Re-upload required documents
- Fix listing mapping, Remove duplicates
- Fix permissions, Technical/API fix
- Manual CS intervention

**Output:**
```
📱 Booking.com (15 issues)
Top Issue Type: Sync Issue (8 occurrences)
Solution Types: 4 different solutions | 20% manual intervention
Most Common Solution: Refresh connection/sync

🎯 Opportunity: Implement auto-retry logic and better error messages

Real Examples:
1. Sync Issue
   - Subject: Synchronisation calendrier Booking.com bloquée
   - Customer: Rock in Share
   - Solution: Refresh connection/sync
```

**Why It Matters:**
- Understand root causes, not just symptoms
- Identify automation opportunities (high manual intervention = self-service opportunity)
- See what solutions actually work
- Build better self-service features
- Train CS team with proven solutions

**Where:** Categories tab & Top Issues tab → "🔬 Deep Dive" expandable section

---

### 🐛 Bug Fixes

#### Month Data Fetching
**Fixed:** Previous month data not rendering correctly
**Solution:** Changed to fetch each month separately instead of fetching together and splitting
**Impact:** More reliable month-over-month comparisons without timezone/boundary issues

---

### 🎨 UI/UX Improvements

#### Dropdown & Label Visibility
**Fixed:**
- Dropdown labels now bold and dark (#0f172a) for better readability
- "Select a category to drill down" label now clearly visible
- Sidebar month selector: black background (#0f172a) with white text when selected
- Main content dropdowns: white background with dark text, clear contrast
- Dropdown menu items readable when open (white background, dark text)
- Selected item: indigo background with white text
- Hover effect: light indigo background

**Why:** Users reported difficulty reading dropdown labels and selected values

#### Metrics Visibility
**Improved:**
- Key metrics values are bolder and darker for better contrast
- Main content metric values: font-weight 800, color #0f172a
- Sidebar metrics remain white for dark background
- Increased font sizes for prominence

---

### 🔧 Technical Improvements

#### Data Layer
- Extended `fetch_zendesk_tickets()` to support date ranges
- Extended `fetch_modjo_calls()` to support date ranges
- Refactored `fetch_all_data()` to handle both week and month modes
- Added `fetch_ticket_comments()` for deep dive analysis
- Improved ticket categorization and enrichment

#### Dependencies
- Added `python-dateutil>=2.8.2` for relativedelta calculations

#### Caching
- Maintained 5-minute TTL for all data modes
- Independent cache keys for week vs month views

---

### 🔍 Debug Tools

**Added:**
- Collapsible "🔍 Debug Info - Data Ranges" panel
- Shows ticket counts for current and previous periods
- Displays date ranges of fetched tickets
- Helps diagnose data fetching issues

**Where:** Below the header, before key metrics

---

## How to Use New Features

### Switching to Month View
1. Go to sidebar
2. Under "Time Period", click **Month** radio button
3. Select a month from dropdown (April 2026, March 2026, etc.)
4. Dashboard updates with month-over-month comparison

### Viewing Insights
1. Go to **Categories** or **Top Issues** tab
2. Scroll down to "💡 Actionable Insights & Opportunities"
3. Top 2 insights auto-expand, click others to expand
4. Read the insight, suggested action, and potential impact

### Running Deep Dive
1. Go to **Categories** or **Top Issues** tab
2. Scroll to "🔬 Deep Dive: Real Issues, Apps & Solutions"
3. Click to expand the section
4. Click "🔍 Analyze Solved Tickets" button
5. Wait for analysis (fetches up to 30 tickets with comments)
6. Review findings by app, issue type, and solutions

---

## What This Enables

### For Product Team
- Identify UX friction points (onboarding, sync, documents)
- Prioritize features based on ticket volume and impact
- Spot opportunities for self-service improvements
- Track success of fixes (declining ticket categories)

### For Engineering Team
- See which APIs/integrations need reliability improvements
- Identify automation opportunities (high manual intervention)
- Understand root causes of technical issues
- Prioritize bug fixes based on real customer impact

### For CS Team
- Understand most common issues and solutions
- Build better playbooks from proven solutions
- Identify training needs (varied solution patterns)
- Spot customers needing proactive engagement

### For Leadership
- Month-over-month trend analysis
- Data-driven prioritization of initiatives
- Impact measurement (before/after fix comparisons)
- Resource allocation based on ticket patterns

---

## Questions or Feedback?

Reach out if you:
- Have suggestions for additional insights
- Want different categorizations or patterns detected
- Need export functionality for reports
- Have ideas for new analysis types

---

**Dashboard URL:** https://smily-cs-insights.streamlit.app/

**Deployment:** Auto-deployed to Streamlit Cloud (live now)
