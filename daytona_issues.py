"""
Original file is located at
    https://colab.research.google.com/drive/1MIc8fDaCk5zfJ04oEg5yE6O8vnnRqfRs
"""

import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import json
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# GitHub repository information
owner = "daytonaio"
repo = "daytona"
api_url = f"https://api.github.com/repos/{owner}/{repo}"

# Load environment variables from .env file, for local testing uncomment the following lines
# from dotenv import load_dotenv  # Import load_dotenv
# load_dotenv()

# Your GitHub personal access token (replace 'your_token_here' with your actual token)
access_token = os.environ.get('GITHUB_TOKEN')

headers = {
    'Authorization': f'token {access_token}'
}

# Get current date in YYYYMMDD format
current_date = datetime.now().strftime("%Y%m%d")

# Create artifact directory if it doesn't exist
artifact_dir = "artifact"
os.makedirs(artifact_dir, exist_ok=True)

# Redirect print output to a file
output_file = os.path.join(artifact_dir, f"{current_date}_weekly_issues_results.txt")
sys.stdout = open(output_file, 'w')


def check_rate_limit():
    response = requests.get('https://api.github.com/rate_limit', headers=headers)
    if response.status_code == 200:
        data = response.json()
        remaining = data['resources']['core']['remaining']
        reset_time = datetime.fromtimestamp(data['resources']['core']['reset'])
        if remaining < 10:
            wait_time = (reset_time - datetime.now()).total_seconds()
            print(f"Rate limit almost exceeded. Waiting for {wait_time:.2f} seconds.")
            time.sleep(wait_time + 1)
    else:
        print("Failed to check rate limit.")

def create_weekly_issues_plot(weekly_data, owner, repo):
    """
    Create a plotly figure for weekly opened and closed issues.

    Parameters:
    weekly_data (pd.DataFrame): DataFrame containing weekly issue data
    owner (str): Owner of the repository
    repo (str): Name of the repository

    Returns:
    plotly.graph_objs._figure.Figure: Plotly figure object
    """
    # Convert 'week' to a list of Python datetime objects
    x_values = weekly_data['week'].to_numpy()

    # Create figure with secondary y-axis
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add traces
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=weekly_data['issues_opened'],
            name="Issues Opened",
            text=weekly_data['issues_opened'],
            textposition="top center",
            mode='lines+markers+text'
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=weekly_data['issues_closed'],
            name="Issues Closed",
            text=weekly_data['issues_closed'],
            textposition="bottom center",
            mode='lines+markers+text'
        ),
        secondary_y=True,
    )

    # Add figure title
    fig.update_layout(
        title_text=f"Weekly Analysis of Issues for {owner}/{repo}",
        width=1200,  # Increase width for a wider image
        height=600,  # Adjust height as needed
    )

    # Set x-axis title
    fig.update_xaxes(title_text="Week")

    # Set y-axes titles
    fig.update_yaxes(title_text="Issues Opened", secondary_y=False)
    fig.update_yaxes(title_text="Issues Closed", secondary_y=True)

    return fig

def fetch_issues(state='all', since=None):
    print(f"Fetching {state} issues for repository: {owner}/{repo}")
    issues = []
    page = 1
    params = {'state': state, 'per_page': 100}
    if since:
        params['since'] = since.isoformat()
        print(f"Fetching issues since: {params['since']}")

    while True:
        check_rate_limit()
        print(f"Requesting page {page} of issues")
        try:
            response = requests.get(f"{api_url}/issues", headers=headers, params=params)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error fetching issues: {e}")
            break

        page_data = response.json()
        print(f"Retrieved {len(page_data)} issues from page {page}")

        if len(page_data) == 0:
            break
        issues.extend([issue for issue in page_data if 'pull_request' not in issue])

        if 'next' not in response.links:
            break
        page += 1
        params['page'] = page

    print(f"Total {state} issues fetched: {len(issues)}")
    return issues

def parse_dates(issues):
    print("Parsing dates for issues")
    for issue in issues:
        issue['created_at'] = pd.to_datetime(issue['created_at'], utc=True).tz_localize(None)
        if issue.get('closed_at'):
            issue['closed_at'] = pd.to_datetime(issue['closed_at'], utc=True).tz_localize(None)
    print("Date parsing completed")
    return issues

