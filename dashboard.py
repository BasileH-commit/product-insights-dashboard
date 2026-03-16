#!/usr/bin/env python3
"""
Product Insights Interactive Dashboard
Built with Streamlit - connects to Zendesk & Modjo APIs
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import json
import os

# Import data fetching functions
from dashboard_data import (
    fetch_all_data,
    get_category_breakdown,
    get_subcategory_breakdown,
    get_top_issues,
    get_top_customers,
    get_agent_stats,
    get_modjo_summary,
    CATEGORIES_DETAILED
)

# Page config
st.set_page_config(
    page_title="Product Insights Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for styling
st.markdown("""
<style>
    /* Main background */
    .main {
        background-color: #f8f9fc;
    }

    /* Cards */
    .metric-card {
        background: white;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        margin-bottom: 20px;
    }

    /* KPI styling */
    .kpi-value {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1e293b;
    }

    .kpi-label {
        font-size: 0.9rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .kpi-delta-positive {
        color: #10b981;
        font-size: 0.9rem;
    }

    .kpi-delta-negative {
        color: #ef4444;
        font-size: 0.9rem;
    }

    /* Section headers */
    .section-header {
        font-size: 1.25rem;
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 10px;
    }

    .section-subheader {
        font-size: 0.85rem;
        color: #64748b;
        margin-bottom: 20px;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }

    .stTabs [data-baseweb="tab"] {
        background-color: white;
        border-radius: 8px;
        padding: 8px 16px;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Table styling */
    .dataframe {
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)


def format_delta(current, previous):
    """Format delta with color and arrow."""
    if previous == 0:
        if current > 0:
            return "🆕 New", "positive"
        return "—", "neutral"

    delta = ((current - previous) / previous) * 100

    if delta > 0:
        return f"▲ +{delta:.1f}%", "positive"
    elif delta < 0:
        return f"▼ {delta:.1f}%", "negative"
    else:
        return "➡️ 0%", "neutral"


def render_kpi_card(label, value, delta_text, delta_type):
    """Render a KPI card."""
    delta_class = f"kpi-delta-{delta_type}" if delta_type != "neutral" else "kpi-delta-neutral"

    st.markdown(f"""
    <div class="metric-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        <div class="{delta_class}">{delta_text} vs last week</div>
    </div>
    """, unsafe_allow_html=True)


def create_comparison_chart(df, title, x_col, y_cols, colors=None):
    """Create a grouped bar chart comparing two periods."""
    if colors is None:
        colors = ['#6366f1', '#a5b4fc']  # Indigo shades

    fig = go.Figure()

    for i, col in enumerate(y_cols):
        fig.add_trace(go.Bar(
            name=col,
            x=df[x_col],
            y=df[col],
            marker_color=colors[i],
            text=df[col],
            textposition='outside'
        ))

    fig.update_layout(
        title=title,
        barmode='group',
        xaxis_tickangle=-45,
        height=400,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        plot_bgcolor='white',
        paper_bgcolor='white',
        margin=dict(t=80, b=100)
    )

    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor='#f1f5f9')

    return fig


def create_trend_table(df):
    """Create a styled dataframe with trend indicators."""

    def style_delta(val):
        if isinstance(val, str):
            if '▲' in val or '+' in val:
                return 'color: #10b981; font-weight: 600'
            elif '▼' in val or '-' in val:
                return 'color: #ef4444; font-weight: 600'
        return ''

    styled = df.style.applymap(style_delta, subset=['Δ', 'WoW %'])
    return styled


@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data(days_back=7):
    """Load data with caching."""
    return fetch_all_data(days_back)


def main():
    # Sidebar
    with st.sidebar:
        st.image("https://bookingsync.com/images/logo.svg", width=150)
        st.title("📊 Product Insights")
        st.markdown("---")

        # Date range selector
        st.subheader("📅 Time Period")
        period = st.selectbox(
            "Select period",
            ["Last 7 days", "Last 14 days", "Last 30 days"],
            index=0
        )

        days_map = {"Last 7 days": 7, "Last 14 days": 14, "Last 30 days": 30}
        days_back = days_map[period]

        # Data source selector
        st.subheader("📡 Data Source")
        data_source = st.multiselect(
            "Select sources",
            ["Zendesk", "Modjo"],
            default=["Zendesk", "Modjo"]
        )

        st.markdown("---")

        # Refresh button
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Main content
    st.title("Product Insights Dashboard")
    st.markdown(f"<p class='section-subheader'>Analyzing data from {period.lower()} • Zendesk + Modjo</p>", unsafe_allow_html=True)

    # Load data
    with st.spinner("Loading data from APIs..."):
        try:
            data = load_data(days_back)
        except Exception as e:
            st.error(f"Error loading data: {e}")
            st.info("Make sure your .env file has valid API credentials.")
            return

    if not data:
        st.warning("No data available. Check your API connections.")
        return

    # Extract data
    tickets_tw = data.get("tickets_this_week", [])
    tickets_lw = data.get("tickets_last_week", [])
    categories_tw = data.get("categories_this_week", {})
    categories_lw = data.get("categories_last_week", {})
    modjo_tw = data.get("modjo_this_week", [])
    modjo_lw = data.get("modjo_last_week", [])

    # ========== KPI SECTION ==========
    st.markdown("### 📈 Key Metrics")

    kpi_cols = st.columns(5)

    # Total Tickets
    with kpi_cols[0]:
        delta_text, delta_type = format_delta(len(tickets_tw), len(tickets_lw))
        st.metric(
            label="Total Tickets",
            value=len(tickets_tw),
            delta=f"{((len(tickets_tw) - len(tickets_lw)) / len(tickets_lw) * 100):.1f}%" if tickets_lw else "N/A"
        )

    # High Priority
    with kpi_cols[1]:
        hp_tw = sum(1 for t in tickets_tw if t.get("priority") in ["high", "urgent"])
        hp_lw = sum(1 for t in tickets_lw if t.get("priority") in ["high", "urgent"])
        st.metric(
            label="High Priority",
            value=hp_tw,
            delta=f"{hp_tw - hp_lw:+d}" if tickets_lw else "N/A"
        )

    # Solved Rate
    with kpi_cols[2]:
        solved_tw = sum(1 for t in tickets_tw if t.get("status") == "solved")
        rate_tw = (solved_tw / len(tickets_tw) * 100) if tickets_tw else 0
        solved_lw = sum(1 for t in tickets_lw if t.get("status") == "solved")
        rate_lw = (solved_lw / len(tickets_lw) * 100) if tickets_lw else 0
        st.metric(
            label="Solve Rate",
            value=f"{rate_tw:.0f}%",
            delta=f"{rate_tw - rate_lw:.1f}pp" if tickets_lw else "N/A"
        )

    # Modjo Calls
    with kpi_cols[3]:
        st.metric(
            label="Modjo Calls",
            value=len(modjo_tw),
            delta=f"{len(modjo_tw) - len(modjo_lw):+d}" if modjo_lw else "N/A"
        )

    # Unique Customers
    with kpi_cols[4]:
        customers_tw = len(set(t.get("organization_name") for t in tickets_tw if t.get("organization_name")))
        customers_lw = len(set(t.get("organization_name") for t in tickets_lw if t.get("organization_name")))
        st.metric(
            label="Unique Customers",
            value=customers_tw,
            delta=f"{customers_tw - customers_lw:+d}" if tickets_lw else "N/A"
        )

    st.markdown("---")

    # ========== TABS ==========
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Categories", "🔥 Top Issues", "🏢 Customers", "👤 Agents"])

    # ========== TAB 1: CATEGORIES ==========
    with tab1:
        st.markdown("### Tickets by Category — Overview")
        st.markdown(f"<p class='section-subheader'>All categories with WoW comparison • Total: {len(tickets_tw)} tickets</p>", unsafe_allow_html=True)

        # Prepare category data
        cat_data = []
        for cat in set(list(categories_tw.keys()) + list(categories_lw.keys())):
            tw_count = categories_tw.get(cat, 0)
            lw_count = categories_lw.get(cat, 0)
            delta = tw_count - lw_count
            wow_pct = ((tw_count - lw_count) / lw_count * 100) if lw_count > 0 else (100 if tw_count > 0 else 0)

            cat_data.append({
                "Category": cat,
                "This Week": tw_count,
                "Last Week": lw_count,
                "Δ": delta,
                "WoW %": f"{wow_pct:+.1f}%" if lw_count > 0 else ("🆕 New" if tw_count > 0 else "—")
            })

        cat_df = pd.DataFrame(cat_data)
        cat_df = cat_df.sort_values("This Week", ascending=False)

        # Chart
        chart_df = cat_df.head(10).copy()
        fig = create_comparison_chart(
            chart_df,
            "",
            "Category",
            ["This Week", "Last Week"],
            colors=['#6366f1', '#a5b4fc']
        )
        st.plotly_chart(fig, use_container_width=True)

        # Table
        st.markdown("#### Detailed Breakdown")

        # Style the dataframe
        display_df = cat_df[["Category", "This Week", "Last Week", "Δ", "WoW %"]].copy()

        def color_delta(val):
            if isinstance(val, (int, float)):
                if val > 0:
                    return 'color: #10b981'
                elif val < 0:
                    return 'color: #ef4444'
            elif isinstance(val, str):
                if '+' in val or '🆕' in val:
                    return 'color: #10b981'
                elif '-' in val:
                    return 'color: #ef4444'
            return ''

        styled_df = display_df.style.applymap(color_delta, subset=['Δ', 'WoW %'])
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

        # Subcategory drill-down
        st.markdown("---")
        st.markdown("### 🔍 Subcategory Breakdown")

        selected_category = st.selectbox(
            "Select a category to drill down",
            options=cat_df["Category"].tolist()
        )

        if selected_category:
            subcats = get_subcategory_breakdown(tickets_tw, tickets_lw, selected_category)

            if subcats:
                subcat_df = pd.DataFrame(subcats)
                subcat_df = subcat_df.sort_values("This Week", ascending=False)

                # Subcategory chart
                fig_sub = create_comparison_chart(
                    subcat_df.head(15),
                    f"{selected_category} — Subcategory Breakdown",
                    "Subcategory",
                    ["This Week", "Last Week"],
                    colors=['#6366f1', '#a5b4fc']
                )
                st.plotly_chart(fig_sub, use_container_width=True)

                # Subcategory table
                st.dataframe(
                    subcat_df.style.applymap(color_delta, subset=['Δ', 'WoW %']),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No subcategory data available for this category.")

    # ========== TAB 2: TOP ISSUES ==========
    with tab2:
        st.markdown("### 🔥 Top Issues")
        st.markdown(f"<p class='section-subheader'>Most frequent ticket subjects</p>", unsafe_allow_html=True)

        top_issues = get_top_issues(tickets_tw, tickets_lw, limit=15)

        if top_issues:
            issues_df = pd.DataFrame(top_issues)

            # Chart
            fig_issues = px.bar(
                issues_df.head(10),
                x="Issue",
                y="Count",
                color="Customers",
                title="Top 10 Issues by Ticket Count",
                color_continuous_scale="Blues"
            )
            fig_issues.update_layout(
                xaxis_tickangle=-45,
                height=450,
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            st.plotly_chart(fig_issues, use_container_width=True)

            # Table
            st.markdown("#### All Issues")

            def color_trend(val):
                if '▲' in str(val):
                    return 'color: #ef4444'  # Red for increasing issues
                elif '▼' in str(val):
                    return 'color: #10b981'  # Green for decreasing
                return ''

            display_issues = issues_df[["Issue", "Count", "Customers", "Trend"]].copy()
            st.dataframe(
                display_issues.style.applymap(color_trend, subset=['Trend']),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No issue data available.")

    # ========== TAB 3: CUSTOMERS ==========
    with tab3:
        st.markdown("### 🏢 Top Customers by Ticket Volume")
        st.markdown(f"<p class='section-subheader'>Customers with most tickets this period</p>", unsafe_allow_html=True)

        top_customers = get_top_customers(tickets_tw, tickets_lw, limit=15)

        if top_customers:
            cust_df = pd.DataFrame(top_customers)

            # Chart
            fig_cust = px.bar(
                cust_df.head(10),
                x="Customer",
                y="Tickets",
                title="Top 10 Customers by Volume",
                color="Tickets",
                color_continuous_scale="Purples"
            )
            fig_cust.update_layout(
                xaxis_tickangle=-45,
                height=450,
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            st.plotly_chart(fig_cust, use_container_width=True)

            # Table
            st.markdown("#### Customer Details")
            st.dataframe(cust_df, use_container_width=True, hide_index=True)

            # At-risk highlight
            st.markdown("---")
            st.markdown("### ⚠️ Customers to Watch")

            # Find customers with high volume or increasing trend
            watch_list = [c for c in top_customers if c.get("Tickets", 0) >= 5 or "▲" in str(c.get("Trend", ""))]

            if watch_list:
                for cust in watch_list[:5]:
                    st.warning(f"**{cust['Customer']}** — {cust['Tickets']} tickets ({cust.get('Trend', '')})")
            else:
                st.success("No customers flagged for attention.")
        else:
            st.info("No customer data available.")

    # ========== TAB 4: AGENTS ==========
    with tab4:
        st.markdown("### 👤 Agent Performance")
        st.markdown(f"<p class='section-subheader'>Ticket assignments and solve rates</p>", unsafe_allow_html=True)

        agent_stats = get_agent_stats(tickets_tw, tickets_lw)

        if agent_stats:
            agent_df = pd.DataFrame(agent_stats)

            # Chart
            fig_agent = go.Figure()

            fig_agent.add_trace(go.Bar(
                name="Assigned",
                x=agent_df["Agent"],
                y=agent_df["Assigned"],
                marker_color='#6366f1'
            ))

            fig_agent.add_trace(go.Bar(
                name="Solved",
                x=agent_df["Agent"],
                y=agent_df["Solved"],
                marker_color='#10b981'
            ))

            fig_agent.update_layout(
                title="Agent Workload & Performance",
                barmode='group',
                xaxis_tickangle=-45,
                height=450,
                plot_bgcolor='white',
                paper_bgcolor='white',
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            st.plotly_chart(fig_agent, use_container_width=True)

            # Table
            st.markdown("#### Agent Statistics")
            st.dataframe(agent_df, use_container_width=True, hide_index=True)
        else:
            st.info("No agent data available.")

    # ========== FOOTER ==========
    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("📊 **Data Sources**")
        st.caption("Zendesk API • Modjo API")

    with col2:
        st.markdown("🔗 **Quick Links**")
        st.caption("[Notion Insights](https://www.notion.so/smilycom/Insights-from-CS-Modjo-Automated-3185d6a20ddc8084ada8f279005803b8)")

    with col3:
        st.markdown("⏰ **Auto-refresh**")
        st.caption("Data cached for 5 minutes")


if __name__ == "__main__":
    main()
