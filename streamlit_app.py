import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import os

try:
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()
except:
    from snowflake.snowpark import Session
    conn_name = os.getenv('SNOWFLAKE_CONNECTION_NAME', 'default')
    session = Session.builder.config('connection_name', conn_name).create()

st.title("Cortex Agent Usage Analytics")

@st.cache_data(ttl=300)
def get_agents():
    query = """
    SELECT 
        name as AGENT_NAME,
        database_name as DATABASE_NAME,
        schema_name as SCHEMA_NAME,
        owner as OWNER,
        comment as DESCRIPTION,
        created_on as CREATED_ON,
        TRY_PARSE_JSON(profile):display_name::STRING as DISPLAY_NAME
    FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
    """
    session.sql("SHOW AGENTS IN ACCOUNT").collect()
    return session.sql(query).to_pandas()

@st.cache_data(ttl=300)
def get_agent_usage_history(days_back: int = 90):
    query = f"""
    SELECT 
        USER_NAME,
        QUERY_TYPE,
        QUERY_TEXT,
        START_TIME,
        DATABASE_NAME,
        SCHEMA_NAME,
        TOTAL_ELAPSED_TIME,
        EXECUTION_STATUS
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY 
    WHERE (
        QUERY_TEXT ILIKE '%SNOWFLAKE_INTELLIGENCE.AGENTS%' 
        OR QUERY_TEXT ILIKE '%COMPLETE_AGENT%'
        OR QUERY_TEXT ILIKE '%RUN AGENT%'
        OR QUERY_TEXT ILIKE '%CREATE%AGENT%'
        OR QUERY_TEXT ILIKE '%ALTER%AGENT%'
        OR QUERY_TEXT ILIKE '%DESCRIBE AGENT%'
        OR QUERY_TEXT ILIKE '%SHOW%AGENT%'
    )
    AND QUERY_TEXT NOT ILIKE '%DataOps_Pipeline%'
    AND START_TIME >= DATEADD(day, -{days_back}, CURRENT_TIMESTAMP())
    ORDER BY START_TIME DESC
    """
    return session.sql(query).to_pandas()

def extract_agent_name(query_text):
    if pd.isna(query_text):
        return "Unknown"
    query_upper = query_text.upper()
    agents = [
        "COMPANY_CHATBOT_AGENT_RETAIL", "DATA_ENGINEER_ASSISTANT", "NEW_SF_DOCS",
        "PAWCORE_DEMO", "SALES_CONVERSATION_AGENT", "SLACK_SUPPORT_AI",
        "SNOWFLAKE_DCS", "TPCDS"
    ]
    for agent in agents:
        if agent in query_upper:
            return agent
    return "Other"

def categorize_action(query_type, query_text):
    if pd.isna(query_text):
        return "Other"
    query_upper = query_text.upper()
    if "CREATE" in query_upper and "AGENT" in query_upper:
        return "Create"
    elif "ALTER" in query_upper and "AGENT" in query_upper:
        return "Modify"
    elif "DESCRIBE" in query_upper and "AGENT" in query_upper:
        return "Describe"
    elif "SHOW" in query_upper and "AGENT" in query_upper:
        return "List"
    elif "RUN" in query_upper or "COMPLETE" in query_upper:
        return "Execute"
    return "Other"

try:
    agents_df = get_agents()
except:
    agents_df = pd.DataFrame()

usage_df = get_agent_usage_history()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Agents", len(agents_df) if not agents_df.empty else 8)
with col2:
    st.metric("Total Queries", len(usage_df))
with col3:
    unique_users = usage_df["USER_NAME"].nunique() if not usage_df.empty else 0
    st.metric("Active Users", unique_users)
with col4:
    if not usage_df.empty and len(usage_df) > 0:
        date_range = (usage_df["START_TIME"].max() - usage_df["START_TIME"].min()).days
        avg_per_day = len(usage_df) / max(date_range, 1)
        st.metric("Avg Queries/Day", f"{avg_per_day:.1f}")
    else:
        st.metric("Avg Queries/Day", "0")

st.divider()

if not usage_df.empty:
    usage_df["AGENT_NAME"] = usage_df["QUERY_TEXT"].apply(extract_agent_name)
    usage_df["ACTION_TYPE"] = usage_df.apply(
        lambda x: categorize_action(x["QUERY_TYPE"], x["QUERY_TEXT"]), axis=1
    )
    usage_df["DATE"] = pd.to_datetime(usage_df["START_TIME"]).dt.date
    usage_df["HOUR"] = pd.to_datetime(usage_df["START_TIME"]).dt.hour

tab1, tab2, tab3, tab4 = st.tabs(["What", "Who", "When", "Frequency"])

with tab1:
    st.subheader("What Agents Are Being Used")
    
    agent_counts = usage_df["AGENT_NAME"].value_counts().reset_index()
    agent_counts.columns = ["Agent", "Query Count"]
    
    chart = alt.Chart(agent_counts).mark_bar(color="#29B5E8").encode(
        x=alt.X("Query Count:Q", title="Number of Queries"),
        y=alt.Y("Agent:N", sort="-x", title="Agent Name"),
        tooltip=["Agent", "Query Count"]
    ).properties(height=300)
    st.altair_chart(chart, use_container_width=True)
    
    st.caption("Agent action types breakdown")
    action_by_agent = usage_df.groupby(["AGENT_NAME", "ACTION_TYPE"]).size().reset_index(name="Count")
    action_chart = alt.Chart(action_by_agent).mark_bar().encode(
        x=alt.X("Count:Q", title="Count"),
        y=alt.Y("AGENT_NAME:N", sort="-x", title="Agent"),
        color=alt.Color("ACTION_TYPE:N", title="Action Type"),
        tooltip=["AGENT_NAME", "ACTION_TYPE", "Count"]
    ).properties(height=300)
    st.altair_chart(action_chart, use_container_width=True)