def weekly_analysis(df):
    logging.info("Starting weekly analysis")
    logging.info(f"DataFrame shape: {df.shape}")
    logging.info(f"DataFrame columns: {df.columns}")

    if 'created_at' not in df.columns:
        logging.error("'created_at' column not found in DataFrame")
        logging.info(f"First few rows of DataFrame:\n{df.head()}")
        raise KeyError("'created_at' column not found in DataFrame")

    # Convert 'created_at' to datetime if it's not already
    df['created_at'] = pd.to_datetime(df['created_at'])
    logging.info("Converted 'created_at' to datetime")

    # Use datetime for week start instead of Period
    df['week'] = df['created_at'].dt.to_period('W').apply(lambda r: r.start_time)
    weekly_opened = df.groupby('week').size().reset_index(name='issues_opened')
    logging.info("Weekly opened issues calculated")

    closed_issues = df[df['state'] == 'closed'].copy()
    logging.info(f"Number of closed issues: {len(closed_issues)}")

    if 'closed_at' not in closed_issues.columns:
        logging.error("'closed_at' column not found in closed_issues DataFrame")
        logging.info(f"Closed issues columns: {closed_issues.columns}")
        raise KeyError("'closed_at' column not found in closed_issues DataFrame")

    # Convert 'closed_at' to datetime if it's not already
    closed_issues['closed_at'] = pd.to_datetime(closed_issues['closed_at'])
    closed_issues['week_closed'] = closed_issues['closed_at'].dt.to_period('W').apply(lambda r: r.start_time)
    weekly_closed = closed_issues.groupby('week_closed').size().reset_index(name='issues_closed')
    logging.info("Weekly closed issues calculated")

    # Combine opened and closed issues
    weekly_combined = pd.merge(weekly_opened, weekly_closed, left_on='week', right_on='week_closed', how='outer').fillna(0)
    weekly_combined = weekly_combined.drop('week_closed', axis=1)

    # Ensure 'week' column is datetime
    weekly_combined['week'] = pd.to_datetime(weekly_combined['week'])

    # Filter out invalid dates (before 2000)
    weekly_combined = weekly_combined[weekly_combined['week'].dt.year >= 2000]

    # Sort by the datetime 'week' column
    weekly_combined = weekly_combined.sort_values('week')

    # Convert 'issues_opened' and 'issues_closed' to integers
    weekly_combined['issues_opened'] = weekly_combined['issues_opened'].astype(int)
    weekly_combined['issues_closed'] = weekly_combined['issues_closed'].astype(int)

    # Calculate total opened and closed issues
    total_opened = weekly_combined['issues_opened'].sum()
    total_closed = weekly_combined['issues_closed'].sum()

    logging.info("Weekly analysis completed")
    logging.info(f"Total issues opened: {total_opened}")
    logging.info(f"Total issues closed: {total_closed}")

    return weekly_combined

def fetch_forks():
    print(f"Fetching forks count for repository: {owner}/{repo}")
    check_rate_limit()
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        forks_count = response.json().get('forks_count', 0)
        print(f"Forks count fetched: {forks_count}")
        return forks_count
    except requests.RequestException as e:
        print(f"Error fetching forks count: {e}")
        return 0

def save_data(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f)
    print(f"Data saved to {filename}")

def load_data(filename):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return None

def main():
    # Fetch new data
    issues = fetch_issues()
    forks_count = fetch_forks()
    # Save the fetched data
    save_data({'issues': issues, 'forks_count': forks_count}, 'github_data.json')

    # Parse dates and create DataFrame
    issues_with_dates = parse_dates(issues)
    df = pd.DataFrame(issues_with_dates)
    logging.info(f"Created DataFrame with shape: {df.shape}")
    logging.info(f"DataFrame columns: {df.columns}")

    # Perform weekly analysis
    weekly_data = weekly_analysis(df)

    # Print results
    print("\nWeekly Issue Analysis:")
    print(weekly_data)
    print(f"\nTotal Forks: {forks_count}")

    # Create the plot
    fig = create_weekly_issues_plot(weekly_data, owner, repo)

    # Write the interactive plot
    plot_filename = os.path.join(artifact_dir, "weekly_issues_plot.png")
    fig.write_image(plot_filename)
    print(f"\nPlot saved as: {plot_filename}")

if __name__ == "__main__":
    main()
    sys.stdout.close()  # Close the file
    sys.stdout = sys.__stdout__  # Reset stdout to the console
    print(f"Results saved in {output_file}")
    print(f"Plot saved in {artifact_dir}/weekly_issues_plot.png")