with tab2:
    st.subheader("Who Is Using Agents")
    
    user_counts = usage_df["USER_NAME"].value_counts().reset_index()
    user_counts.columns = ["User", "Query Count"]
    
    user_chart = alt.Chart(user_counts.head(15)).mark_bar(color="#FF4B4B").encode(
        x=alt.X("Query Count:Q", title="Number of Queries"),
        y=alt.Y("User:N", sort="-x", title="User Name"),
        tooltip=["User", "Query Count"]
    ).properties(height=300)
    st.altair_chart(user_chart, use_container_width=True)
    
    st.caption("User activity by agent")
    user_agent = usage_df.groupby(["USER_NAME", "AGENT_NAME"]).size().reset_index(name="Count")
    user_agent_pivot = user_agent.pivot(index="USER_NAME", columns="AGENT_NAME", values="Count").fillna(0)
    st.dataframe(user_agent_pivot, use_container_width=True, hide_index=False)

with tab3:
    st.subheader("When Agents Are Being Used")
    
    daily_usage = usage_df.groupby("DATE").size().reset_index(name="Count")
    daily_usage["DATE"] = pd.to_datetime(daily_usage["DATE"])
    
    daily_chart = alt.Chart(daily_usage).mark_line(point=True, color="#29B5E8").encode(
        x=alt.X("DATE:T", title="Date"),
        y=alt.Y("Count:Q", title="Number of Queries"),
        tooltip=["DATE:T", "Count:Q"]
    ).properties(height=300)
    st.altair_chart(daily_chart, use_container_width=True)
    
    st.caption("Usage by hour of day")
    hourly_usage = usage_df.groupby("HOUR").size().reset_index(name="Count")
    
    hourly_chart = alt.Chart(hourly_usage).mark_bar(color="#FF9F00").encode(
        x=alt.X("HOUR:O", title="Hour of Day (24h)"),
        y=alt.Y("Count:Q", title="Number of Queries"),
        tooltip=["HOUR", "Count"]
    ).properties(height=250)
    st.altair_chart(hourly_chart, use_container_width=True)

with tab4:
    st.subheader("Usage Frequency Analysis")
    
    weekly_usage = usage_df.copy()
    weekly_usage["WEEK"] = pd.to_datetime(weekly_usage["START_TIME"]).dt.to_period("W").astype(str)
    weekly_counts = weekly_usage.groupby("WEEK").size().reset_index(name="Count")
    
    weekly_chart = alt.Chart(weekly_counts).mark_bar(color="#50C878").encode(
        x=alt.X("WEEK:N", title="Week", sort=None),
        y=alt.Y("Count:Q", title="Number of Queries"),
        tooltip=["WEEK", "Count"]
    ).properties(height=250)
    st.altair_chart(weekly_chart, use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.caption("Most active days")
        day_of_week = usage_df.copy()
        day_of_week["DAY"] = pd.to_datetime(day_of_week["START_TIME"]).dt.day_name()
        day_counts = day_of_week.groupby("DAY").size().reset_index(name="Count")
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_counts["DAY"] = pd.Categorical(day_counts["DAY"], categories=day_order, ordered=True)
        day_counts = day_counts.sort_values("DAY")
        st.dataframe(day_counts, use_container_width=True, hide_index=True)
    
    with col2:
        st.caption("Query execution stats")
        stats = {
            "Total Queries": len(usage_df),
            "Unique Users": usage_df["USER_NAME"].nunique(),
            "Unique Agents": usage_df["AGENT_NAME"].nunique(),
            "Success Rate": f"{(usage_df['EXECUTION_STATUS'] == 'SUCCESS').mean() * 100:.1f}%",
            "Avg Response (ms)": f"{usage_df['TOTAL_ELAPSED_TIME'].mean():.0f}"
        }
        st.dataframe(pd.DataFrame.from_dict(stats, orient="index", columns=["Value"]), use_container_width=True)

st.divider()

with st.expander("View Agent Details"):
    if not agents_df.empty:
        display_cols = ["AGENT_NAME", "DISPLAY_NAME", "OWNER", "DESCRIPTION", "CREATED_ON"]
        available_cols = [c for c in display_cols if c in agents_df.columns]
        st.dataframe(agents_df[available_cols], use_container_width=True, hide_index=True)
    else:
        st.info("Agent metadata not available. Showing known agents from SNOWFLAKE_INTELLIGENCE.AGENTS schema.")
        known_agents = pd.DataFrame({
            "Agent Name": ["COMPANY_CHATBOT_AGENT_RETAIL", "DATA_ENGINEER_ASSISTANT", "NEW_SF_DOCS",
                          "PAWCORE_DEMO", "SALES_CONVERSATION_AGENT", "SLACK_SUPPORT_AI", 
                          "SNOWFLAKE_DCS", "TPCDS"],
            "Schema": ["SNOWFLAKE_INTELLIGENCE.AGENTS"] * 8
        })
        st.dataframe(known_agents, use_container_width=True, hide_index=True)

with st.expander("Raw Query History"):
    display_cols = ["USER_NAME", "AGENT_NAME", "ACTION_TYPE", "START_TIME", "EXECUTION_STATUS"]
    st.dataframe(usage_df[display_cols].head(100), use_container_width=True, hide_index=True)

st.caption(f"Data refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Last 90 days of query history")
